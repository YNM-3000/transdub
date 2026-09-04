"""edge-tts voice backend (online, free, high-quality zh-CN neural voices).

edge-tts yields MP3; we transcode to the normalized WAV via ffmpeg so all
clips concatenate cleanly. edge-tts is imported lazily.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path

from .backend import SAMPLE_RATE

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"


class EdgeBackend:
    name = "edge-tts"

    def __init__(self, voice: str = DEFAULT_VOICE) -> None:
        self.voice = voice

    def synthesize(self, text: str, out_path: str | Path) -> None:
        import edge_tts  # lazy

        fd, mp3 = tempfile.mkstemp(prefix="recreator-dub-", suffix=".mp3")
        os.close(fd)  # edge-tts writes the path itself

        async def _run() -> None:
            await edge_tts.Communicate(text, self.voice).save(mp3)

        try:
            asyncio.run(_run())
            _to_wav(Path(mp3), Path(out_path))
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
