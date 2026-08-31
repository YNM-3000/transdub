"""Download → translate flow.

`translate_download` is the hand-off: given a finished download it triggers a
translation, writing the bilingual ASS next to the video. Parallel downloads
are reused from the download stage; translations run sequentially to keep API
usage predictable.
"""

from __future__ import annotations

import logging

from download.downloader import download_many, download_one
from download.models import DownloadResult
from transcribe.backend import Transcriber
from transcribe.pipeline import ensure_subtitle
from translate.backend import TranslationBackend
from translate.pipeline import translate_file

from .models import (
    DOWNLOAD_FAILED,
    NO_SUBTITLE,
    TRANSCRIBE_FAILED,
    TRANSLATE_FAILED,
    TRANSLATED,
    PipelineResult,
)

log = logging.getLogger("recreator.translate")


def translate_download(
    result: DownloadResult,
    backend: TranslationBackend,
    *,
    clean: bool = True,
    on_progress=None,
    transcriber: Transcriber | None = None,
    asr_progress=None,
) -> PipelineResult:
    """Trigger translation for a completed download.

    When no caption track was downloaded, fall back to transcribing the audio
    with `transcriber` (if supplied) so the video is still translatable. With
    no transcriber, a caption-less video is skipped rather than failed hard.
    """
    if not result.ok:
        return PipelineResult(result.url, DOWNLOAD_FAILED, result, error=result.error)

    subtitle = result.subtitle_path
    if subtitle is None:
        if transcriber is None or result.video_path is None:
            return PipelineResult(
                result.url, NO_SUBTITLE, result, error="no subtitle track"
            )
        log.info("no caption track; transcribing audio with Whisper …")
        try:
            subtitle = ensure_subtitle(
                result.video_path, transcriber, on_progress=asr_progress
            )
        except Exception as err:
            return PipelineResult(
                result.url, TRANSCRIBE_FAILED, result, error=str(err)
            )

    anchor = result.video_path or subtitle
    out_path = anchor.with_suffix(".bilingual.ass")
    try:
        ass = translate_file(
            subtitle, out_path, backend, clean=clean,
            on_progress=on_progress,
        )
    except Exception as err:
        return PipelineResult(result.url, TRANSLATE_FAILED, result, error=str(err))
    return PipelineResult(result.url, TRANSLATED, result, ass_path=ass)


def process_url(
    url: str,
    backend: TranslationBackend,
    *,
    clean: bool = True,
    **download_kwargs,
) -> PipelineResult:
    """Download one URL, then immediately translate it."""
    result = download_one(url, **download_kwargs)
    return translate_download(result, backend, clean=clean)


def process_urls(
    urls: list[str],
    backend: TranslationBackend,
    *,
    max_workers: int = 3,
    clean: bool = True,
    **download_kwargs,
) -> list[PipelineResult]:
    """Download all URLs in parallel, then translate each in order.

    Downloads are IO-bound and parallelised; translations are API-bound and
    run sequentially to avoid rate-limit storms.
    """
    downloads = download_many(urls, max_workers=max_workers, **download_kwargs)
    return [translate_download(d, backend, clean=clean) for d in downloads]
