"""Scan watched channels and produce alerts for new / trending videos."""

from __future__ import annotations

from dataclasses import replace

from .models import NEW, TRENDING, Alert, WatchConfig
from .state import SeenStore


def scan(config: WatchConfig, client, state: SeenStore, *, now: str | None = None) -> list[Alert]:
    """Inspect recent uploads per channel and return alerts.

    - A video unseen before its caption-filtered first sighting → NEW.
    - A video whose views cross its category threshold (once) → TRENDING.
    - Videos without captions are skipped (current-stage rule).
    """
    alerts: list[Alert] = []
    for category in config.categories:
        for channel in category.channels:
            for video in client.recent_videos(channel.id, config.scan_limit):
                video = replace(video, category=category.name)
                if not video.has_captions:
                    continue

                if not state.is_seen(video.video_id):
                    state.mark_seen(video, now)
                    alerts.append(Alert(video, NEW))

                views = video.view_count or 0
                if views >= category.min_trending_views and not state.is_trending_notified(
                    video.video_id
                ):
                    state.mark_trending(video.video_id, now)
                    alerts.append(Alert(video, TRENDING))
    return alerts
