"""Produce a subtitle from a media file when no caption track was downloaded."""

from __future__ import annotations

from pathlib import Path

from .backend import ProgressFn, Transcriber
from .srt import write_srt


def ensure_subtitle(
    video_path: str | Path,
    transcriber: Transcriber,
    *,
    on_progress: ProgressFn | None = None,
) -> Path:
    """Transcribe `video_path` and write an English SRT next to it.

    The SRT is named `<video>.en.srt` so it blends in with a yt-dlp-downloaded
    caption and is picked up by the same downstream stages.
    """
    video = Path(video_path)
    segments = transcriber.transcribe(video, on_progress=on_progress)
    out = video.with_suffix(".en.srt")
    return write_srt(segments, out)
