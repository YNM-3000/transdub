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
    out_path: str | Path | None = None,
) -> Path:
    """Transcribe `video_path` and write an English SRT.

    Defaults to `<video>.en.srt` (so it blends in with a yt-dlp caption and feeds
    the same downstream stages). Pass `out_path` to write elsewhere — e.g.
    `<video>.whisper.srt` when forcing Whisper on a video that *also* has a
    downloaded auto-caption, so the two don't collide. Idempotent: an existing
    non-empty target is reused, so a translate retry never re-runs transcription.
    """
    video = Path(video_path)
    out = Path(out_path) if out_path else video.with_suffix(".en.srt")
    if out.is_file() and out.stat().st_size > 0:
        log.info("transcribe: reusing existing %s", out.name)
        return out

    segments = transcriber.transcribe(video, on_progress=on_progress)
    return write_srt(segments, out)
