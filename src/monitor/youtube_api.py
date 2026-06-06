"""Thin YouTube Data API v3 client.

Uses the REST endpoints directly through an injectable transport so tests need
no network and no SDK. Quota per channel: channels.list (1) + playlistItems
.list (1) + videos.list (1).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Callable

from .models import VideoCandidate

API_BASE = "https://www.googleapis.com/youtube/v3"

Transport = Callable[[str, dict], dict]


def _urllib_transport(url: str, params: dict) -> dict:
    query = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{query}", timeout=30) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class YouTubeClient:
    """Minimal client for the calls the monitor needs."""

    def __init__(self, api_key: str, transport: Transport | None = None) -> None:
        self._key = api_key
        self._transport = transport or _urllib_transport

    def _get(self, endpoint: str, params: dict) -> dict:
        return self._transport(f"{API_BASE}/{endpoint}", {**params, "key": self._key})

    def uploads_playlist(self, channel_id: str) -> str | None:
        data = self._get("channels", {"part": "contentDetails", "id": channel_id})
        items = data.get("items") or []
        if not items:
            return None
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    def recent_video_ids(self, playlist_id: str, limit: int) -> list[str]:
        data = self._get(
            "playlistItems",
            {"part": "contentDetails", "playlistId": playlist_id, "maxResults": limit},
        )
        return [it["contentDetails"]["videoId"] for it in data.get("items", [])]

    def video_details(self, video_ids: list[str]) -> list[VideoCandidate]:
        if not video_ids:
            return []
        data = self._get(
            "videos",
            {"part": "snippet,statistics,contentDetails", "id": ",".join(video_ids)},
        )
        return [_to_candidate(it) for it in data.get("items", [])]

    def recent_videos(self, channel_id: str, limit: int) -> list[VideoCandidate]:
        playlist = self.uploads_playlist(channel_id)
        if not playlist:
            return []
        return self.video_details(self.recent_video_ids(playlist, limit))


def _to_candidate(item: dict) -> VideoCandidate:
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    details = item.get("contentDetails", {})
    return VideoCandidate(
        video_id=item.get("id", ""),
        title=snippet.get("title", ""),
        description=snippet.get("description", ""),
        channel_id=snippet.get("channelId", ""),
        channel=snippet.get("channelTitle", ""),
        published_at=snippet.get("publishedAt"),
        view_count=_int(stats.get("viewCount")),
        like_count=_int(stats.get("likeCount")),
        tags=tuple(snippet.get("tags") or ()),
        has_captions=details.get("caption") == "true",
    )
