"""Pluggable metadata-generation backend.

Mirrors translate's backend design: callers depend on the `MetadataBackend`
protocol so Claude can later be swapped for a local LLM without changes here.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import PublishMetadata


@runtime_checkable
class MetadataBackend(Protocol):
    """Generates Chinese title / description / tags from video content."""

    def generate(self, source_title: str, content: str) -> PublishMetadata: ...


def get_metadata_backend(name: str) -> MetadataBackend:
    """Resolve a metadata backend by name.

    Only Claude generates publish metadata for now, so "auto"/"local"/"ollama"
    all resolve to Claude here (the translation stage can still run locally).
    """
    key = (name or "claude").strip().lower()
    if key in ("claude", "auto", "local", "ollama"):
        from .claude_backend import ClaudeMetadataBackend

        return ClaudeMetadataBackend()
    raise ValueError(f"unknown metadata backend: {name!r}")
