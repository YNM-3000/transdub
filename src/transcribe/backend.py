"""Transcriber abstraction + factory.

Mirrors the translate/publish backends: callers depend only on the Protocol,
so the Whisper engine can be swapped (or faked in tests) with no changes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Protocol

from .models import Segment

ProgressFn = Callable[[int], None]


class Transcriber(Protocol):
    def transcribe(
        self, media_path: str | Path, *, on_progress: ProgressFn | None = None
    ) -> list[Segment]:
        """Transcribe the audio of `media_path` into timed segments."""
        ...


def get_transcriber(
    model: str | None = None,
    device: str | None = None,
    compute_type: str | None = None,
    language: str | None = "en",
) -> Transcriber | None:
    """Build the default Whisper transcriber.

    Returns None when faster-whisper isn't installed, so the caller can warn
    and fall back to skipping caption-less videos rather than crashing. Model /
    device / compute default from the environment (WHISPER_MODEL etc.).
    """
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return None

    from .whisper_backend import WhisperBackend

    return WhisperBackend(
        model=model or os.environ.get("WHISPER_MODEL", "small"),
        device=device or os.environ.get("WHISPER_DEVICE", "cpu"),
        compute_type=compute_type or os.environ.get("WHISPER_COMPUTE", "int8"),
        language=language,
    )
