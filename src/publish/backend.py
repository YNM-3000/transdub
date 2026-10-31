"""Pluggable metadata-generation backend.

Mirrors translate's backend design: callers depend on the `MetadataBackend`
protocol so Claude can later be swapped for a local LLM without changes here.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from .models import PublishMetadata

log = logging.getLogger("transdub.publish")


@runtime_checkable
class MetadataBackend(Protocol):
    """Generates Chinese title / description / tags from video content."""

    def generate(self, source_title: str, content: str) -> PublishMetadata: ...


class FallbackMetadataBackend:
    """Try a primary metadata backend, fall back to a secondary on failure."""

    def __init__(self, primary: MetadataBackend, make_secondary) -> None:
        self._primary = primary
        self._make_secondary = make_secondary
        self._secondary: MetadataBackend | None = None
        self._used = "primary"

    def generate(self, source_title: str, content: str) -> PublishMetadata:
        try:
            meta = self._primary.generate(source_title, content)
            self._used = "primary"
            return meta
        except Exception as err:
            log.warning("publish: primary backend failed (%s); falling back", err)
            if self._secondary is None:
                self._secondary = self._make_secondary()
            self._used = "secondary"
            return self._secondary.generate(source_title, content)

    def describe(self) -> str:
        from translate.backend import describe_backend

        chosen = self._secondary if self._used == "secondary" else self._primary
        return describe_backend(chosen)


def get_metadata_backend(name: str) -> MetadataBackend:
    """Resolve a metadata backend by name.

    "auto" (default) prefers a local Ollama model and falls back to Claude,
    mirroring the translation stage. "ollama"/"local" and "claude" force one.
    Metadata generation needs a chat model, so translation-only engine names
    (google, hunyuan, …) resolve to "auto" rather than erroring — the publish
    stage shares the `--backend` flag but has no MT equivalent.
    """
    key = (name or "auto").strip().lower()

    if key == "claude":
        from .claude_backend import ClaudeMetadataBackend

        return ClaudeMetadataBackend()

    if key in ("ollama", "local"):
        from .ollama_backend import OllamaMetadataBackend

        return OllamaMetadataBackend()

    if key not in ("auto", "claude", "ollama", "local"):
        log.info("publish: no metadata backend for %r; using auto", key)
        key = "auto"

    if key == "auto":
        from translate.ollama_backend import ollama_available

        from .claude_backend import ClaudeMetadataBackend
        from .ollama_backend import OllamaMetadataBackend, publish_model

        model = publish_model()
        if ollama_available(model=model):
            log.info("publish: Ollama %s (Claude fallback) metadata backend", model)
            return FallbackMetadataBackend(OllamaMetadataBackend(), make_secondary=ClaudeMetadataBackend)

        log.info("publish: %s unavailable, using Claude metadata backend", model)
        return ClaudeMetadataBackend()

    raise ValueError(f"unknown metadata backend: {name!r}")
