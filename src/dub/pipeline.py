"""Dub a video: bilingual ASS → Chinese voice track → audio-replaced video."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from .assread import chinese_cues
from .audio import build_dub_track, default_dub_output, mux_audio
from .backend import VoiceBackend
from .models import DubResult

log = logging.getLogger("recreator.dub")


def dub_video(
    video_path: str | Path,
    ass_path: str | Path,
    backend: VoiceBackend,
    out_path: str | Path | None = None,
    *,
    on_progress=None,
) -> DubResult:
    """Produce a Chinese-dubbed copy of `video_path`. Never raises."""
    video = Path(video_path)
    out = Path(out_path) if out_path else default_dub_output(video)
    # The actual voice (e.g. zh-CN-YunxiNeural), not the engine name.
    voice = getattr(backend, "voice", "") or getattr(backend, "name", "")

    cues = chinese_cues(ass_path)
    if not cues:
        return DubResult(video, out, ok=False, voice=voice,
                         error=f"no Chinese cues in {ass_path}")

    log.info("dub: synthesizing %d lines with %s", len(cues), voice or "voice backend")
    try:
        with tempfile.TemporaryDirectory(prefix="recreator-dub-") as tmp:
            track = build_dub_track(
                cues, backend, Path(tmp) / "dub.wav",
                workdir=Path(tmp), on_progress=on_progress,
            )
            mux_audio(video, track, out)
    except Exception as err:
        return DubResult(video, out, ok=False, voice=voice, error=str(err))

    return DubResult(video, out, ok=True, voice=voice)
