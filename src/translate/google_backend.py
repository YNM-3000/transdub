"""Free online translation via Google's public translate endpoint.

Unlike the LLM backends, a dedicated MT service translates each cue on its own,
so the output is *always* one line per input — the line-drop / line-merge / line-
repeat failures that plague local LLMs on the numbered-line protocol simply can't
happen here. No API key; uses the free `translate_a/single` endpoint over stdlib.

Quality is best paired with `--sentences` (whole sentences translate better than
mid-caption fragments). Cues in a chunk are translated concurrently to hide the
per-request latency.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger("transdub.translate")

ENDPOINT = "https://translate.googleapis.com/translate_a/single"
DEFAULT_TARGET = "zh-CN"
MAX_RETRIES = 3
BACKOFF_BASE_S = 1.0
TIMEOUT_S = 15.0


class GoogleBackend:
    """Translate each cue independently via Google's free endpoint."""

    name = "google"

    def __init__(
        self,
        target: str | None = None,
        source: str = "auto",
        *,
        max_workers: int = 5,
        max_retries: int = MAX_RETRIES,
        sleep=time.sleep,
        transport=None,  # injected for tests: (text:str) -> translated text
    ) -> None:
        self._target = target or os.environ.get("GOOGLE_TRANSLATE_TARGET", DEFAULT_TARGET)
        self._source = source
        self._workers = max(1, int(os.environ.get("GOOGLE_TRANSLATE_WORKERS", max_workers)))
        self._max_retries = max_retries
        self._sleep = sleep
        self._transport = transport

    def describe(self) -> str:
        return "online · google-translate"

    def translate_chunk(self, cues: list[str], context: str) -> list[str]:
        if not cues:
            return []
        out: list[str] = [""] * len(cues)

        def one(i: int) -> None:
            out[i] = self._translate_one(cues[i])

        workers = min(self._workers, len(cues))
        if workers == 1:
            for i in range(len(cues)):
                one(i)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(one, range(len(cues))))
        return out

    def _translate_one(self, text: str) -> str:
        if not text.strip():
            return ""
        last_err: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                return self._request(text)
            except Exception as err:
                last_err = err
                if attempt < self._max_retries - 1:
                    self._sleep(BACKOFF_BASE_S * (2**attempt))
        raise RuntimeError(f"google translate failed: {last_err}") from last_err

    def _request(self, text: str) -> str:
        if self._transport is not None:
            return self._transport(text)
        query = urllib.parse.urlencode(
            {"client": "gtx", "sl": self._source, "tl": self._target, "dt": "t", "q": text}
        )
        req = urllib.request.Request(
            f"{ENDPOINT}?{query}", headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.load(resp)
        return _extract(data)


def _extract(data) -> str:
    """Join the translated segments from a translate_a/single response."""
    segments = data[0] if data and data[0] else []
    return "".join(seg[0] for seg in segments if seg and seg[0]).strip()
