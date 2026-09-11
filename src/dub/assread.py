"""Read the Chinese dub script from a bilingual ASS subtitle."""

from __future__ import annotations

from pathlib import Path

import pysubs2

from .models import VoiceCue


def chinese_cues(ass_path: str | Path) -> list[VoiceCue]:
    """Extract (start, end, Chinese-text) cues from a bilingual ASS.

    The styler writes Chinese on the first line and English on the second
    (`中文\\N原文`); `plaintext` drops override tags and turns \\N into a
    newline, so the Chinese line is everything before the first newline.
    """
    return _cues(ass_path, line=0)


def english_cues(ass_path: str | Path) -> list[VoiceCue]:
    """Extract (start, end, English-text) cues — the second line of each event.

    Used to cut a reference voice clip from the source: the English text is the
    transcript of the spoken audio in that time window.
    """
    return _cues(ass_path, line=1)


def _cues(ass_path: str | Path, line: int) -> list[VoiceCue]:
    subs = pysubs2.load(str(ass_path))
    cues: list[VoiceCue] = []
    for ev in subs:
        if ev.is_comment:
            continue
        parts = ev.plaintext.split("\n")
        text = parts[line].strip() if len(parts) > line else ""
        if text:
            cues.append(VoiceCue(ev.start / 1000.0, ev.end / 1000.0, text))
    return cues
