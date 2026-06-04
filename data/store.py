"""SQLite-backed repository for source and upload metric snapshots."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Comparison, SourceRecord, UploadRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id     TEXT NOT NULL,
    url           TEXT,
    title         TEXT,
    channel       TEXT,
    uploader      TEXT,
    upload_date   TEXT,
    duration_s    INTEGER,
    view_count    INTEGER,
    like_count    INTEGER,
    comment_count INTEGER,
    captured_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sources_sid ON sources(source_id, captured_at);

CREATE TABLE IF NOT EXISTS uploads (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id     TEXT NOT NULL,
    platform      TEXT NOT NULL,
    url           TEXT,
    title         TEXT,
    view_count    INTEGER,
    like_count    INTEGER,
    comment_count INTEGER,
    captured_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_uploads_sid ON uploads(source_id, captured_at);
"""

_SOURCE_COLS = (
    "source_id, url, title, channel, uploader, upload_date, "
    "duration_s, view_count, like_count, comment_count, captured_at"
)
_UPLOAD_COLS = (
    "source_id, platform, url, title, view_count, like_count, comment_count, captured_at"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DataStore:
    """Append-only metrics store. Use as a context manager or call close()."""

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        if self.path.parent and str(self.path.parent) not in ("", "."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # -- writes ---------------------------------------------------------------

    def record_source(self, rec: SourceRecord) -> int:
        captured = rec.captured_at or _now()
        cur = self.conn.execute(
            f"INSERT INTO sources ({_SOURCE_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                rec.source_id, rec.url, rec.title, rec.channel, rec.uploader,
                rec.upload_date, rec.duration_s, rec.view_count, rec.like_count,
                rec.comment_count, captured,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def record_upload(self, rec: UploadRecord) -> int:
        captured = rec.captured_at or _now()
        cur = self.conn.execute(
            f"INSERT INTO uploads ({_UPLOAD_COLS}) VALUES (?,?,?,?,?,?,?,?)",
            (
                rec.source_id, rec.platform, rec.url, rec.title, rec.view_count,
                rec.like_count, rec.comment_count, captured,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    # -- reads ----------------------------------------------------------------

    def latest_source(self, source_id: str) -> SourceRecord | None:
        row = self.conn.execute(
            "SELECT * FROM sources WHERE source_id=? ORDER BY captured_at DESC, id DESC LIMIT 1",
            (source_id,),
        ).fetchone()
        return _to_source(row) if row else None

    def latest_upload(self, source_id: str) -> UploadRecord | None:
        row = self.conn.execute(
            "SELECT * FROM uploads WHERE source_id=? ORDER BY captured_at DESC, id DESC LIMIT 1",
            (source_id,),
        ).fetchone()
        return _to_upload(row) if row else None

    def list_sources(self) -> list[SourceRecord]:
        """Latest snapshot per distinct source video, newest first."""
        rows = self.conn.execute(
            "SELECT * FROM sources s1 WHERE id = ("
            "  SELECT id FROM sources s2 WHERE s2.source_id = s1.source_id"
            "  ORDER BY captured_at DESC, id DESC LIMIT 1"
            ") ORDER BY captured_at DESC, id DESC"
        ).fetchall()
        return [_to_source(r) for r in rows]

    def comparison(self, source_id: str) -> Comparison:
        return Comparison(
            source_id=source_id,
            source=self.latest_source(source_id),
            upload=self.latest_upload(source_id),
        )

    # -- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "DataStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _to_source(row: sqlite3.Row) -> SourceRecord:
    return SourceRecord(
        source_id=row["source_id"], url=row["url"], title=row["title"],
        channel=row["channel"], uploader=row["uploader"], upload_date=row["upload_date"],
        duration_s=row["duration_s"], view_count=row["view_count"],
        like_count=row["like_count"], comment_count=row["comment_count"],
        captured_at=row["captured_at"],
    )


def _to_upload(row: sqlite3.Row) -> UploadRecord:
    return UploadRecord(
        source_id=row["source_id"], platform=row["platform"], url=row["url"],
        title=row["title"], view_count=row["view_count"], like_count=row["like_count"],
        comment_count=row["comment_count"], captured_at=row["captured_at"],
    )
