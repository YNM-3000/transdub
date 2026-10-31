"""Build a bilingual ASS subtitle: Chinese on top, original below.

A single fixed style is applied — white fill with a black outline — with the
Chinese font larger than the (smaller) original. Long lines are folded so they
don't run off the frame: Chinese wraps to at most two lines (shrinking the font
only if it still won't fit), and the smaller English line shrinks to stay on one
line. YouTube captions carry no rich styling, so we apply one tidy default.
"""

from __future__ import annotations

import re
import unicodedata

import pysubs2

# Chinese is the primary line: larger on top; English smaller underneath.
ZH_FONTSIZE = 22
EN_FONTSIZE = 13
MIN_ZH_FONTSIZE = 16
MIN_EN_FONTSIZE = 10
FONT_NAME = "Arial"
ALIGN_BOTTOM_CENTER = pysubs2.Alignment.BOTTOM_CENTER

# Max display width per line (CJK chars count as 2). Tuned for a 16:9 frame; a
# line wider than this is folded (Chinese) or shrunk (English).
ZH_MAX_WIDTH = 38   # ~19 Chinese characters
EN_MAX_WIDTH = 52

# Static look: white text, black outline (opaque; ASS alpha 0 == opaque).
WHITE = pysubs2.Color(255, 255, 255, 0)
BLACK = pysubs2.Color(0, 0, 0, 0)
OUTLINE_WIDTH = 2.0
# Vertical margin from the bottom edge — smaller sits the subtitle lower.
MARGIN_V = 6

from .models import Cue

_WS = re.compile(r"\s+")


def _flatten(text: str) -> str:
    """Collapse internal whitespace/newlines so each language is one line."""
    return _WS.sub(" ", text.replace("\\N", " ")).strip()


def _width(text: str) -> int:
    """Display width: CJK (wide/fullwidth) counts as 2, everything else as 1."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def _wrap(text: str, max_width: int) -> list[str]:
    """Greedily wrap `text` into lines no wider than `max_width`.

    Breaks at a space when there's a recent one (keeps English words intact),
    otherwise between characters (Chinese wraps anywhere).
    """
    lines: list[str] = []
    line = ""
    last_space = -1
    for ch in text:
        line += ch
        if ch == " ":
            last_space = len(line) - 1
        if _width(line) > max_width and len(line) > 1:
            if last_space > 0:
                lines.append(line[:last_space].rstrip())
                line = line[last_space + 1:]
            else:
                lines.append(line[:-1].rstrip())
                line = ch
            last_space = -1
    if line.strip():
        lines.append(line.strip())
    return lines or [""]


def _fold_zh(text: str) -> tuple[str, int]:
    """Chinese → (text with \\N breaks, font size). At most two lines; if it
    won't fit in two at the base size, shrink the font so it does."""
    text = _flatten(text)
    if _width(text) <= ZH_MAX_WIDTH:
        return text, ZH_FONTSIZE
    lines = _wrap(text, ZH_MAX_WIDTH)
    if len(lines) <= 2:
        return "\\N".join(lines), ZH_FONTSIZE
    budget = (_width(text) + 1) // 2  # widen so two lines suffice
    size = max(MIN_ZH_FONTSIZE, round(ZH_FONTSIZE * ZH_MAX_WIDTH / budget))
    return "\\N".join(_wrap(text, budget)), size


def _fit_en(text: str) -> tuple[str, int]:
    """English (reference) → (one line, font size), shrinking if too wide."""
    text = _flatten(text)
    width = _width(text)
    if width <= EN_MAX_WIDTH:
        return text, EN_FONTSIZE
    size = max(MIN_EN_FONTSIZE, round(EN_FONTSIZE * EN_MAX_WIDTH / width))
    return text, size


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
        zh_line, zh_fs = _fold_zh(zh)
        en_line, en_fs = _fit_en(cue.text)
        # Chinese on top (larger, up to two lines), English below (smaller).
        text = f"{{\\fs{zh_fs}}}{zh_line}\\N{{\\fs{en_fs}}}{en_line}"
        subs.append(
            pysubs2.SSAEvent(
                start=cue.start_ms,
                end=cue.end_ms,
                text=text,
                style="Default",
            )
        )
    return subs
