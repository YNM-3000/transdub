"""Local LLM implementation of MetadataBackend via Ollama.

Generates Chinese publish metadata with a local model, reusing the exact same
labeled-section prompt + parser as the Claude backend. stdlib-only HTTP.
"""

from __future__ import annotations

import logging
import os
import time

from .claude_backend import MAX_CONTENT_CHARS, SYSTEM_PROMPT, _parse_metadata
from .models import PublishMetadata

log = logging.getLogger("recreator.publish")

MAX_RETRIES = 3
BACKOFF_BASE_S = 1.0


class OllamaMetadataBackend:
    """Generate publish metadata via a local Ollama model."""

    def __init__(
        self,
        model: str | None = None,
        server: str | None = None,
        transport=None,  # injected for tests: (user:str) -> assistant text
        max_retries: int = MAX_RETRIES,
        sleep=time.sleep,
        temperature: float = 0.4,
    ) -> None:
        # Reuse translate's Ollama helpers for host/model resolution.
        from translate.ollama_backend import available_models, host, pick_model

        self._server = (server or host()).rstrip("/")
        self._model = model or os.environ.get("OLLAMA_MODEL")
        self._transport = transport
        self._max_retries = max_retries
        self._sleep = sleep
        self._temperature = temperature
        self._available_models = available_models
        self._pick_model = pick_model

    @property
    def model(self) -> str:
        if not self._model:
            self._model = self._pick_model(self._available_models(self._server)) or "llama3"
        return self._model

    def describe(self) -> str:
        return f"local · ollama:{self.model}"

    def generate(self, source_title: str, content: str) -> PublishMetadata:
        user = (
            f"Source title: {source_title}\n\n"
            f"Chinese content (subtitle text):\n{content[:MAX_CONTENT_CHARS]}\n\n"
            "Write the metadata in the required labeled format."
        )

        last_err: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                return _parse_metadata(self._request(user))
            except Exception as err:
                last_err = err
            if attempt < self._max_retries - 1:
                self._sleep(BACKOFF_BASE_S * (2**attempt))

        raise RuntimeError(f"ollama metadata generation failed: {last_err}") from last_err

    def _request(self, user: str) -> str:
        if self._transport is not None:
            return self._transport(user)
        from translate.ollama_backend import _chat

        return _chat(self._server, self.model, user, self._temperature, SYSTEM_PROMPT)
