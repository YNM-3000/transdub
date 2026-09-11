"""faster-whisper transcription backend.

faster-whisper (CTranslate2) is imported lazily so the dependency is only
needed when a caption-less video actually reaches this stage. Audio is
extracted to 16 kHz mono WAV with ffmpeg (already required by compose) for a
predictable decode, independent of the container's codecs.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from .backend import ProgressFn
from .models import Segment

log = logging.getLogger("recreator.transcribe")

DEFAULT_MODEL = "small"
SAMPLE_RATE = 16_000


class WhisperBackend:
    """Transcribe media with faster-whisper. The model loads once, on first use."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        device: str = "cpu",
        compute_type: str = "int8",
        language: str | None = "en",
    ) -> None:
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.language = language  # None → auto-detect
        self.detected_language: str | None = None
        self._model = None

    def describe(self) -> str:
        return f"local · whisper:{self.model_name}"

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # lazy: heavy import

            log.info(
                "transcribe: loading Whisper model %r (%s/%s)",
                self.model_name, self.device, self.compute_type,
            )
            self._model = WhisperModel(
                self.model_name, device=self.device, compute_type=self.compute_type
            )
        return self._model

    def transcribe(
        self, media_path: str | Path, *, on_progress: ProgressFn | None = None
    ) -> list[Segment]:
        model = self._load()
        audio = _extract_audio(Path(media_path))
        try:
            segments, info = model.transcribe(
                str(audio), language=self.language, vad_filter=True
            )
            self.detected_language = getattr(info, "language", None) or self.language
            duration = getattr(info, "duration", 0) or 0
            out: list[Segment] = []
            last = -5
            for seg in segments:  # generator: work streams as decoding proceeds
                out.append(Segment(float(seg.start), float(seg.end), seg.text))
                if on_progress is not None and duration:
                    pct = min(99, int(seg.end / duration * 100))
                    if pct >= last + 5:
                        last = pct
                        on_progress(pct)
            if on_progress is not None:
                on_progress(100)
            log.info("transcribe: %d segments", len(out))
            return out
        finally:
            audio.unlink(missing_ok=True)


def _extract_audio(media_path: Path) -> Path:
    """Extract mono 16 kHz WAV to a temp file; caller deletes it."""
    fd, tmp = tempfile.mkstemp(prefix="recreator-asr-", suffix=".wav")
    os.close(fd)  # ffmpeg -y writes the path itself
    cmd = [
        "ffmpeg", "-y", "-i", str(media_path),
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "wav", tmp,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        Path(tmp).unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg audio extract failed: {(proc.stderr or '')[-500:]}")
    return Path(tmp)
