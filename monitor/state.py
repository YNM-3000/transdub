"""SQLite state tracking which videos have been seen / trending-notified."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import VideoCandidate

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_videos (
    video_id             TEXT PRIMARY KEY,
    channel_id           TEXT,
    category             TEXT,
    title                TEXT,
    view_count           INTEGER,
    first_seen_at        TEXT NOT NULL,
    trending_notified_at TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SeenStore:
    """Remembers seen videos so only genuinely new ones alert."""

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        if str(self.path.parent) not in ("", "."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def is_seen(self, video_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen_videos WHERE video_id=?", (video_id,)
        ).fetchone()
        return row is not None

    def mark_seen(self, candidate: VideoCandidate, seen_at: str | None = None) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO seen_videos "
            "(video_id, channel_id, category, title, view_count, first_seen_at) "
            "VALUES (?,?,?,?,?,?)",
            (
                candidate.video_id, candidate.channel_id, candidate.category,
                candidate.title, candidate.view_count, seen_at or _now(),
            ),
        )
        self.conn.commit()

    def is_trending_notified(self, video_id: str) -> bool:
        row = self.conn.execute(
            "SELECT trending_notified_at FROM seen_videos WHERE video_id=?", (video_id,)
        ).fetchone()
        return bool(row and row["trending_notified_at"])

    def mark_trending(self, video_id: str, when: str | None = None) -> None:
        self.conn.execute(
            "UPDATE seen_videos SET trending_notified_at=? WHERE video_id=?",
            (when or _now(), video_id),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "SeenStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
