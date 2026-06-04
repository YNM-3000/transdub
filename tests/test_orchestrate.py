"""Orchestration tests: download → translate handoff (no network, no API)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pysubs2
import pytest

from download.models import DownloadResult, VideoInfo
from orchestrate.models import (
    DOWNLOAD_FAILED,
    NO_SUBTITLE,
    TRANSLATE_FAILED,
    TRANSLATED,
)
from orchestrate.pipeline import process_url, process_urls, translate_download


@pytest.fixture
def downloaded(tmp_path):
    """A successful DownloadResult with a real subtitle file on disk."""
    folder = tmp_path / "2026-06-04" / "Chan"
    folder.mkdir(parents=True)
    video = folder / "Clip.mp4"
    video.write_bytes(b"x")
    srt = folder / "Clip.en.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nHello\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\nWorld\n",
        encoding="utf-8",
    )
    info = VideoInfo(id="i", title="Clip", channel="Chan", url="u")
    return DownloadResult(
        url="u", ok=True, video_path=video, subtitle_path=srt, info=info
    )


def test_translate_download_writes_ass_next_to_video(downloaded, fake_backend):
    res = translate_download(downloaded, fake_backend)

    assert res.status == TRANSLATED
    assert res.ok
    assert res.ass_path == downloaded.video_path.with_suffix(".bilingual.ass")
    assert res.ass_path.is_file()
    subs = pysubs2.load(str(res.ass_path))
    assert "译:Hello" in subs[0].text  # fake_backend prefixes 译:


def test_translate_download_skips_when_download_failed(fake_backend):
    failed = DownloadResult(url="u", ok=False, error="bot check")
    res = translate_download(failed, fake_backend)
    assert res.status == DOWNLOAD_FAILED
    assert res.error == "bot check"
    assert res.ass_path is None


def test_translate_download_skips_when_no_subtitle(tmp_path, fake_backend):
    no_sub = DownloadResult(
        url="u", ok=True, video_path=tmp_path / "v.mp4", subtitle_path=None
    )
    res = translate_download(no_sub, fake_backend)
    assert res.status == NO_SUBTITLE
    assert not res.ok


def test_translate_download_reports_translate_failure(downloaded):
    class BoomBackend:
        def translate_chunk(self, cues, context):
            raise RuntimeError("model exploded")

    res = translate_download(downloaded, BoomBackend())
    assert res.status == TRANSLATE_FAILED
    assert "model exploded" in res.error


# --- process_url / process_urls wire the real download stage via a fake runner ---


def _proc(stdout):
    return SimpleNamespace(returncode=0, stdout=stdout, stderr="")


class FakeRunner:
    """Simulates yt-dlp: writes video + srt and prints info JSON."""

    def __init__(self):
        self.commands = []

    def __call__(self, cmd):
        self.commands.append(cmd)
        url = cmd[-1]
        tmpl = cmd[cmd.index("-o") + 1]
        root = tmpl.split("/%(channel)s/")[0]
        folder = Path(root) / "Chan"
        folder.mkdir(parents=True, exist_ok=True)
        video = folder / f"{url.rsplit('/', 1)[-1]}.mp4"
        video.write_bytes(b"x")
        (video.with_suffix(".en.srt")).write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHi\n", encoding="utf-8"
        )
        return _proc(json.dumps({"id": "i", "title": video.stem, "channel": "Chan",
                                 "webpage_url": url, "_filename": str(video)}))


def test_process_url_downloads_then_translates(tmp_path, fake_backend):
    res = process_url(
        "https://yt/clipA",
        fake_backend,
        base_dir=tmp_path,
        day="2026-06-04",
        runner=FakeRunner(),
    )
    assert res.status == TRANSLATED
    assert res.ass_path.is_file()
    assert res.download.video_path.parent.parent.name == "2026-06-04"


def test_process_urls_handles_each_independently(tmp_path, fake_backend):
    urls = ["https://yt/a", "https://yt/b", "https://yt/c"]
    results = process_urls(
        urls,
        fake_backend,
        max_workers=2,
        base_dir=tmp_path,
        day="2026-06-04",
        runner=FakeRunner(),
    )
    assert [r.url for r in results] == urls
    assert all(r.status == TRANSLATED for r in results)
    assert all(r.ass_path.is_file() for r in results)


def test_cli_runs_pipeline_and_reports(monkeypatch, capsys):
    from orchestrate import cli
    from orchestrate.flow import COMPLETED, DOWNLOAD_FAILED, FlowResult

    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(cli, "get_backend", lambda name: object())
    results = iter([
        FlowResult("u1", COMPLETED),
        FlowResult("u2", DOWNLOAD_FAILED, error="boom"),
    ])
    monkeypatch.setattr(cli, "run_full", lambda url, **k: next(results))

    rc = cli.main(["u1", "u2", "--no-publish", "--no-data"])
    out = capsys.readouterr()

    assert rc == 1
    assert "completed" in out.out
    assert "boom" in out.err


def test_cli_no_urls_returns_2(monkeypatch):
    from orchestrate import cli
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
    assert cli.main([]) == 2


def test_cli_backend_resolution_error_returns_2(monkeypatch):
    from orchestrate import cli

    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(cli, "get_backend", lambda name: (_ for _ in ()).throw(ValueError("bad")))
    assert cli.main(["u", "--backend", "nope", "--no-data", "--no-publish"]) == 2


def test_cli_monitor_mode_delegates(monkeypatch):
    from orchestrate import cli

    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
    captured = {}
    monkeypatch.setattr(cli, "monitor_main", lambda argv: captured.update(argv=argv) or 0)
    assert cli.main(["--monitor", "--config", "c.json", "--db", "d.db", "--dry-run"]) == 0
    assert "--dry-run" in captured["argv"]


def test_cli_schedule_uses_scheduler(monkeypatch):
    from orchestrate import cli

    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(cli, "get_backend", lambda name: object())
    captured = {}
    monkeypatch.setattr(
        cli, "run_periodically",
        lambda task, interval, **k: captured.update(interval=interval, max_runs=k.get("max_runs")),
    )
    rc = cli.main(["u", "--no-publish", "--no-data", "--schedule", "30", "--max-runs", "5"])
    assert rc == 0
    assert captured["interval"] == 30 and captured["max_runs"] == 5
