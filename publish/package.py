"""Assemble the publish package: metadata JSON + cover, in the output tree."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from .backend import MetadataBackend
from .cover import Runner, _default_runner, cover_timestamp, extract_cover
from .models import PublishMetadata, PublishPackage
from .source import SourceInfo, attribution_block

DEFAULT_OUTPUT_DIR = "output"


def mirrored_dir(video_path: Path, output_dir: str | Path) -> Path:
    """`output/<date>/<channel>` mirrored from the source video's location."""
    parts = video_path.parent.parts
    if parts and parts[0] == video_path.parent.anchor and video_path.parent.anchor:
        parts = parts[1:]  # drop filesystem root so the join stays relative
    mirror = Path(*parts[-2:]) if len(parts) >= 2 else Path()
    return Path(output_dir) / mirror


def _metadata_dict(
    metadata: PublishMetadata, source_title: str, source: SourceInfo | None
) -> dict:
    data = {
        "title": metadata.title,
        "description": metadata.description,
        "tags": list(metadata.tags),
        "source_title": source_title,
    }
    if source is not None and not source.is_empty():
        data["source"] = source.as_dict()
    return data


def build_package(
    video_path: str | Path,
    content: str,
    *,
    backend: MetadataBackend,
    source_title: str | None = None,
    source: SourceInfo | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    cover_at: float | None = None,
    runner: Runner = _default_runner,
) -> PublishPackage:
    """Generate metadata + cover for a video. Never raises — errors returned.

    Metadata is required; the cover is best-effort (a failed extraction leaves
    `cover_path` None but still yields an ok package). When `source` is given,
    a deterministic attribution block is appended to the description.
    """
    video = Path(video_path)
    title = source_title or video.stem

    try:
        metadata = backend.generate(title, content)
    except Exception as err:
        return PublishPackage(video, ok=False, error=f"metadata: {err}")

    if source is not None and not source.is_empty():
        combined = f"{metadata.description}\n\n{attribution_block(source)}".strip()
        metadata = replace(metadata, description=combined)

    out_dir = mirrored_dir(video, output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    meta_path = out_dir / f"{video.stem}.metadata.json"
    meta_path.write_text(
        json.dumps(_metadata_dict(metadata, title, source), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    cover_path: Path | None = out_dir / f"{video.stem}.cover.jpg"
    ts = cover_timestamp(video, cover_at, runner)
    ok, _err = extract_cover(video, cover_path, ts, runner)
    if not ok:
        cover_path = None

    return PublishPackage(
        video,
        ok=True,
        metadata=metadata,
        metadata_path=meta_path,
        cover_path=cover_path,
    )
