"""Source-video attribution from the yt-dlp info.json sidecar."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# Repo URLs on the common git hosts (owner/repo), scheme required.
_REPO = re.compile(
    r"https?://(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org)"
    r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SourceInfo:
    """Original-video attribution fields."""

    url: str | None = None
    title: str | None = None
    uploader: str | None = None
    upload_date: str | None = None  # YYYYMMDD as yt-dlp reports it
    description: str | None = None

    @classmethod
    def from_ytdlp_json(cls, path: str | Path) -> "SourceInfo":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            url=data.get("webpage_url") or data.get("original_url"),
            title=data.get("title"),
            uploader=data.get("uploader") or data.get("channel"),
            upload_date=data.get("upload_date"),
            description=data.get("description"),
        )

    def is_empty(self) -> bool:
        return not any((self.url, self.title, self.uploader, self.upload_date))

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "uploader": self.uploader,
            "upload_date": self.upload_date,
        }


def extract_repos(text: str | None) -> tuple[str, ...]:
    """Pull git-repo URLs from free text, de-duplicated, order preserved."""
    if not text:
        return ()
    seen: list[str] = []
    for match in _REPO.finditer(text):
        url = match.group(0).rstrip(".,);]")
        if url not in seen:
            seen.append(url)
    return tuple(seen)


def _format_date(value: str | None) -> str | None:
    if value and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def attribution_block(source: SourceInfo) -> str:
    """A Chinese attribution block for the description (deterministic, exact)."""
    lines = ["—— 原视频信息 ——"]
    if source.title:
        lines.append(f"原标题：{source.title}")
    if source.uploader:
        lines.append(f"UP主：{source.uploader}")
    date = _format_date(source.upload_date)
    if date:
        lines.append(f"发布日期：{date}")
    if source.url:
        lines.append(f"原链接：{source.url}")
    return "\n".join(lines)


_VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".mov")
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def _sibling_with_ext(info_json: str | Path | None, exts: tuple[str, ...]) -> Path | None:
    """Find a same-stemmed sibling of the info.json with one of `exts`."""
    if not info_json:
        return None
    info = Path(info_json)
    base = info.name[: -len(".info.json")]
    for ext in exts:
        candidate = info.parent / f"{base}{ext}"
        if candidate.is_file():
            return candidate
    return None


def source_video_for(info_json: str | Path | None) -> Path | None:
    """Locate the clean source video sitting beside its info.json.

    yt-dlp writes `<title>.info.json` next to `<title>.mp4`, so the original
    (pre-burn) video is the same-stemmed sibling — the right source for a cover
    frame without burned-in subtitles.
    """
    return _sibling_with_ext(info_json, _VIDEO_EXTS)


def source_thumbnail_for(info_json: str | Path | None) -> Path | None:
    """Locate the downloaded source thumbnail beside its info.json.

    yt-dlp's `--write-thumbnail` saves `<title>.jpg` next to the video — the
    real platform thumbnail, a better cover than an arbitrary frame.
    """
    return _sibling_with_ext(info_json, _IMAGE_EXTS)


def find_info_json(*candidates: str | Path | None) -> Path | None:
    """Locate a yt-dlp *.info.json near a subtitle/video file.

    Prefers an info.json whose stem prefixes the candidate's name (so it picks
    the right one when several videos share a directory); falls back to a lone
    info.json in the directory.
    """
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        folder = path.parent
        if not folder.is_dir():
            continue
        found = sorted(folder.glob("*.info.json"))
        for info in found:
            base = info.name[: -len(".info.json")]
            if path.name.startswith(base):
                return info
        if len(found) == 1:
            return found[0]
    return None
