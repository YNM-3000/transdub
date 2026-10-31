"""Read the Chinese dub script from a bilingual ASS subtitle.

The styler writes each event as `{\\fsZH}<chinese>\\N{\\fsEN}<english>`, where
either language may itself be folded across extra `\\N` line breaks for display.
So we split Chinese from English by the two font-size markers (not by the first
newline — that would grab only the first folded line and make the dub speak just
part of a sentence) and rejoin any folded lines back into one string.
"""

from __future__ import annotations

import re
from pathlib import Path

import pysubs2

from .models import VoiceCue

_FONT = re.compile(r"\{\\fs\d+\}")   # the per-language font-size markers
_TAG = re.compile(r"\{[^}]*\}")       # any ASS override block
_WS = re.compile(r"\s+")
# A space introduced by rejoining folded lines, sitting before CJK punctuation.
_SPACE_BEFORE_CJK_PUNCT = re.compile(r"\s+([，。！？、；：”』）》])")


def chinese_cues(ass_path: str | Path) -> list[VoiceCue]:
    """Extract (start, end, full-Chinese) cues — the whole sentence, unfolded."""
    return _cues(ass_path, part=0)


def english_cues(ass_path: str | Path) -> list[VoiceCue]:
    """Extract (start, end, full-English) cues (the reference transcript)."""
    return _cues(ass_path, part=1)


def _clean(text: str) -> str:
    """Drop override tags, turn line breaks into spaces, collapse whitespace."""
    text = _TAG.sub("", text).replace("\\N", " ").replace("\n", " ")
    text = _WS.sub(" ", text).strip()
    return _SPACE_BEFORE_CJK_PUNCT.sub(r"\1", text)


def _split_languages(raw: str) -> tuple[str, str]:
    """(chinese, english) from one event, split at the two font markers.

    Falls back to a first-newline split for subtitles not produced by our styler.
    """
    marks = list(_FONT.finditer(raw))
    if len(marks) >= 2:
        return (_clean(raw[marks[0].end():marks[1].start()]),
                _clean(raw[marks[1].end():]))
    parts = raw.split("\\N")
    return _clean(parts[0]), _clean("\\N".join(parts[1:]))


def _cues(ass_path: str | Path, part: int) -> list[VoiceCue]:
    subs = pysubs2.load(str(ass_path))
    cues: list[VoiceCue] = []
    for ev in subs:
        if ev.is_comment:
            continue
        text = _split_languages(ev.text)[part]
        if text:
            cues.append(VoiceCue(ev.start / 1000.0, ev.end / 1000.0, text))
    return cues
