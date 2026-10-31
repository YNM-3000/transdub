"""Strip parenthetical glosses / translator notes from model output.

Translation models (dedicated MT especially, e.g. Hunyuan-MT) love to pad a line
with parenthetical asides: a kept source term `手动配置（provisioning）`, a proper
noun gloss `威瑞森（Verizon）`, a meta-note `（此处内容似乎不完整…）`, or an
explanatory aside `（即账户无法关联）`. None belong in a subtitle/dub — they clutter
the text and lengthen the spoken line (making it overrun its time window). So we
drop parenthetical groups wholesale, regardless of which backend produced them.
"""

from __future__ import annotations

import re

_OPEN = "（("
_CLOSE = "）)"
_WS = re.compile(r"[ \t]{2,}")


def strip_translator_notes(text: str) -> str:
    """Remove parenthetical groups (glosses/notes/asides), nesting-aware.

    Keeps a group only if dropping it would leave nothing — i.e. the whole line
    is itself parenthesised — so a line is never emptied to blank.
    """
    stripped = _strip_parens(text)
    return stripped if stripped.strip() else _WS.sub(" ", text).strip()


def _strip_parens(text: str) -> str:
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in _OPEN:
            end = _match_close(text, i)
            if end != -1:
                i = end + 1  # drop the whole bracketed group
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
