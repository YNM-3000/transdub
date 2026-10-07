"""Local LLM implementation of TranslationBackend via Ollama.

Talks to a local Ollama server (http://localhost:11434) over its native
`/api/chat` endpoint using only the stdlib, so no new dependency. Reuses the
exact same system prompt + numbered-line wire protocol as the Claude backend,
so translation quality/parse behaviour is consistent and the two are truly
interchangeable.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request

from .backend import LengthMismatchError
from .claude_backend import SYSTEM_PROMPT, _parse_numbered

log = logging.getLogger("recreator.translate")

DEFAULT_HOST = "http://localhost:11434"
# Models good at Chinese, best first — used to auto-pick when OLLAMA_MODEL is unset.
PREFERRED = ("qwen", "yi", "glm", "deepseek", "gemma", "llama")
MAX_RETRIES = 3
BACKOFF_BASE_S = 1.0
CONNECT_TIMEOUT_S = 2.0
CHAT_TIMEOUT_S = 300.0
# Local 7–9B models reliably hold the numbered-line contract only for small
# batches; at 30 they merge short cues and drop lines. The pipeline still chunks
# at 30 (good for Claude's coherence) — we re-batch smaller just for Ollama.
DEFAULT_BATCH_SIZE = 15


def host() -> str:
    return os.environ.get("OLLAMA_HOST", DEFAULT_HOST).rstrip("/")


def available_models(server: str | None = None) -> list[str]:
    """Names of models the Ollama server has pulled; [] if unreachable."""
    url = f"{server or host()}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=CONNECT_TIMEOUT_S) as resp:
            data = json.load(resp)
    except Exception:
        return []
    return [m.get("name", "") for m in data.get("models", []) if m.get("name")]


def unload(server: str | None = None) -> list[str]:
    """Ask Ollama to unload any resident models (keep_alive=0) to free memory.

    Returns the names it tried to unload. Best-effort and silent on failure —
    used before a memory-heavy dub engine (GPT-SoVITS) runs.
    """
    base = (server or host()).rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/api/ps", timeout=CONNECT_TIMEOUT_S) as resp:
            loaded = [m.get("name", "") for m in json.load(resp).get("models", [])]
    except Exception:
        return []
    for model in filter(None, loaded):
        try:
            req = urllib.request.Request(
                f"{base}/api/generate",
                data=json.dumps({"model": model, "keep_alive": 0}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10.0).read()
        except Exception:
            pass
    return loaded


def pick_model(names: list[str]) -> str | None:
    """Choose the most Chinese-capable model from `names`."""
    for pref in PREFERRED:
        for name in names:
            if pref in name.lower():
                return name
    return names[0] if names else None


def ollama_available(server: str | None = None, model: str | None = None) -> bool:
    """True if the server is up and (any / the named) model is present."""
    names = available_models(server)
    if not names:
        return False
    if model:
        base = model.split(":")[0]
        return any(n == model or n.split(":")[0] == base for n in names)
    return True


class OllamaBackend:
    """Translate subtitle chunks via a local Ollama model."""

    def __init__(
        self,
        model: str | None = None,
        server: str | None = None,
        transport=None,  # injected for tests: (user:str) -> assistant text
        max_retries: int = MAX_RETRIES,
        sleep=time.sleep,
        temperature: float = 0.3,
        batch_size: int | None = None,
    ) -> None:
        self._server = (server or host()).rstrip("/")
        self._model = model or os.environ.get("OLLAMA_MODEL")  # may resolve lazily
        self._transport = transport
        self._max_retries = max_retries
        self._sleep = sleep
        self._temperature = temperature
        self._batch_size = batch_size or int(
            os.environ.get("OLLAMA_BATCH_SIZE", DEFAULT_BATCH_SIZE) or DEFAULT_BATCH_SIZE
        )

    @property
    def model(self) -> str:
        if not self._model:
            self._model = pick_model(available_models(self._server)) or "llama3"
            log.info("translate: ollama auto-selected model %r", self._model)
        return self._model

    def describe(self) -> str:
        return f"local · ollama:{self.model}"

    def translate_chunk(self, cues: list[str], context: str) -> list[str]:
        if not cues:
            return []
        # Translate in small batches the local model can keep aligned, then
        # stitch them back into one list. If any batch fails after retries the
        # whole chunk is reported failed, so the FallbackBackend hands the full
        # chunk to Claude (unchanged behaviour, just fewer forced fallbacks).
        out: list[str] = []
        for start in range(0, len(cues), self._batch_size):
            out.extend(self._translate_batch(cues[start : start + self._batch_size], context))
        return out

    def _translate_batch(self, cues: list[str], context: str) -> list[str]:
        numbered = "\n".join(f"{i + 1}. {line}" for i, line in enumerate(cues))
        user = (
            f"Context (for coherence only, do not translate):\n{context}\n\n"
            f"Translate these {len(cues)} lines to Chinese. Output exactly "
            f"{len(cues)} numbered lines, in order:\n{numbered}"
        )

        last_err: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                return _parse_numbered(self._request(user), len(cues))
            except LengthMismatchError as err:
                last_err = err  # model dropped/added lines: retry
            except Exception as err:
                last_err = err
            if attempt < self._max_retries - 1:
                self._sleep(BACKOFF_BASE_S * (2**attempt))

        raise RuntimeError(f"ollama translation failed after retries: {last_err}") from last_err

    def _request(self, user: str) -> str:
        if self._transport is not None:
            return self._transport(user)
        return _chat(self._server, self.model, user, self._temperature, SYSTEM_PROMPT)


def _chat(server: str, model: str, user: str, temperature: float, system: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "think": False,  # suppress <think> output on reasoning models (ignored otherwise)
        "options": {
            "temperature": temperature,
            "num_predict": 4096,
            # Override any penalties baked into the model's Modelfile. A high
            # presence/frequency penalty (qwen3.5:9b ships 1.5) punishes the
            # repeated "N." list markers, so the model merges many subtitle
            # lines into one entry and the chunk comes back short.
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
        },
    }
    req = urllib.request.Request(
        f"{server}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=CHAT_TIMEOUT_S) as resp:
        data = json.load(resp)
    return data.get("message", {}).get("content", "")
