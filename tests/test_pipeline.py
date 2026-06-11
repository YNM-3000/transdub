"""End-to-end pipeline tests using a fake backend (no API calls)."""

from __future__ import annotations

import pysubs2
import pytest

from translate.pipeline import translate_cues, translate_file


def test_translate_cues_preserves_order_and_count(sample_cues, fake_backend):
    out = translate_cues(sample_cues, fake_backend)
    assert out == ["译:Hello world", "译:Second line", "译:Third line"]


def test_translate_cues_reports_progress_per_chunk(sample_cues, fake_backend):
    seen: list[int] = []
    translate_cues(sample_cues, fake_backend, on_progress=seen.append)
    assert seen and seen[-1] == 100  # finishes at 100%
    assert seen == sorted(seen)  # monotonic


def test_translate_cues_raises_on_backend_length_mismatch(sample_cues):
    class BadBackend:
        def translate_chunk(self, cues, context):
            return cues[:-1]  # drops a line

    with pytest.raises(RuntimeError):
        translate_cues(sample_cues, BadBackend())


def test_translate_file_writes_bilingual_ass(sample_srt, tmp_path, fake_backend):
    out_path = tmp_path / "nested" / "demo.bilingual.ass"
    result = translate_file(sample_srt, out_path, fake_backend)

    assert result == out_path
    assert out_path.is_file()
    subs = pysubs2.load(str(out_path))
    assert len(subs) == 2  # blank cue dropped on load
    assert "译:Hello world" in subs[0].text


def test_translate_file_rejects_empty_subtitle(tmp_path, fake_backend):
    empty = tmp_path / "empty.srt"
    empty.write_text("1\n00:00:01,000 --> 00:00:02,000\n   \n", encoding="utf-8")
    with pytest.raises(ValueError):
        translate_file(empty, tmp_path / "o.ass", fake_backend)
