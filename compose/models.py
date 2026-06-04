"""Immutable result model for the compose stage."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

BURN = "burn"  # hard subtitles rendered into the frames (mp4)
SOFT = "soft"  # selectable ASS subtitle track (mkv)

AAC = "aac"  # transcode audio to AAC (broad platform compatibility)
COPY = "copy"  # passthrough the source audio stream as-is


@dataclass(frozen=True, slots=True)
class ComposeResult:
    """Outcome of composing a final video."""

    video_path: Path
    subtitle_path: Path
    out_path: Path
    mode: str
    ok: bool
    error: str | None = None
