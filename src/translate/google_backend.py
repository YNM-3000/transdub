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
# Batch many cues into one request (newline-joined) to cut request count ~30x —
# essential for long videos (thousands of fragment cues would otherwise rate-limit
# the free endpoint). Google preserves the newline-separated lines; on any count
# mismatch we fall back to per-cue for that batch so the 1:1 mapping is exact.
BATCH_MAX_LINES = 30
BATCH_MAX_CHARS = 1500


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
        # Group non-blank cues into newline-batches (bounded by lines + chars).
        batches: list[list[int]] = []
        cur: list[int] = []
        cur_chars = 0
        for i, text in enumerate(cues):
            if not text.strip():
                continue
            if cur and (len(cur) >= BATCH_MAX_LINES or cur_chars + len(text) > BATCH_MAX_CHARS):
                batches.append(cur)
                cur, cur_chars = [], 0
            cur.append(i)
            cur_chars += len(text) + 1
        if cur:
            batches.append(cur)

        def do_batch(batch: list[int]) -> None:
            texts = [cues[i] for i in batch]
            result = self._translate_batch(texts)
            for i, r in zip(batch, result):
                out[i] = r

        workers = min(self._workers, len(batches)) or 1
        if workers == 1:
            for b in batches:
                do_batch(b)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(do_batch, batches))
        return out

    def _translate_batch(self, texts: list[str]) -> list[str]:
        """Translate a group of cues in one request; fall back to per-cue on any
        line-count mismatch so the 1:1 mapping is always exact."""
        if len(texts) == 1:
            return [self._translate_one(texts[0])]
        try:
            lines = self._request("\n".join(texts)).split("\n")
        except Exception:
            lines = []
        if len(lines) == len(texts):
            return [line.strip() for line in lines]
        return [self._translate_one(t) for t in texts]  # fallback: guaranteed 1:1

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


def reachable(timeout: float = 2.0) -> bool:
    """True if Google's translate endpoint answers — used to prefer it in `auto`
    only when online, so offline runs still fall back to a local engine."""
    url = f"{ENDPOINT}?client=gtx&sl=en&tl={DEFAULT_TARGET}&dt=t&q=hi"
    try:
        urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
            timeout=timeout,
        )
        return True
    except urllib.error.HTTPError:
        return True  # any HTTP reply means it's reachable
    except Exception:
        return False


def _extract(data) -> str:
    """Join the translated segments from a translate_a/single response."""
    segments = data[0] if data and data[0] else []
    return "".join(seg[0] for seg in segments if seg and seg[0]).strip()
