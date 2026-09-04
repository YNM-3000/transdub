"""Kokoro (local, offline) voice backend via kokoro-onnx.

Requires the ONNX model + voices files (KOKORO_MODEL / KOKORO_VOICES env, or
the kokoro-onnx defaults) and Chinese g2p (misaki[zh]); the constructor raises
if they're absent, so `get_voice_backend` can fall back to edge-tts. Samples
are written to WAV with the stdlib `wave` module (no extra audio dep).
"""

from __future__ import annotations

import os
import wave
from pathlib import Path

import numpy as np

from .backend import SAMPLE_RATE

DEFAULT_VOICE = "zf_xiaobei"  # a Chinese Kokoro voice


class KokoroBackend:
    name = "kokoro"

    def __init__(self, voice: str = DEFAULT_VOICE) -> None:
        from kokoro_onnx import Kokoro  # raises ImportError if not installed

        model = os.environ.get("KOKORO_MODEL", "kokoro-v1.0.onnx")
        voices = os.environ.get("KOKORO_VOICES", "voices-v1.0.bin")
        if not (Path(model).is_file() and Path(voices).is_file()):
            raise FileNotFoundError(
                f"Kokoro model files not found ({model!r}, {voices!r}); "
                "set KOKORO_MODEL / KOKORO_VOICES"
            )
        self.voice = voice
        self._kokoro = Kokoro(model, voices)
        self._g2p = None  # misaki zh G2P, created on first use

    def describe(self) -> str:
        return f"local · kokoro:{self.voice}"

    def _phonemes(self, text: str) -> str:
        # Kokoro's built-in espeak g2p has no Chinese; misaki provides it.
        if self._g2p is None:
            from misaki import zh

            self._g2p = zh.ZHG2P()
        phonemes, _ = self._g2p(text)
        return phonemes

    def synthesize(self, text: str, out_path: str | Path) -> None:
        samples, sr = self._kokoro.create(
            self._phonemes(text), voice=self.voice, is_phonemes=True
        )
        _write_wav(np.asarray(samples, dtype=np.float32), sr, Path(out_path))


def _write_wav(samples: "np.ndarray", sample_rate: int, out: Path) -> None:
    if sample_rate != SAMPLE_RATE:
        samples = _resample(samples, sample_rate, SAMPLE_RATE)
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767).astype("<i2")
    with wave.open(str(out), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm.tobytes())


def _resample(samples: "np.ndarray", src_rate: int, dst_rate: int) -> "np.ndarray":
    """Cheap linear resample (Kokoro is already 24 kHz; this is a safety net)."""
    n_dst = int(round(len(samples) * dst_rate / src_rate))
    if n_dst <= 0:
        return samples
    x_src = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
    x_dst = np.linspace(0.0, 1.0, num=n_dst, endpoint=False)
    return np.interp(x_dst, x_src, samples).astype(np.float32)
