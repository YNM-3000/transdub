"""Cover-frame extraction via ffmpeg/ffprobe."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
FALLBACK_COVER_SECONDS = 10.0
COVER_FRACTION = 0.3  # grab a frame ~30% into the video by default

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def _default_runner(cmd: list[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(cmd, capture_output=True, text=True)


def probe_duration(video: Path, runner: Runner = _default_runner) -> float | None:
    """Return the video duration in seconds, or None if it can't be read."""
    cmd = [
        FFPROBE, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1",
        str(video),
    ]
    try:
        proc = runner(cmd)
        return float(proc.stdout.strip())
    except Exception:
        return None


def cover_timestamp(
    video: Path,
    at_seconds: float | None,
    runner: Runner = _default_runner,
) -> float:
    """Pick the cover timestamp: explicit value, else a fraction of duration."""
    if at_seconds is not None:
        return max(0.0, at_seconds)
    duration = probe_duration(video, runner)
    return duration * COVER_FRACTION if duration else FALLBACK_COVER_SECONDS


def convert_thumbnail(
    thumbnail: Path,
    out_path: Path,
    runner: Runner = _default_runner,
) -> tuple[bool, str | None]:
    """Convert an existing thumbnail image to the cover JPEG."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [FFMPEG, "-y", "-i", str(thumbnail), str(out_path)]
    try:
        proc = runner(cmd)
    except Exception as err:
        return False, str(err)
    if proc.returncode != 0:
        return False, (proc.stderr or "").strip()[-400:]
    return True, None


def extract_cover(
    video: Path,
    out_path: Path,
    at_seconds: float,
    runner: Runner = _default_runner,
) -> tuple[bool, str | None]:
    """Extract a single high-quality JPEG frame at `at_seconds`."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG, "-y",
        "-ss", str(at_seconds),
        "-i", str(video),
        "-frames:v", "1", "-q:v", "2",
        str(out_path),
    ]
    try:
        proc = runner(cmd)
    except Exception as err:
        return False, str(err)
    if proc.returncode != 0:
        return False, (proc.stderr or "").strip()[-400:]
    return True, None
