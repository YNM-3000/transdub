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


def test_translate_chunk_is_one_to_one_and_ordered():
    # The whole point: each cue maps to exactly one line, in order — always.
    table = {"hello": "你好", "world": "世界", "cat": "猫"}
    be = GoogleBackend(transport=lambda t: table[t], max_workers=3)
    assert be.translate_chunk(["hello", "world", "cat"], "ctx") == ["你好", "世界", "猫"]


def test_translate_chunk_preserves_count_even_with_blanks():
    be = GoogleBackend(transport=lambda t: "译", max_workers=1)
    out = be.translate_chunk(["a", "   ", "b"], "")
    assert out == ["译", "", "译"]   # blank stays blank, length preserved


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
