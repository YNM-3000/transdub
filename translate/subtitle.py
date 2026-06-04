"""Subtitle loading and chunking, backed by pysubs2.

We never hand-roll subtitle parsing; pysubs2 handles SRT/VTT/ASS. This module
converts a loaded file into our immutable `Cue` list and splits it into
overlapping `Chunk`s for context-aware translation.
"""

from __future__ import annotations

from pathlib import Path

import pysubs2

from .models import Chunk, Cue

# Chunk size trades API calls against per-call output size (bounded by the
# model's max_tokens). 30 keeps calls low while staying well under the limit;
# overlap gives each chunk cross-cut context for coherent translation.
DEFAULT_CHUNK_SIZE = 30
DEFAULT_OVERLAP = 2


def load_cues(path: str | Path, clean: bool = True) -> list[Cue]:
    """Load a subtitle file into a list of immutable cues.

    Empty / whitespace-only cues are dropped so the backend never wastes a
    slot on them. `index` is the 0-based position among the *kept* cues
    (contiguous), not the original source event number.

    When `clean` is set (default), YouTube-style "rolling" auto-captions —
    where each cue repeats the previous line plus one new line — are collapsed
    into one clean line per distinct utterance. This is a no-op for subtitles
    that have no consecutive duplicate lines.
    """
    subs = pysubs2.load(str(path))
    raw = [
        Cue(index=i, start_ms=int(e.start), end_ms=int(e.end), text=e.plaintext)
        for i, e in enumerate(subs)
    ]
    if clean:
        return dedupe_rolling(raw)
    kept = [c for c in raw if c.text.strip()]
    return [
        Cue(index=i, start_ms=c.start_ms, end_ms=c.end_ms, text=c.text.strip())
        for i, c in enumerate(kept)
    ]


def dedupe_rolling(cues: list[Cue]) -> list[Cue]:
    """Collapse rolling auto-captions into one cue per distinct line.

    Each cue's text may hold several lines; a line is emitted only when it
    differs from the previously emitted line, which removes the carry-over
    duplication. Emitted lines are re-timed sequentially (each ends when the
    next begins) so the cleaned track has no overlaps.
    """
    emitted: list[Cue] = []
    last_line: str | None = None
    for cue in cues:
        for line in cue.text.split("\n"):
            line = line.strip()
            if not line or line == last_line:
                continue
            emitted.append(
                Cue(
                    index=len(emitted),
                    start_ms=cue.start_ms,
                    end_ms=cue.end_ms,
                    text=line,
                )
            )
            last_line = line

    result: list[Cue] = []
    for i, cue in enumerate(emitted):
        end = emitted[i + 1].start_ms if i + 1 < len(emitted) else cue.end_ms
        result.append(
            Cue(
                index=i,
                start_ms=cue.start_ms,
                end_ms=max(end, cue.start_ms + 1),
                text=cue.text,
            )
        )
    return result


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
