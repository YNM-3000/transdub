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

# Sentence-merge tuning. Auto-captions arrive as ~2s fragments chopped
# mid-sentence (and usually carry no punctuation), which makes local models
# drop/repeat lines when asked to translate each slice. Merging fragments into
# whole thoughts gives coherent, count-stable units. A unit is flushed on
# terminal punctuation, a speech pause, or a size cap — whichever comes first.
_SENTENCE_ENDERS = ".?!。！？…"
MERGE_MAX_CHARS = 80       # keep a merged line short enough to still render
MERGE_MAX_MS = 10_000
MERGE_MAX_GAP_MS = 700     # a pause this long likely ends a clause/sentence


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


def merge_sentences(
    cues: list[Cue],
    *,
    max_chars: int = MERGE_MAX_CHARS,
    max_ms: int = MERGE_MAX_MS,
    max_gap_ms: int = MERGE_MAX_GAP_MS,
) -> list[Cue]:
    """Merge consecutive cues into sentence-sized units.

    Combines fragments until the text ends on sentence punctuation, a pause
    longer than `max_gap_ms` precedes the next cue, or a size cap is hit. The
    merged cue spans from the first fragment's start to the last's end, so it
    stays anchored to the picture. Translating these whole units (instead of
    mid-sentence slivers) is far more reliable for local models, and reads
    better as a subtitle. Re-indexes the result contiguously.
    """
    if not cues:
        return []

    merged: list[Cue] = []
    start = cues[0].start_ms
    end = cues[0].end_ms
    parts = [cues[0].text.strip()]

    def flush() -> None:
        text = " ".join(p for p in parts if p).strip()
        if text:
            merged.append(Cue(len(merged), start, max(end, start + 1), text))

    for prev, cur in zip(cues, cues[1:]):
        ends_sentence = bool(parts[-1]) and parts[-1][-1] in _SENTENCE_ENDERS
        paused = cur.start_ms - prev.end_ms > max_gap_ms
        would_overflow = (
            sum(len(p) for p in parts) + 1 + len(cur.text) > max_chars
            or cur.end_ms - start > max_ms
        )
        if ends_sentence or paused or would_overflow:
            flush()
            start, end, parts = cur.start_ms, cur.end_ms, [cur.text.strip()]
        else:
            parts.append(cur.text.strip())
            end = cur.end_ms
    flush()
    return merged


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
