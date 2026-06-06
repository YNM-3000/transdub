"""Immutable models for the publish stage."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PublishMetadata:
    """Chinese-platform metadata for a repurposed video."""

    title: str
    description: str
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PublishPackage:
    """The assembled upload package for one video."""

    video_path: Path
    ok: bool
    metadata: PublishMetadata | None = None
    metadata_path: Path | None = None
    cover_path: Path | None = None
    error: str | None = None
