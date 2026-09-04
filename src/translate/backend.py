"""Pluggable translation backend.

The pipeline depends only on the `TranslationBackend` Protocol, so swapping
Claude for a local LLM (Ollama/vLLM/OpenAI-compatible) later requires no
changes to `pipeline.py` or `cli.py` — only a new implementation registered
in `get_backend`.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

log = logging.getLogger("recreator.translate")


@runtime_checkable
class TranslationBackend(Protocol):
    """Translates a list of source lines to Chinese.

    Contract:
    - returns a list of the SAME length as `cues`, in the same order
    - `context` is the surrounding text window (may include neighbouring
      cues) provided only to improve coherence; do not translate it
    """

    def translate_chunk(self, cues: list[str], context: str) -> list[str]: ...


class LengthMismatchError(RuntimeError):
    """Raised when a backend returns a different number of lines than asked."""

    def __init__(self, expected: int, got: int) -> None:
        super().__init__(f"expected {expected} translated lines, got {got}")
        self.expected = expected
        self.got = got


class FallbackBackend:
    """Try a primary backend per chunk; fall back to a secondary on failure.

    Implements "local first, cloud fallback": a local model handles most
    chunks for free, and the (lazily created) cloud backend rescues any chunk
    the local one flubs — e.g. dropping lines from a strict count.
    """

    def __init__(self, primary: "TranslationBackend", make_secondary) -> None:
        self._primary = primary
        self._make_secondary = make_secondary  # () -> TranslationBackend, lazy
        self._secondary: TranslationBackend | None = None
        self._primary_uses = 0
        self._secondary_uses = 0

    def translate_chunk(self, cues: list[str], context: str) -> list[str]:
        try:
            out = self._primary.translate_chunk(cues, context)
            self._primary_uses += 1
            return out
        except Exception as err:
            log.warning("translate: primary backend failed (%s); falling back", err)
            if self._secondary is None:
                self._secondary = self._make_secondary()
            out = self._secondary.translate_chunk(cues, context)
            self._secondary_uses += 1
            return out

    def describe(self) -> str:
        total = self._primary_uses + self._secondary_uses
        if total == 0:
            return describe_backend(self._primary)
        parts = [f"{describe_backend(self._primary)} ({self._primary_uses}/{total} chunks)"]
        if self._secondary_uses and self._secondary is not None:
            parts.append(f"{describe_backend(self._secondary)} ({self._secondary_uses}/{total})")
        return " + ".join(parts)


def describe_backend(backend: object) -> str:
    """Human label for a backend, e.g. 'local · ollama:llama3.1:8b'."""
    describe = getattr(backend, "describe", None)
    if callable(describe):
        return describe()
    return type(backend).__name__


def get_backend(name: str) -> TranslationBackend:
    """Resolve a translation backend by name.

    "auto" (the default) prefers a local Ollama model and falls back to Claude
    when Ollama isn't reachable — so translation runs locally/free when
    possible and still works out of the box otherwise. "ollama"/"local" and
    "claude" force a specific engine.
    """
    key = (name or "auto").strip().lower()

    if key == "claude":
        from .claude_backend import ClaudeBackend

        return ClaudeBackend()

    if key in ("ollama", "local"):
        from .ollama_backend import OllamaBackend

        return OllamaBackend()

    if key == "auto":
        import os

        from .claude_backend import ClaudeBackend
        from .ollama_backend import OllamaBackend, ollama_available

        if ollama_available(model=os.environ.get("OLLAMA_MODEL")):
            log.info("translate: local Ollama (Claude fallback) backend")
            return FallbackBackend(OllamaBackend(), make_secondary=ClaudeBackend)

        log.info("translate: Ollama unavailable, using Claude backend")
        return ClaudeBackend()

    raise ValueError(f"unknown translation backend: {name!r}")
