"""Voice backend abstraction + factory.

Callers depend only on `VoiceBackend`, so the engine (Kokoro local, edge-tts
online, or a fake in tests) is swappable. `get_voice_backend` prefers a local
Kokoro model when available and configured, and otherwise falls back to
edge-tts — per the chosen "Kokoro primary, edge fallback" policy.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Protocol

log = logging.getLogger("recreator.dub")

# Synthesized clips are normalized to this format for seamless concatenation.
SAMPLE_RATE = 24_000


class VoiceBackend(Protocol):
    name: str

    def synthesize(self, text: str, out_path: str | Path) -> None:
        """Write `text` as a mono WAV (SAMPLE_RATE) to `out_path`."""
        ...


def get_voice_backend(voice: str | None = None) -> VoiceBackend | None:
    """Build the preferred available voice backend, or None if none is usable.

    Order: Kokoro (local, offline) → edge-tts (online). `voice` overrides the
    default voice for whichever engine is chosen.
    """
    kokoro = _try_kokoro(voice)
    if kokoro is not None:
        log.info("dub: using Kokoro voice backend")
        return kokoro

    edge = _try_edge(voice)
    if edge is not None:
        log.info("dub: using edge-tts voice backend (Kokoro unavailable)")
        return edge

    return None


def _try_kokoro(voice: str | None):
    try:
        from .kokoro_backend import KokoroBackend
    except ImportError:
        return None
    try:
        return KokoroBackend(voice=voice or os.environ.get("KOKORO_VOICE", "zf_xiaobei"))
    except Exception as err:  # missing model files, etc.
        log.debug("dub: Kokoro unavailable: %s", err)
        return None


def _try_edge(voice: str | None):
    try:
        from .edge_backend import EdgeBackend
    except ImportError:
        return None
    return EdgeBackend(voice=voice or os.environ.get("DUB_VOICE", "zh-CN-XiaoxiaoNeural"))
