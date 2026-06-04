"""Build a bilingual ASS subtitle: original on top, Chinese below.

Per the spec, the new subtitle keeps a clean, consistent style with the
Chinese font slightly larger than the original. YouTube captions carry no
rich styling, so we apply one tidy default style rather than reproducing the
source pixel-for-pixel.
"""

from __future__ import annotations

import re

import pysubs2

from .models import Cue

EN_FONTSIZE = 16
ZH_FONTSIZE = 20
FONT_NAME = "Arial"
ALIGN_BOTTOM_CENTER = pysubs2.Alignment.BOTTOM_CENTER

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
    style.outline = 1.5
    style.shadow = 0.5
    style.marginv = 24

    for cue, zh in zip(cues, translations):
        en_line = _flatten(cue.text)
        zh_line = _flatten(zh)
        # English on top (smaller), Chinese below (larger), one event per cue.
        text = f"{{\\fs{EN_FONTSIZE}}}{en_line}\\N{{\\fs{ZH_FONTSIZE}}}{zh_line}"
        subs.append(
            pysubs2.SSAEvent(
                start=cue.start_ms,
                end=cue.end_ms,
                text=text,
                style="Default",
            )
        )
    return subs
