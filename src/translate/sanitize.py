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
# Markers that identify a parenthetical as a translator note / meta-commentary
# (not real content) — e.g. the model hedging about garbled source audio with
# `（此处内容似乎不完整或存在语法错误…）`. A group is dropped only if it contains
# one of these, so genuine parentheticals in the translation are preserved.
_NOTE_MARKERS = (
    "注：", "注:", "译注", "譯注", "訳注", "注释", "注釋", "translator", "T/N",
    # meta-commentary about the text itself (almost never legitimate content)
    "此处", "此處", "原文", "似乎", "无法翻译", "無法翻譯", "语法错误", "語法錯誤",
    "不完整", "疑似", "机翻", "機翻", "译者", "譯者", "音频", "音頻",
    "untranslat", "unclear", "garbled", "(sic)", "[sic]",
)
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
