"""Pluggable translation backend.

The pipeline depends only on the `TranslationBackend` Protocol, so swapping
Claude for a local LLM (Ollama/vLLM/OpenAI-compatible) later requires no
changes to `pipeline.py` or `cli.py` — only a new implementation registered
in `get_backend`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


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


def get_backend(name: str) -> TranslationBackend:
    """Resolve a backend by name. Defaults route here from config/CLI/env."""
    key = (name or "claude").strip().lower()
    if key == "claude":
        from .claude_backend import ClaudeBackend

        return ClaudeBackend()
    # Future: "local" -> LocalBackend (Ollama/vLLM/OpenAI-compatible)
    raise ValueError(f"unknown translation backend: {name!r}")
