"""Claude implementation of TranslationBackend.

Translates life/knowledge-video subtitles into natural, spoken Chinese.

Wire format: numbered plain-text lines ("N. translation"), NOT JSON. Subtitle
text is full of quotes and commas, and the model's JSON escaping proved
unreliable for arrays; line-numbered text is parsed by index and is immune to
those characters, tolerant of preamble, and self-correcting via retries.
"""

from __future__ import annotations

import os
import re
import time

from .backend import LengthMismatchError

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_RETRIES = 3
BACKOFF_BASE_S = 2.0

SYSTEM_PROMPT = """\
You are a professional subtitle translator for Chinese video platforms.
You translate English subtitles of life/knowledge videos (everyday phenomena,
product design, things people overlook) into natural, spoken Mandarin Chinese.

Rules:
- Translate into colloquial, fluent Chinese that sounds natural when spoken,
  not literal word-for-word.
- Keep terminology consistent across lines.
- Preserve meaning and tone; do not add or omit content.
- Each input line maps to exactly one output line. Never merge or split lines.

Output format (STRICT):
- Output one line per input line, prefixed with its number and a period:
  `1. 译文`
- Output exactly as many numbered lines as there were input lines, in order.
- No preamble, no commentary, no blank lines, nothing but the numbered lines.
"""

_NUMBERED = re.compile(r"^\s*(\d+)[.)、]\s*(.*)$")


class ClaudeBackend:
    """Translate chunks of subtitle lines via the Anthropic Messages API."""

    def __init__(
        self,
        client: object | None = None,
        model: str | None = None,
        max_retries: int = MAX_RETRIES,
        sleep=time.sleep,
    ) -> None:
        self._client = client  # injected for tests; lazily created otherwise
        self._model = model or os.environ.get("RECREATOR_MODEL", DEFAULT_MODEL)
        self._max_retries = max_retries
        self._sleep = sleep

    @property
    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def translate_chunk(self, cues: list[str], context: str) -> list[str]:
        if not cues:
            return []

        numbered = "\n".join(f"{i + 1}. {line}" for i, line in enumerate(cues))
        user = (
            f"Context (for coherence only, do not translate):\n{context}\n\n"
            f"Translate these {len(cues)} lines to Chinese. Output exactly "
            f"{len(cues)} numbered lines, in order:\n{numbered}"
        )

        last_err: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                text = self._request(user)
                return _parse_numbered(text, len(cues))
            except LengthMismatchError as err:
                last_err = err  # retry: model dropped/added lines
            except Exception as err:
                if _is_non_retryable(err):
                    raise  # auth/permission/bad-request: retrying won't help
                last_err = err  # transient API/network error
            if attempt < self._max_retries - 1:
                self._sleep(BACKOFF_BASE_S * (2**attempt))

        raise RuntimeError(
            f"translation failed after retries: {last_err}"
        ) from last_err

    def _request(self, user: str) -> str:
        message = self.client.messages.create(
            model=self._model,
            max_tokens=8192,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text


def _is_non_retryable(err: Exception) -> bool:
    """True for 4xx API errors (except 429) — retrying those is futile.

    Detected via a `status_code` attribute so we stay decoupled from the
    anthropic SDK's specific exception classes.
    """
    status = getattr(err, "status_code", None)
    return isinstance(status, int) and 400 <= status < 500 and status != 429


def _parse_numbered(text: str, expected: int) -> list[str]:
    """Parse `N. translation` lines into an ordered list of `expected` items.

    Lines that do not start with a number are treated as continuations of the
    current entry (so a wrapped translation is preserved). Raises
    LengthMismatchError if any of 1..expected is missing.
    """
    by_index: dict[int, str] = {}
    current: int | None = None
    for line in text.splitlines():
        match = _NUMBERED.match(line)
        if match:
            current = int(match.group(1))
            by_index[current] = match.group(2).strip()
        elif current is not None and line.strip():
            by_index[current] = f"{by_index[current]} {line.strip()}".strip()

    out: list[str] = []
    for i in range(1, expected + 1):
        if i not in by_index:
            raise LengthMismatchError(expected, len(by_index))
        out.append(by_index[i])
    return out
