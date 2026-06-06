"""Build a bilingual ASS subtitle: Chinese on top, original below.

A single fixed style is applied — white fill with a black outline — with the
Chinese font larger than the (smaller) original. YouTube captions carry no
rich styling, so we apply one tidy default rather than reproducing the source.
"""

from __future__ import annotations

import re

import pysubs2

# Chinese is the primary line: larger on top; English smaller underneath.
ZH_FONTSIZE = 22
EN_FONTSIZE = 13
FONT_NAME = "Arial"
ALIGN_BOTTOM_CENTER = pysubs2.Alignment.BOTTOM_CENTER

# Static look: white text, black outline (opaque; ASS alpha 0 == opaque).
WHITE = pysubs2.Color(255, 255, 255, 0)
BLACK = pysubs2.Color(0, 0, 0, 0)
OUTLINE_WIDTH = 2.0
# Vertical margin from the bottom edge — smaller sits the subtitle lower.
MARGIN_V = 12

from .models import Cue

_WS = re.compile(r"\s+")


def _flatten(text: str) -> str:
    """Collapse internal whitespace/newlines so each language is one line."""
    return _WS.sub(" ", text.replace("\\N", " ")).strip()


def build_bilingual(cues: list[Cue], translations: list[str]) -> pysubs2.SSAFile:
    """Assemble a bilingual ASS file from source cues and Chinese lines.

    `translations` must be parallel to `cues` (same length, same order).
    """
    if len(cues) != len(translations):
        raise ValueError(
            f"cues ({len(cues)}) and translations ({len(translations)}) "
            "must be the same length"
        )

    subs = pysubs2.SSAFile()
    style = subs.styles["Default"]
    style.fontname = FONT_NAME
    style.fontsize = ZH_FONTSIZE
    style.alignment = ALIGN_BOTTOM_CENTER
    style.primarycolor = WHITE
    style.outlinecolor = BLACK
    style.backcolor = BLACK
    style.borderstyle = 1  # outline + drop shadow
    style.outline = OUTLINE_WIDTH
    style.shadow = 0.0
    style.marginv = MARGIN_V

    for cue, zh in zip(cues, translations):
        en_line = _flatten(cue.text)
        zh_line = _flatten(zh)
        # Chinese on top (larger), English below (smaller), one event per cue.
        text = f"{{\\fs{ZH_FONTSIZE}}}{zh_line}\\N{{\\fs{EN_FONTSIZE}}}{en_line}"
        subs.append(
            pysubs2.SSAEvent(
                start=cue.start_ms,
                end=cue.end_ms,
                text=text,
                style="Default",
            )
        )
    return subs
