"""Dub-stage tests: pure timeline/assread/naming logic (no TTS, no ffmpeg)."""

from __future__ import annotations

from pathlib import Path

import pysubs2

from dub.assread import chinese_cues
from dub.audio import default_dub_output
from dub.models import VoiceCue
from dub.timeline import plan_timeline, tempo_for


def _bilingual_ass(tmp_path):
    subs = pysubs2.SSAFile()
    subs.append(pysubs2.SSAEvent(start=0, end=2000, text=r"{\fs22}你好世界\N{\fs13}Hello world"))
    subs.append(pysubs2.SSAEvent(start=2000, end=4000, text=r"{\fs22}第二行\N{\fs13}Second line"))
    path = tmp_path / "b.ass"
    subs.save(str(path))
    return path


def test_chinese_cues_takes_first_line_and_strips_tags(tmp_path):
    cues = chinese_cues(_bilingual_ass(tmp_path))
    assert [c.text for c in cues] == ["你好世界", "第二行"]
    assert cues[0].start == 0.0 and cues[0].end == 2.0


def test_tempo_for_speeds_up_only_when_too_long():
    assert tempo_for(1.0, 2.0) == 1.0            # shorter than window → no change
    assert tempo_for(3.0, 2.0) == 1.5            # 3s into 2s → 1.5x
    assert tempo_for(10.0, 2.0, max_tempo=1.6) == 1.6  # capped
    assert tempo_for(1.0, 0.0) == 1.0            # degenerate window


def test_plan_timeline_places_clips_and_never_drifts():
    cues = [VoiceCue(0.0, 2.0, "a"), VoiceCue(5.0, 6.0, "b")]
    # clip 0 fits (1.5s <= 2s); clip 1 too long (2s into 1s → 1.6x cap)
    pieces = plan_timeline(cues, [1.5, 2.0])

    kinds = [(p.kind, round(p.seconds, 3)) for p in pieces]
    # cue0 at t=0 (no leading gap), then silence until t=5, then cue1
    assert kinds[0][0] == "clip"
    assert kinds[1] == ("silence", 3.5)          # 5.0 - 1.5 placed
    assert kinds[2][0] == "clip"
    assert pieces[2].tempo == 1.6                 # capped speed-up
    # running position stays anchored: last clip fitted = 2.0/1.6 = 1.25
    assert round(pieces[2].seconds, 3) == 1.25


def test_default_dub_output_is_sibling_variant():
    out = default_dub_output(Path("output/x/Clip.final.mp4"))
    assert out == Path("output/x/Clip.final.dubbed.mp4")
