"""Strip translator notes / meta-commentary from model output.

LLMs (local ones especially) sometimes inject annotations into a translated
line — e.g. `（注：此处为直译错误…）` or a whole deliberation in parentheses.
Those must never reach the subtitle/dub, so they're removed deterministically
regardless of which backend produced them.
"""

from __future__ import annotations

import re

_OPEN = "（("
_CLOSE = "）)"
# Markers that identify a parenthetical as a translator note (not real content).
_NOTE_MARKERS = ("注：", "注:", "译注", "譯注", "訳注", "注释", "注釋", "translator", "T/N")
_WS = re.compile(r"[ \t]{2,}")


def strip_translator_notes(text: str) -> str:
    """Remove parenthetical translator notes, handling nested brackets.

    A bracket group is dropped only when it contains a note marker, so genuine
    parentheticals in the translation are preserved.
    """
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in _OPEN:
            end = _match_close(text, i)
            if end != -1:
                group = text[i : end + 1]
                if any(m in group for m in _NOTE_MARKERS):
                    i = end + 1  # drop the whole note group
                    continue
                out.append(group)
                i = end + 1
                continue
        out.append(ch)
        i += 1
    return _WS.sub(" ", "".join(out)).strip()


def _match_close(text: str, start: int) -> int:
    """Index of the bracket closing the one at `start`, or -1 if unbalanced."""
    depth = 0
    for j in range(start, len(text)):
        if text[j] in _OPEN:
            depth += 1
        elif text[j] in _CLOSE:
            depth -= 1
            if depth == 0:
                return j
    return -1
