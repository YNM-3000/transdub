"""Tests for retry policy, scheduler, and the full pipeline flow."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from orchestrate import flow
from orchestrate.flow import (
    AWAITING_REVIEW,
    COMPLETED,
    COMPOSE_FAILED,
    DOWNLOAD_FAILED,
    TRANSLATE_FAILED,
    run_full,
)
from orchestrate.retry import RetryPolicy, retry
from orchestrate.scheduler import run_periodically


# --- retry -------------------------------------------------------------------

def test_retry_returns_first_success():
    calls = []
    out = retry(lambda: calls.append(1) or "ok", RetryPolicy(attempts=3),
                success=lambda r: True, sleep=lambda _s: None)
    assert out == "ok" and len(calls) == 1


def test_retry_retries_until_success():
    seq = iter([SimpleNamespace(ok=False), SimpleNamespace(ok=False), SimpleNamespace(ok=True)])
    slept = []
    out = retry(lambda: next(seq), RetryPolicy(attempts=5, base_delay=1.0),
                success=lambda r: r.ok, sleep=slept.append)
    assert out.ok is True
    assert slept == [1.0, 2.0]  # backoff before the 2 retries


def test_retry_returns_last_failed_result_when_exhausted():
    out = retry(lambda: SimpleNamespace(ok=False, n=1), RetryPolicy(attempts=3),
                success=lambda r: r.ok, sleep=lambda _s: None)
    assert out.ok is False


def test_retry_reraises_when_every_attempt_raises():
    def boom():
        raise RuntimeError("nope")
    with pytest.raises(RuntimeError):
        retry(boom, RetryPolicy(attempts=2), sleep=lambda _s: None)


def test_retry_recovers_from_transient_exception():
    seq = iter([None, "ok"])
    def fn():
        v = next(seq)
        if v is None:
            raise ValueError("transient")
        return v
    assert retry(fn, RetryPolicy(attempts=3), sleep=lambda _s: None) == "ok"


def test_policy_backoff_is_capped():
    p = RetryPolicy(base_delay=10.0, max_delay=15.0)
    assert p.delay_for(0) == 10.0
    assert p.delay_for(5) == 15.0  # capped


# --- scheduler ---------------------------------------------------------------

def test_run_periodically_bounded_by_max_runs():
    runs = []
    n = run_periodically(lambda: runs.append(1), 0.0, max_runs=3, sleep=lambda _s: None)
    assert n == 3 and len(runs) == 3


def test_run_periodically_continues_on_error_with_handler():
    errors = []
    count = {"n": 0}
    def task():
        count["n"] += 1
        raise RuntimeError("boom")
    run_periodically(task, 0.0, max_runs=2, sleep=lambda _s: None, on_error=errors.append)
    assert count["n"] == 2 and len(errors) == 2


# --- full flow ---------------------------------------------------------------

def _dl(ok=True, **kw):
    from download.models import DownloadResult, VideoInfo
    return DownloadResult(
        url="u", ok=ok,
        video_path=kw.get("video_path"), subtitle_path=kw.get("subtitle_path"),
        info=VideoInfo(id="vid", title="T", channel="C", url="u", view_count=100),
        error=None if ok else "dl error",
    )


def _tr(ok=True, ass="/x.ass"):
    from orchestrate.models import PipelineResult, TRANSLATED, TRANSLATE_FAILED as TF
    from pathlib import Path
    return PipelineResult("u", TRANSLATED if ok else TF,
                          ass_path=Path(ass) if ok else None,
                          error=None if ok else "tr error")


def _cmp(ok=True):
    from compose.models import ComposeResult, BURN
    from pathlib import Path
    return ComposeResult(Path("/v.mp4"), Path("/s.ass"), Path("/out.mp4"), BURN,
                         ok=ok, error=None if ok else "cmp error")


class RecordingStore:
    def __init__(self):
        self.records = []
    def record_source(self, rec):
        self.records.append(rec)


@pytest.fixture
def stub_stages(monkeypatch):
    """Patch every stage in flow with controllable fakes."""
    state = {
        "download": _dl(),
        "translate": _tr(),
        "compose": _cmp(),
    }
    monkeypatch.setattr(flow, "download_one", lambda url, **k: state["download"])
    monkeypatch.setattr(flow, "translate_download", lambda dl, backend, **k: state["translate"])
    monkeypatch.setattr(flow, "compose", lambda *a, **k: state["compose"])
    monkeypatch.setattr(flow, "find_info_json", lambda *a: None)
    monkeypatch.setattr(flow, "source_thumbnail_for", lambda p: None)
    monkeypatch.setattr(flow, "chinese_from_ass", lambda p: "内容")
    return state


_FAST = RetryPolicy(attempts=2, base_delay=0.0)


def test_run_full_completes_without_publish(stub_stages):
    store = RecordingStore()
    r = run_full("u", backend=object(), policy=_FAST, store=store, sleep=lambda _s: None)
    assert r.status == COMPLETED and r.ok
    assert r.data_recorded and len(store.records) == 1
    assert store.records[0].source_id == "vid"


def test_run_full_dubs_when_voice_backend_given(stub_stages, monkeypatch):
    from pathlib import Path

    from dub.models import DubResult

    called = {}

    def fake_dub(video, ass, backend, **k):
        called["ran"] = (video, ass, backend)
        return DubResult(Path(video), Path(f"{video}.dubbed.mp4"), ok=True, voice="fake")

    monkeypatch.setattr(flow, "dub_video", fake_dub)
    r = run_full("u", backend=object(), voice_backend=object(),
                 policy=_FAST, sleep=lambda _s: None)
    assert r.status == COMPLETED
    assert called.get("ran") is not None  # dub ran
    assert r.dub is not None and r.dub.ok


def test_run_full_dub_failure_is_non_fatal(stub_stages, monkeypatch):
    from pathlib import Path

    from dub.models import DubResult

    monkeypatch.setattr(
        flow, "dub_video",
        lambda v, a, b, **k: DubResult(Path("v"), Path("o"), ok=False, error="boom"),
    )
    r = run_full("u", backend=object(), voice_backend=object(),
                 policy=_FAST, sleep=lambda _s: None)
    assert r.status == COMPLETED  # dub failure does not block completion
    assert r.dub is not None and not r.dub.ok


def test_run_full_stops_after_translate_for_review(stub_stages):
    r = run_full("u", backend=object(), policy=_FAST, stop_after="translate", sleep=lambda _s: None)
    assert r.status == AWAITING_REVIEW
    assert r.compose is None


def test_run_full_download_failure_short_circuits(stub_stages):
    stub_stages["download"] = _dl(ok=False)
    r = run_full("u", backend=object(), policy=_FAST, sleep=lambda _s: None)
    assert r.status == DOWNLOAD_FAILED and not r.ok
    assert r.translation is None


def test_run_full_translate_failure_short_circuits(stub_stages):
    stub_stages["translate"] = _tr(ok=False)
    r = run_full("u", backend=object(), policy=_FAST, sleep=lambda _s: None)
    assert r.status == TRANSLATE_FAILED


def test_run_full_compose_failure_short_circuits(stub_stages):
    stub_stages["compose"] = _cmp(ok=False)
    r = run_full("u", backend=object(), policy=_FAST, sleep=lambda _s: None)
    assert r.status == COMPOSE_FAILED


def test_run_full_retries_a_flaky_stage(monkeypatch, stub_stages):
    attempts = {"n": 0}
    def flaky_compose(*a, **k):
        attempts["n"] += 1
        return _cmp(ok=attempts["n"] >= 2)  # fail once, then succeed
    monkeypatch.setattr(flow, "compose", flaky_compose)
    r = run_full("u", backend=object(), policy=RetryPolicy(attempts=3, base_delay=0.0),
                 sleep=lambda _s: None)
    assert r.status == COMPLETED and attempts["n"] == 2


def test_run_full_runs_publish_when_backend_given(monkeypatch, stub_stages):
    from publish.models import PublishMetadata, PublishPackage
    from pathlib import Path
    pkg = PublishPackage(Path("/out.mp4"), ok=True,
                         metadata=PublishMetadata("标题", "简介", ("t",)),
                         metadata_path=Path("/out.metadata.json"))
    monkeypatch.setattr(flow, "build_package", lambda *a, **k: pkg)
    r = run_full("u", backend=object(), metadata_backend=object(), policy=_FAST,
                 sleep=lambda _s: None)
    assert r.status == COMPLETED and r.publish is pkg
