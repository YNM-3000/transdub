"""GPT-SoVITS voice backend — HTTP client to a locally-running api_v2 server.

GPT-SoVITS is heavy PyTorch that runs as its own service (`python api_v2.py`,
default 127.0.0.1:9880, works on Apple Silicon). We keep it out of this venv
and just POST /tts with the Chinese text + a reference clip of the channel's
own voice (zero-shot cloning). The reference lives on the same machine, so we
pass its path directly.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from .backend import SAMPLE_RATE

log = logging.getLogger("recreator.dub")

DEFAULT_URL = "http://127.0.0.1:9880"
TIMEOUT_S = 300.0


class GPTSoVITSBackend:
    name = "gpt-sovits"
    needs_reference = True   # dub_video cuts/sets a channel reference before synth
    max_workers = 1          # one shared model on the server; keep requests serial

    def __init__(self, url: str | None = None, transport=None) -> None:
        self.url = (url or os.environ.get("GPT_SOVITS_URL", DEFAULT_URL)).rstrip("/")
        # "zh" = mixed Chinese/English (handles embedded English in the dub text).
        self.text_lang = os.environ.get("GPT_SOVITS_TEXT_LANG", "zh")
        self._transport = transport  # injected for tests: (body:dict) -> wav bytes
        self.ref_audio: str | None = None
        self.ref_text = ""
        self.ref_lang = "en"
        self.voice_label = "channel"

    def set_reference(self, audio_path: str | Path, text: str, lang: str = "en") -> None:
        self.ref_audio = str(Path(audio_path).resolve())
        self.ref_text = text
        self.ref_lang = lang

    def describe(self) -> str:
        return f"local · gpt-sovits:{self.voice_label}"

    def synthesize(self, text: str, out_path: str | Path) -> None:
        if not self.ref_audio:
            raise RuntimeError("GPT-SoVITS: no reference voice set")
        body = {
            "text": text,
            "text_lang": self.text_lang,
            "ref_audio_path": self.ref_audio,
            "prompt_text": self.ref_text,
            "prompt_lang": self.ref_lang,
            "text_split_method": "cut5",
            "media_type": "wav",
            "streaming_mode": False,
        }
        audio = self._transport(body) if self._transport else _post_tts(self.url, body)
        _to_wav(audio, Path(out_path))


def _post_tts(url: str, body: dict) -> bytes:
    req = urllib.request.Request(
        f"{url}/tts",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return resp.read()
    except urllib.error.HTTPError as err:  # api_v2 returns 400 + JSON on failure
        detail = err.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"GPT-SoVITS /tts failed ({err.code}): {detail}") from err
    except urllib.error.URLError as err:
        raise RuntimeError(
            f"GPT-SoVITS server unreachable at {url} ({err.reason}); "
            "start it with `python api_v2.py`"
        ) from err


def _to_wav(audio: bytes, out: Path) -> None:
    """Normalize the server's wav bytes to 24 kHz mono for the dub assembly."""
    fd, tmp = tempfile.mkstemp(prefix="recreator-sovits-", suffix=".wav")
    os.close(fd)
    try:
        Path(tmp).write_bytes(audio)
        cmd = [
            "ffmpeg", "-y", "-i", tmp,
            "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(out),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"GPT-SoVITS wav normalize failed: {(proc.stderr or '')[-300:]}")
    finally:
        Path(tmp).unlink(missing_ok=True)
