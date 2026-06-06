"""Assemble the publish package: metadata JSON + cover, in the output tree."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from .backend import MetadataBackend
from .cover import (
    Runner,
    _default_runner,
    convert_thumbnail,
    cover_timestamp,
    extract_cover,
)
from .models import PublishMetadata, PublishPackage
from .source import SourceInfo, attribution_block, extract_repos

DEFAULT_OUTPUT_DIR = "output"


def mirrored_dir(video_path: Path, output_dir: str | Path) -> Path:
    """`output/<date>/<channel>` mirrored from the source video's location."""
    parts = video_path.parent.parts
    if parts and parts[0] == video_path.parent.anchor and video_path.parent.anchor:
        parts = parts[1:]  # drop filesystem root so the join stays relative
    mirror = Path(*parts[-2:]) if len(parts) >= 2 else Path()
    return Path(output_dir) / mirror


def _metadata_dict(
    metadata: PublishMetadata,
    source_title: str,
    source: SourceInfo | None,
    repos: tuple[str, ...],
) -> dict:
    data = {
        "title": metadata.title,
        "category": metadata.category,
        "description": metadata.description,
        "tags": list(metadata.tags),
        "source_title": source_title,
    }
    if repos:
        data["repos"] = list(repos)
    if source is not None and not source.is_empty():
        data["source"] = source.as_dict()
    return data


def _repos_block(repos: tuple[str, ...]) -> str:
    return "—— 相关项目 ——\n" + "\n".join(repos)


def build_package(
    video_path: str | Path,
    content: str,
    *,
    backend: MetadataBackend,
    source_title: str | None = None,
    source: SourceInfo | None = None,
    thumbnail: str | Path | None = None,
    cover_video: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    cover_at: float | None = None,
    runner: Runner = _default_runner,
) -> PublishPackage:
    """Generate metadata + cover for a video. Never raises — errors returned.

    Metadata is required; the cover is best-effort (a failure leaves
    `cover_path` None but still yields an ok package). When `source` is given,
    a deterministic attribution block is appended to the description.

    Cover source preference: `thumbnail` (the real platform thumbnail) →
    a frame from `cover_video` (the clean pre-burn source) → a frame from
    `video_path`.
    """
    video = Path(video_path)
    title = source_title or video.stem

    try:
        metadata = backend.generate(title, content)
    except Exception as err:
        return PublishPackage(video, ok=False, error=f"metadata: {err}")

    repos = extract_repos(source.description) if source else ()
    parts = [metadata.description]
    if repos:
        parts.append(_repos_block(repos))
    if source is not None and not source.is_empty():
        parts.append(attribution_block(source))
    if len(parts) > 1:
        metadata = replace(metadata, description="\n\n".join(p for p in parts if p))

    out_dir = mirrored_dir(video, output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    meta_path = out_dir / f"{video.stem}.metadata.json"
    meta_path.write_text(
        json.dumps(_metadata_dict(metadata, title, source, repos), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    cover_path: Path | None = out_dir / f"{video.stem}.cover.jpg"
    ok = False
    if thumbnail and Path(thumbnail).is_file():
        ok, _err = convert_thumbnail(Path(thumbnail), cover_path, runner)
    if not ok:  # no usable thumbnail — fall back to a frame grab
        cover_src = Path(cover_video) if cover_video and Path(cover_video).is_file() else video
        ts = cover_timestamp(cover_src, cover_at, runner)
        ok, _err = extract_cover(cover_src, cover_path, ts, runner)
    if not ok:
        cover_path = None

    return PublishPackage(
        video,
        ok=True,
        metadata=metadata,
        metadata_path=meta_path,
        cover_path=cover_path,
    )
