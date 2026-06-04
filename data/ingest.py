"""Build source records from yt-dlp info.json sidecars."""

from __future__ import annotations

import json
from pathlib import Path

from .models import SourceRecord


def source_record_from_info_json(
    path: str | Path, captured_at: str | None = None
) -> SourceRecord:
    """Parse a yt-dlp info.json into a SourceRecord snapshot."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return SourceRecord(
        source_id=data.get("id") or "",
        url=data.get("webpage_url") or data.get("original_url"),
        title=data.get("title"),
        channel=data.get("channel"),
        uploader=data.get("uploader") or data.get("channel"),
        upload_date=data.get("upload_date"),
        duration_s=data.get("duration"),
        view_count=data.get("view_count"),
        like_count=data.get("like_count"),
        comment_count=data.get("comment_count"),
        captured_at=captured_at,
    )


def find_info_jsons(target: str | Path) -> list[Path]:
    """Resolve a file or directory into a list of info.json paths."""
    path = Path(target)
    if path.is_dir():
        return sorted(path.rglob("*.info.json"))
    return [path] if path.is_file() else []
