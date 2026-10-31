"""Tests for the bilingual ASS styler."""

from __future__ import annotations

import pytest

from translate.models import Cue
from translate.styler import (
    BLACK,
    EN_FONTSIZE,
    MARGIN_V,
    MIN_ZH_FONTSIZE,
    WHITE,
    ZH_FONTSIZE,
    ZH_MAX_WIDTH,
    _fit_en,
    _fold_zh,
    _width,
    build_bilingual,
)


def test_width_counts_cjk_as_two():
    assert _width("abc") == 3
    assert _width("中文") == 4
    assert _width("中a") == 3


def test_short_chinese_stays_one_line_at_base_size():
    text, size = _fold_zh("你好世界")
    assert "\\N" not in text and size == ZH_FONTSIZE


def test_long_chinese_folds_to_two_lines():
    line = "这是一个非常长的中文字幕需要折行显示否则会超出屏幕宽度范围"  # > ZH_MAX_WIDTH
    text, size = _fold_zh(line)
    assert text.count("\\N") == 1            # exactly two lines
    assert size == ZH_FONTSIZE               # fits in two at base size
    assert text.replace("\\N", "") == line   # nothing lost


def test_very_long_chinese_shrinks_font_and_stays_two_lines():
    line = "中" * 60  # far wider than two base-size lines can hold
    text, size = _fold_zh(line)
    assert text.count("\\N") == 1            # still only two lines
    assert size < ZH_FONTSIZE and size >= MIN_ZH_FONTSIZE


def test_long_english_shrinks_but_stays_one_line():
    line = "this is a very long english reference line that would otherwise overflow the frame width"
    text, size = _fit_en(line)
    assert "\\N" not in text and text == line
    assert size < EN_FONTSIZE


def test_build_bilingual_produces_one_event_per_cue(sample_cues):
    translations = ["你好世界", "第二行", "第三行"]
    subs = build_bilingual(sample_cues, translations)

    assert len(subs) == len(sample_cues)
    first = subs[0]
    assert first.start == 1000
    assert first.end == 3500


def test_event_text_has_chinese_on_top_and_larger():
    cues = [Cue(index=0, start_ms=0, end_ms=1000, text="Hello world")]
    subs = build_bilingual(cues, ["你好世界"])
    text = subs[0].text

    assert f"\\fs{EN_FONTSIZE}" in text
    assert f"\\fs{ZH_FONTSIZE}" in text
    assert ZH_FONTSIZE > EN_FONTSIZE
    # Chinese precedes the newline (top line), English follows it (below).
    zh_part, en_part = text.split("\\N", 1)
    assert "你好世界" in zh_part
    assert "Hello world" in en_part


def test_multiline_source_is_flattened():
    cues = [Cue(index=0, start_ms=0, end_ms=1000, text="line one\nline two")]
    subs = build_bilingual(cues, ["译文"])
    en_part = subs[0].text.split("\\N", 1)[1]  # English is the second line now
    assert "line one line two" in en_part
    assert "\n" not in en_part


def test_default_style_is_configured():
    subs = build_bilingual([Cue(0, 0, 1000, "x")], ["y"])
    style = subs.styles["Default"]
    assert style.fontsize == ZH_FONTSIZE
    assert style.alignment == 2
    assert style.marginv == MARGIN_V  # sits low near the bottom edge


def test_style_is_white_with_black_outline():
    subs = build_bilingual([Cue(0, 0, 1000, "x")], ["y"])
    style = subs.styles["Default"]
    assert style.primarycolor == WHITE
    assert style.outlinecolor == BLACK
    assert style.borderstyle == 1
    assert style.outline == 2.0


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        build_bilingual([Cue(0, 0, 1, "a")], ["x", "y"])


def test_roundtrip_saves_loadable_ass(tmp_path, sample_cues):
    import pysubs2

    subs = build_bilingual(sample_cues, ["a", "b", "c"])
    out = tmp_path / "out.ass"
    subs.save(str(out))
    reloaded = pysubs2.load(str(out))
    assert len(reloaded) == 3
