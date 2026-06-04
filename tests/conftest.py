"""Shared fixtures and fakes for the translation tests."""

from __future__ import annotations

import pytest

from translate.models import Cue


class FakeBackend:
    """Deterministic backend that records calls and echoes a marker.

    Returns one '译:<line>' per input line so length and ordering are easy to
    assert without hitting any API.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str]] = []

    def translate_chunk(self, cues: list[str], context: str) -> list[str]:
        self.calls.append((list(cues), context))
        return [f"译:{line}" for line in cues]


@pytest.fixture
def fake_backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def sample_cues() -> list[Cue]:
    return [
        Cue(index=0, start_ms=1000, end_ms=3500, text="Hello world"),
        Cue(index=1, start_ms=3600, end_ms=6000, text="Second line"),
        Cue(index=2, start_ms=6200, end_ms=9000, text="Third line"),
    ]


@pytest.fixture
def sample_srt(tmp_path):
    content = (
        "1\n00:00:01,000 --> 00:00:03,500\nHello world\n\n"
        "2\n00:00:03,600 --> 00:00:06,000\n   \n\n"  # blank cue, should drop
        "3\n00:00:06,200 --> 00:00:09,000\nThird line\n"
    )
    path = tmp_path / "in.srt"
    path.write_text(content, encoding="utf-8")
    return path
