"""Immutable models for the monitor stage."""

from __future__ import annotations

from dataclasses import dataclass

NEW = "new"
TRENDING = "trending"


@dataclass(frozen=True, slots=True)
class ChannelRef:
    """A watched channel, tagged with its category."""

    id: str
    name: str = ""
    category: str = ""


@dataclass(frozen=True, slots=True)
class Category:
    """A category of channels plus its trending threshold."""

    name: str
    min_trending_views: int
    channels: tuple[ChannelRef, ...] = ()


@dataclass(frozen=True, slots=True)
class WatchConfig:
    """The full watchlist."""

    categories: tuple[Category, ...] = ()
    scan_limit: int = 5  # recent uploads to inspect per channel


@dataclass(frozen=True, slots=True)
class VideoCandidate:
    """A candidate video discovered during a scan."""

    video_id: str
    title: str
    description: str
    channel_id: str
    channel: str
    published_at: str | None = None
    view_count: int | None = None
    like_count: int | None = None
    tags: tuple[str, ...] = ()
    has_captions: bool = False
    category: str = ""

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


@dataclass(frozen=True, slots=True)
class Alert:
    """A reason to notify about a candidate."""

    candidate: VideoCandidate
    reason: str  # NEW | TRENDING
