"""edge-tts voice backend (online, free, high-quality zh-CN neural voices).

edge-tts yields MP3; we transcode to the normalized WAV via ffmpeg so all
clips concatenate cleanly. edge-tts is imported lazily.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

from .backend import SAMPLE_RATE

log = logging.getLogger("recreator.dub")

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
MAX_RETRIES = 3


class EdgeBackend:
    name = "edge-tts"

    def __init__(self, voice: str = DEFAULT_VOICE) -> None:
        self.voice = voice
        # edge-tts is network I/O-bound; synthesizing cues concurrently hides
        # the per-request websocket latency. Tune with $DUB_WORKERS.
        self.max_workers = int(os.environ.get("DUB_WORKERS", "8"))

    def describe(self) -> str:
        return f"online · edge-tts:{self.voice}"

    def synthesize(self, text: str, out_path: str | Path) -> None:
        import edge_tts  # lazy

        fd, mp3 = tempfile.mkstemp(prefix="recreator-dub-", suffix=".mp3")
        os.close(fd)  # edge-tts writes the path itself

        async def _run() -> None:
            await edge_tts.Communicate(text, self.voice).save(mp3)

        # edge-tts intermittently returns "No audio was received" (transient,
        # or under concurrency); retry with backoff before giving up.
        try:
            last_err: Exception | None = None
            for attempt in range(MAX_RETRIES):
                try:
                    asyncio.run(_run())
                    _to_wav(Path(mp3), Path(out_path))
                    return
                except Exception as err:
                    last_err = err
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(0.5 * (attempt + 1))
            raise last_err  # type: ignore[misc]
        finally:
            Path(mp3).unlink(missing_ok=True)


def _to_wav(src: Path, out: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"edge-tts wav transcode failed: {(proc.stderr or '')[-400:]}")
