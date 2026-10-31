"""Local dedicated-MT translation via an Ollama model, one cue at a time.

Dedicated translation models (e.g. Hunyuan-MT) produce excellent Chinese but do
NOT follow the numbered-line batch protocol the chat backends use — asked for "N
numbered lines" they merge/drop like any non-instruction model. Called per cue as
straight "translate this" requests, they're perfect: one translation per input,
so the count can never drift. This is the local, free, reliable counterpart to
the Google backend — best paired with `--sentences` so each unit is a whole
thought.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .ollama_backend import DEFAULT_HOST, host

log = logging.getLogger("transdub.translate")

# A strong, widely-available into-Chinese MT model (GGUF on Ollama).
DEFAULT_MT_MODEL = "hf.co/mradermacher/Hunyuan-MT-7B-GGUF:Q4_K_M"
# Hunyuan-MT instruction for into-Chinese translation. Only the translation —
# no notes/brackets/explanations, even when the (ASR) source is garbled.
DEFAULT_PROMPT = (
    "把下面的文本翻译成中文。只输出译文本身，不要任何解释、备注或括号说明；"
    "即使原文不完整或有误，也直接翻译，不要评论。\n\n{text}"
)
MAX_RETRIES = 3
BACKOFF_BASE_S = 1.0
GEN_TIMEOUT_S = 120.0


class OllamaMTBackend:
    """Translate each cue with a local MT model via Ollama /api/generate."""

    name = "ollama-mt"

    def __init__(
        self,
        model: str | None = None,
        server: str | None = None,
        *,
        prompt_template: str | None = None,
        max_workers: int = 4,
        max_retries: int = MAX_RETRIES,
        temperature: float = 0.3,
        sleep=time.sleep,
        transport=None,  # injected for tests: (text:str) -> translated text
    ) -> None:
        self._server = (server or host()).rstrip("/")
        self._model = model or os.environ.get("OLLAMA_MT_MODEL", DEFAULT_MT_MODEL)
        self._prompt = prompt_template or os.environ.get("OLLAMA_MT_PROMPT", DEFAULT_PROMPT)
        self._workers = max(1, int(os.environ.get("OLLAMA_MT_WORKERS", max_workers)))
        self._max_retries = max_retries
        self._temperature = temperature
        self._sleep = sleep
        self._transport = transport

    def describe(self) -> str:
        label = "hunyuan-mt" if "hunyuan" in self._model.lower() else self._model
        return f"local · {label}"

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
                result = self._request(text).strip()
                if result:
                    return result
                last_err = RuntimeError("empty translation")
            except Exception as err:
                last_err = err
            if attempt < self._max_retries - 1:
                self._sleep(BACKOFF_BASE_S * (2**attempt))
        raise RuntimeError(f"ollama-mt translation failed: {last_err}") from last_err

    def _request(self, text: str) -> str:
        if self._transport is not None:
            return self._transport(text)
        payload = {
            "model": self._model,
            "prompt": self._prompt.format(text=text),
            "stream": False,
            "think": False,
            "options": {"temperature": self._temperature, "num_predict": 1024},
        }
        req = urllib.request.Request(
            f"{self._server}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=GEN_TIMEOUT_S) as resp:
            return json.load(resp).get("response", "")
