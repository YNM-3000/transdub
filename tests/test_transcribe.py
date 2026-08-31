"""Transcribe package tests using a fake transcriber (no Whisper, no ffmpeg)."""

from __future__ import annotations

import pysubs2
import pytest

from transcribe.models import Segment
from transcribe.pipeline import ensure_subtitle
from transcribe.srt import write_srt


class FakeTranscriber:
    def __init__(self, segments, progress_sink=None):
        self.segments = segments
        self.progress_sink = progress_sink

    def transcribe(self, media_path, *, on_progress=None):
        if on_progress and self.progress_sink is not None:
            for p in self.progress_sink:
                on_progress(p)
        return self.segments


def test_write_srt_roundtrips(tmp_path):
    out = write_srt(
        [Segment(0.0, 1.5, "Hello"), Segment(1.5, 3.0, "  World  ")],
        tmp_path / "sub" / "x.srt",
    )
    assert out.is_file()
    subs = pysubs2.load(str(out))
    assert len(subs) == 2
    assert subs[0].text == "Hello"
    assert subs[1].text == "World"  # trimmed
    assert subs[0].start == 0 and subs[0].end == 1500


def test_write_srt_drops_blank_and_raises_when_empty(tmp_path):
    with pytest.raises(ValueError):
        write_srt([Segment(0.0, 1.0, "   ")], tmp_path / "empty.srt")


def test_ensure_subtitle_writes_next_to_video(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    seen: list[int] = []
    asr = FakeTranscriber([Segment(0.0, 1.0, "hi")], progress_sink=[50, 100])

    out = ensure_subtitle(video, asr, on_progress=seen.append)

    assert out == tmp_path / "clip.en.srt"
    assert out.is_file()
    assert seen == [50, 100]
