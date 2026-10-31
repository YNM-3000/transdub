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

# Chinese is the primary line: on top; English smaller underneath. The Chinese
# size is FIXED (consistent across cues) and kept small so most lines fit without
# folding; when a line is still too long it folds to AT MOST two lines.
ZH_FONTSIZE = 16
EN_FONTSIZE = 12
MIN_EN_FONTSIZE = 9
FONT_NAME = "Arial"
ALIGN_BOTTOM_CENTER = pysubs2.Alignment.BOTTOM_CENTER

# Max display width per line (CJK chars count as 2). The smaller Chinese font
# fits more per line, so the threshold is higher — fewer folds.
ZH_MAX_WIDTH = 54   # ~27 Chinese characters at fs16
ZH_MAX_LINES = 2    # never fold Chinese beyond two lines
EN_MAX_WIDTH = 64   # English stays on ONE line (font shrinks if wider)

# Static look: white text, thin black outline (opaque; ASS alpha 0 == opaque).
WHITE = pysubs2.Color(255, 255, 255, 0)
BLACK = pysubs2.Color(0, 0, 0, 0)
OUTLINE_WIDTH = 1.0
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


def _fold_zh(text: str) -> str:
    """Chinese → at most two lines at the fixed font (never shrinks, never 3+).

    If it won't fit two lines at the normal width, the per-line budget is widened
    so it still lands on exactly two balanced lines rather than folding further.
    """
    text = _flatten(text)
    if _width(text) <= ZH_MAX_WIDTH:
        return text
    lines = _wrap(text, ZH_MAX_WIDTH)
    if len(lines) > ZH_MAX_LINES:
        budget = (_width(text) + ZH_MAX_LINES - 1) // ZH_MAX_LINES  # ~half each
        lines = _wrap(text, budget)
    return "\\N".join(lines)


def _fit_en(text: str) -> tuple[str, int]:
    """English (reference) → one line only, shrinking the font if it's too wide."""
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
        zh_line = _fold_zh(zh)            # Chinese: fixed size, at most two lines
        en_line, en_fs = _fit_en(cue.text)  # English: one line, shrink if too wide
        # Chinese on top (larger), English below (smaller).
        text = f"{{\\fs{ZH_FONTSIZE}}}{zh_line}\\N{{\\fs{en_fs}}}{en_line}"
        subs.append(
            pysubs2.SSAEvent(
                start=cue.start_ms,
                end=cue.end_ms,
                text=text,
                style="Default",
            )
        )
    return subs
