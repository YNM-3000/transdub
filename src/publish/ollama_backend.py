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

log = logging.getLogger("transdub.publish")

MAX_RETRIES = 3
BACKOFF_BASE_S = 1.0
# Publish metadata is the only LLM step now (translation is dedicated MT), so we
# default to a strong, cheap hosted model served through Ollama's cloud. Override
# with $PUBLISH_MODEL (any Ollama model, local or `:cloud`).
DEFAULT_PUBLISH_MODEL = "minimax-m3.1-flash:cloud"


def publish_model() -> str:
    return os.environ.get("PUBLISH_MODEL") or DEFAULT_PUBLISH_MODEL


class OllamaMetadataBackend:
    """Generate publish metadata via an Ollama model (local or cloud)."""

    def __init__(
        self,
        model: str | None = None,
        server: str | None = None,
        transport=None,  # injected for tests: (user:str) -> assistant text
        max_retries: int = MAX_RETRIES,
        sleep=time.sleep,
        temperature: float = 0.4,
    ) -> None:
        from translate.ollama_backend import host  # reuse host resolution

        self._server = (server or host()).rstrip("/")
        self._model = model or publish_model()
        self._transport = transport
        self._max_retries = max_retries
        self._sleep = sleep
        self._temperature = temperature

    @property
    def model(self) -> str:
        return self._model

    def describe(self) -> str:
        where = "cloud" if self._model.endswith(":cloud") else "local"
        return f"{where} · ollama:{self.model}"

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
