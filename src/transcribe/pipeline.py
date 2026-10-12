"""Produce a subtitle from a media file when no caption track was downloaded."""

from __future__ import annotations

import logging
from pathlib import Path

from .backend import ProgressFn, Transcriber
from .srt import write_srt

log = logging.getLogger("transdub.transcribe")


def ensure_subtitle(
    video_path: str | Path,
    transcriber: Transcriber,
    *,
    on_progress: ProgressFn | None = None,
) -> Path:
    """Transcribe `video_path` and write an English SRT next to it.

    The SRT is named `<video>.en.srt` so it blends in with a yt-dlp-downloaded
    caption and is picked up by the same downstream stages. Idempotent: if that
    SRT already exists and is non-empty it is reused, so a translate-stage retry
    never re-runs the (slow) transcription.
    """
    video = Path(video_path)
    out = video.with_suffix(".en.srt")
    if out.is_file() and out.stat().st_size > 0:
        log.info("transcribe: reusing existing %s", out.name)
        return out

    segments = transcriber.transcribe(video, on_progress=on_progress)
    return write_srt(segments, out)
