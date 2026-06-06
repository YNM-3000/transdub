"""Extract the Chinese text from a bilingual ASS for metadata context."""

from __future__ import annotations

import re
from pathlib import Path

import pysubs2

_TAG = re.compile(r"\{[^}]*\}")


def chinese_from_ass(path: str | Path) -> str:
    """Return the Chinese lines of a bilingual ASS as one newline-joined block.

    The styler puts Chinese on the first line of each event (`中文\\N英文`); we
    strip override tags and take that line.
    """
    subs = pysubs2.load(str(path))
    lines: list[str] = []
    for event in subs:
        first = event.text.split(r"\N", 1)[0]
        text = _TAG.sub("", first).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)
