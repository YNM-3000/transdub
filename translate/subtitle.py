"""Subtitle loading and chunking, backed by pysubs2.

We never hand-roll subtitle parsing; pysubs2 handles SRT/VTT/ASS. This module
converts a loaded file into our immutable `Cue` list and splits it into
overlapping `Chunk`s for context-aware translation.
"""

from __future__ import annotations

from pathlib import Path

import pysubs2

from .models import Chunk, Cue

DEFAULT_CHUNK_SIZE = 40
DEFAULT_OVERLAP = 2


def load_cues(path: str | Path) -> list[Cue]:
    """Load a subtitle file into a list of immutable cues.

    Empty / whitespace-only cues are dropped so the backend never wastes a
    slot on them. `index` is the 0-based position among the *kept* cues
    (contiguous), not the original source event number.
    """
    subs = pysubs2.load(str(path))
    cues: list[Cue] = []
    for event in subs:
        text = event.plaintext.strip()
        if not text:
            continue
        cues.append(
            Cue(
                index=len(cues),
                start_ms=int(event.start),
                end_ms=int(event.end),
                text=text,
            )
        )
    return cues


def chunk_cues(
    cues: list[Cue],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Split cues into translation chunks with neighbouring context.

    Each chunk carries up to `overlap` cues before it as `lead` and after it
    as `trail`. Those neighbours are context only — they are not re-translated.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")

    chunks: list[Chunk] = []
    for start in range(0, len(cues), chunk_size):
        end = min(start + chunk_size, len(cues))
        lead = cues[max(0, start - overlap) : start]
        trail = cues[end : min(len(cues), end + overlap)]
        chunks.append(
            Chunk(
                cues=tuple(cues[start:end]),
                lead=tuple(lead),
                trail=tuple(trail),
            )
        )
    return chunks
