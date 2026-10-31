"""Tests for the Google online-translate backend (no network)."""

from __future__ import annotations

import pytest

from translate.google_backend import GoogleBackend, _extract


def test_extract_joins_segments():
    # Shape of translate_a/single: [[["你好","hello",...],["世界","world",...]], ...]
    data = [[["你好", "hello", None, None, 10], ["世界", "world", None, None, 3]], None, "en"]
    assert _extract(data) == "你好世界"


def test_extract_handles_empty():
    assert _extract([None]) == ""


# transport now receives a newline-joined BATCH; translate line by line.
def _batch_transport(table):
    return lambda text: "\n".join(table[t] for t in text.split("\n"))


def test_translate_chunk_is_one_to_one_and_ordered():
    # The whole point: each cue maps to exactly one line, in order — always.
    table = {"hello": "你好", "world": "世界", "cat": "猫"}
    be = GoogleBackend(transport=_batch_transport(table), max_workers=3)
    assert be.translate_chunk(["hello", "world", "cat"], "ctx") == ["你好", "世界", "猫"]


def test_translate_chunk_batches_into_one_request():
    calls = {"n": 0}

    def transport(text):
        calls["n"] += 1
        return "\n".join("译" for _ in text.split("\n"))

    be = GoogleBackend(transport=transport, max_workers=4)
    out = be.translate_chunk(["a", "b", "c", "d"], "")
    assert out == ["译"] * 4
    assert calls["n"] == 1  # all four cues sent in a single batched request


def test_translate_chunk_preserves_count_even_with_blanks():
    be = GoogleBackend(transport=_batch_transport({"a": "译", "b": "译"}), max_workers=1)
    out = be.translate_chunk(["a", "   ", "b"], "")
    assert out == ["译", "", "译"]   # blank stays blank, length preserved


def test_batch_mismatch_falls_back_to_per_cue():
    # If the batched response has the wrong line count, each cue is retried alone.
    def transport(text):
        if "\n" in text:
            return "只有一行"            # bad: one line for a multi-line batch
        return {"a": "甲", "b": "乙"}[text]
    be = GoogleBackend(transport=transport, max_workers=1)
    assert be.translate_chunk(["a", "b"], "") == ["甲", "乙"]


def test_translate_retries_then_raises(monkeypatch):
    calls = {"n": 0}

    def flaky(_t):
        calls["n"] += 1
        raise RuntimeError("429")

    be = GoogleBackend(transport=flaky, max_retries=3, sleep=lambda _s: None, max_workers=1)
    with pytest.raises(RuntimeError, match="google translate failed"):
        be.translate_chunk(["x"], "")
    assert calls["n"] == 3  # retried up to the limit


def test_get_backend_resolves_google():
    from translate.backend import get_backend

    assert isinstance(get_backend("google"), GoogleBackend)
