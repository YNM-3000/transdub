"""Immutable data models for the downloader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class VideoInfo:
    """Source-video metadata captured at download time.

    Feeds the directory layout, the translation hand-off, and (later) the
    data stage that compares source vs. re-uploaded performance.
    """

    id: str
    title: str
    channel: str
    url: str
    upload_date: str | None = None  # YYYYMMDD as yt-dlp reports it
    view_count: int | None = None
    like_count: int | None = None
    duration_s: int | None = None


@dataclass(frozen=True, slots=True)
class DownloadResult:
    """Outcome of one download attempt."""

    url: str
    ok: bool
    video_path: Path | None = None
    subtitle_path: Path | None = None
    info: VideoInfo | None = None
    error: str | None = None
