"""Claude implementation of TranslationBackend.

Translates life/knowledge-video subtitles into natural, spoken Chinese.
Uses prompt caching on the system prompt and retries transient API errors.
"""

from __future__ import annotations

import json
import os
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
- Preserve the meaning and tone; do not add or omit content.
- Each input line maps to exactly one output line. Never merge or split lines.
- Output ONLY a JSON array of strings, one per input line, in order.
"""


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
            f"Translate these {len(cues)} lines to Chinese and return a JSON "
            f"array of exactly {len(cues)} strings, in order:\n{numbered}"
        )

        last_err: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                text = self._request(user)
                translated = _parse_array(text)
                if len(translated) != len(cues):
                    raise LengthMismatchError(len(cues), len(translated))
                return translated
            except LengthMismatchError as err:
                last_err = err  # retry: model miscounted lines
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
            max_tokens=4096,
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


def _parse_array(text: str) -> list[str]:
    """Extract a JSON array of strings from the model response."""
    cleaned = text.strip()
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON array in response: {text[:200]!r}")
    data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
        raise ValueError("response JSON is not a list of strings")
    return data
