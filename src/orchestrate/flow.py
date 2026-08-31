"""The full per-video flow: download → translate → compose → publish → data.

Each stage is wrapped in the retry policy. Stages return result objects (with
`.ok`), so a stage that ultimately fails short-circuits the flow and is
reported in the FlowResult rather than raising.

Note: this autopilot bypasses the human subtitle-review gate. Use
`stop_after="translate"` to halt for review before compose.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import obs
from compose.ffmpeg import compose
from compose.models import ComposeResult
from data.models import SourceRecord
from download.downloader import download_one
from download.models import DownloadResult, VideoInfo
from publish.content import chinese_from_ass
from publish.models import PublishPackage
from publish.package import build_package
from publish.source import SourceInfo, find_info_json, source_thumbnail_for
from translate.backend import TranslationBackend

from .models import PipelineResult
from .pipeline import translate_download
from .retry import RetryPolicy, retry

log = logging.getLogger("recreator.flow")

# Terminal statuses.
COMPLETED = "completed"
AWAITING_REVIEW = "awaiting_review"
DOWNLOAD_FAILED = "download_failed"
TRANSLATE_FAILED = "translate_failed"
COMPOSE_FAILED = "compose_failed"
PUBLISH_FAILED = "publish_failed"


def _timed(name, thunk):
    """Log a stage notice + elapsed time around a stage call."""
    log.info("▶ %s …", name)
    started = time.monotonic()
    result = thunk()
    ok = getattr(result, "ok", True)
    log.info("%s %s (%.1fs)", "✓" if ok else "✗", name, time.monotonic() - started)
    return result


@dataclass(frozen=True, slots=True)
class FlowResult:
    url: str
    status: str
    download: DownloadResult | None = None
    translation: PipelineResult | None = None
    compose: ComposeResult | None = None
    publish: PublishPackage | None = None
    data_recorded: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in (COMPLETED, AWAITING_REVIEW)


def _source_record(info: VideoInfo) -> SourceRecord:
    return SourceRecord(
        source_id=info.id, url=info.url, title=info.title, channel=info.channel,
        uploader=info.channel, upload_date=info.upload_date,
        duration_s=info.duration_s, view_count=info.view_count,
        like_count=info.like_count,
    )


def run_full(
    url: str,
    *,
    backend: TranslationBackend,
    metadata_backend=None,
    transcriber=None,
    policy: RetryPolicy = RetryPolicy(),
    output_dir: str = "output",
    store=None,
    stop_after: str | None = None,
    download_kwargs: dict | None = None,
    sleep=None,
) -> FlowResult:
    """Run a video end to end. Never raises — failures land in FlowResult."""
    retry_kw = {"sleep": sleep} if sleep is not None else {}
    log.info("processing %s", url)

    # 1. Download
    dl: DownloadResult = _timed("download", lambda: retry(
        lambda: download_one(
            url, on_progress=obs.make_progress("  download", log),
            **(download_kwargs or {}),
        ),
        policy, success=lambda r: r.ok, **retry_kw,
    ))
    if not dl.ok:
        return FlowResult(url, DOWNLOAD_FAILED, download=dl, error=dl.error)

    # Record source metrics (best-effort; never blocks the flow).
    data_recorded = False
    if store is not None and dl.info is not None:
        try:
            store.record_source(_source_record(dl.info))
            data_recorded = True
            log.debug("recorded source metrics for %s", dl.info.id)
        except Exception:
            data_recorded = False

    # 2. Translate (transcribes the audio first when no caption was downloaded)
    tr: PipelineResult = _timed("translate", lambda: retry(
        lambda: translate_download(
            dl, backend, on_progress=obs.make_progress("  translate", log),
            transcriber=transcriber,
            asr_progress=obs.make_progress("  transcribe", log),
        ),
        policy, success=lambda r: r.ok, **retry_kw,
    ))
    if not tr.ok:
        return FlowResult(url, TRANSLATE_FAILED, download=dl, translation=tr,
                          data_recorded=data_recorded, error=tr.error)
    if stop_after == "translate":  # respect the human review gate
        return FlowResult(url, AWAITING_REVIEW, download=dl, translation=tr,
                          data_recorded=data_recorded)

    # 3. Compose
    cmp: ComposeResult = _timed("compose", lambda: retry(
        lambda: compose(
            dl.video_path, tr.ass_path, output_dir=output_dir,
            on_progress=obs.make_progress("  compose", log),
        ),
        policy, success=lambda r: r.ok, **retry_kw,
    ))
    if not cmp.ok:
        return FlowResult(url, COMPOSE_FAILED, download=dl, translation=tr,
                          compose=cmp, data_recorded=data_recorded, error=cmp.error)
    if stop_after == "compose":
        return FlowResult(url, COMPLETED, download=dl, translation=tr,
                          compose=cmp, data_recorded=data_recorded)

    # 4. Publish (skipped when no metadata backend is supplied)
    pkg: PublishPackage | None = None
    if metadata_backend is not None:
        info_json = find_info_json(dl.subtitle_path, dl.video_path)
        source = SourceInfo.from_ytdlp_json(info_json) if info_json else None
        content = chinese_from_ass(tr.ass_path)
        pkg = _timed("publish", lambda: retry(
            lambda: build_package(
                cmp.out_path, content, backend=metadata_backend, source=source,
                thumbnail=source_thumbnail_for(info_json), cover_video=dl.video_path,
                output_dir=output_dir,
            ),
            policy, success=lambda r: r.ok, **retry_kw,
        ))
        if not pkg.ok:
            return FlowResult(url, PUBLISH_FAILED, download=dl, translation=tr,
                              compose=cmp, publish=pkg, data_recorded=data_recorded,
                              error=pkg.error)

    return FlowResult(url, COMPLETED, download=dl, translation=tr, compose=cmp,
                      publish=pkg, data_recorded=data_recorded)
