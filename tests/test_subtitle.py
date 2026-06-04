"""Tests for subtitle loading and chunking."""

from __future__ import annotations

import pytest

from translate.models import Cue
from translate.subtitle import chunk_cues, dedupe_rolling, load_cues


def test_load_cues_parses_and_drops_blank(sample_srt):
    cues = load_cues(sample_srt)

    assert [c.text for c in cues] == ["Hello world", "Third line"]
    # Indices are stable to the kept cues (0-based, contiguous).
    assert [c.index for c in cues] == [0, 1]
    assert cues[0].start_ms == 1000


def test_dedupe_rolling_collapses_youtube_auto_captions():
    # Classic rolling format: each cue repeats the prior line + one new line,
    # interleaved with tiny transitional cues.
    rolling = [
        Cue(0, 0, 1590, "Look, be honest"),
        Cue(1, 1590, 1600, "Look, be honest\n "),
        Cue(2, 1600, 3670, "Look, be honest\nsecond, you have a drawer"),
        Cue(3, 3670, 3680, "second, you have a drawer\n "),
        Cue(4, 3680, 6470, "second, you have a drawer\nthere's a cable"),
    ]
    out = dedupe_rolling(rolling)

    assert [c.text for c in out] == [
        "Look, be honest",
        "second, you have a drawer",
        "there's a cable",
    ]
    # Re-timed sequentially with no overlaps.
    assert out[0].start_ms == 0 and out[0].end_ms == 1600
    assert out[1].start_ms == 1600 and out[1].end_ms == 3680
    assert all(out[i].end_ms <= out[i + 1].start_ms for i in range(len(out) - 1))


def test_dedupe_rolling_is_noop_for_clean_subtitles():
    clean = [Cue(0, 0, 1000, "one"), Cue(1, 1000, 2000, "two")]
    out = dedupe_rolling(clean)
    assert [c.text for c in out] == ["one", "two"]


def test_load_cues_no_clean_keeps_raw_lines(sample_srt):
    cues = load_cues(sample_srt, clean=False)
    assert [c.text for c in cues] == ["Hello world", "Third line"]


def _cues(n: int) -> list[Cue]:
    return [Cue(index=i, start_ms=i * 1000, end_ms=i * 1000 + 500, text=f"l{i}") for i in range(n)]


def test_chunk_cues_covers_all_cues_once():
    cues = _cues(100)
    chunks = chunk_cues(cues, chunk_size=40, overlap=2)

    flat = [c for ch in chunks for c in ch.cues]
    assert flat == cues  # every cue appears exactly once, in order
    assert len(chunks) == 3  # 40 + 40 + 20


def test_chunk_overlap_provides_context_without_retranslation():
    cues = _cues(10)
    chunks = chunk_cues(cues, chunk_size=4, overlap=2)

    # Second chunk translates cues 4..7, with 2 lead + 2 trail as context.
    second = chunks[1]
    assert [c.text for c in second.cues] == ["l4", "l5", "l6", "l7"]
    assert [c.text for c in second.lead] == ["l2", "l3"]
    assert [c.text for c in second.trail] == ["l8", "l9"]
    # Context is surrounding cues only (lead + trail), never the cues themselves.
    assert second.context.splitlines() == ["l2", "l3", "l8", "l9"]


def test_first_chunk_has_no_lead():
    chunks = chunk_cues(_cues(10), chunk_size=4, overlap=2)
    assert chunks[0].lead == ()


def test_chunk_cues_rejects_bad_params():
    with pytest.raises(ValueError):
        chunk_cues(_cues(3), chunk_size=0)
    with pytest.raises(ValueError):
        chunk_cues(_cues(3), overlap=-1)
