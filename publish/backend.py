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
    """Resolve a metadata backend by name (defaults to Claude)."""
    key = (name or "claude").strip().lower()
    if key == "claude":
        from .claude_backend import ClaudeMetadataBackend

        return ClaudeMetadataBackend()
    # Future: "local" -> a local-LLM implementation of the same protocol.
    raise ValueError(f"unknown metadata backend: {name!r}")
