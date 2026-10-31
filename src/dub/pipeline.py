"""Dub a video: bilingual ASS → Chinese voice track → audio-replaced video."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from .assread import chinese_cues
from .audio import build_dub_track, default_dub_output, mux_audio
from .backend import VoiceBackend
from .models import DubResult
from .segment import merge_into_sentences

log = logging.getLogger("transdub.dub")


def dub_video(
    video_path: str | Path,
    ass_path: str | Path,
    backend: VoiceBackend,
    out_path: str | Path | None = None,
    *,
    merge: bool = False,
    on_progress=None,
) -> DubResult:
    """Produce a Chinese-dubbed copy of `video_path`. Never raises.

    By default the voice is synthesized **one clip per subtitle cue**, so the
    spoken line stays locked to what's on screen (no desync from the dub grouping
    cues differently than the subtitle). `merge=True` re-groups cues into longer
    sentence units first — smoother prosody for raw caption fragments, but the
    voice then spans several subtitle lines. Prefer the default with sentence-
    level subtitles (`--sentences`); they already read as whole sentences.
    """
    video = Path(video_path)
    out = Path(out_path) if out_path else default_dub_output(video)
    # The actual voice (e.g. zh-CN-YunxiNeural), not the engine name.
    voice = getattr(backend, "voice", "") or getattr(backend, "name", "")

    cues = chinese_cues(ass_path)
    if not cues:
        return DubResult(video, out, ok=False, voice=voice,
                         error=f"no Chinese cues in {ass_path}")
    # Align the voice 1:1 with the displayed subtitle cues unless asked to merge.
    if merge:
        cues = merge_into_sentences(cues)

    # Cloning backends (GPT-SoVITS) need a reference of the channel's own voice;
    # cut one from the source (or reuse the cached per-channel clip).
    if getattr(backend, "needs_reference", False) and not getattr(backend, "ref_audio", None):
        try:
            from .assread import english_cues
            from .reference import channel_of, ensure_reference

            ref, prompt = ensure_reference(video, english_cues(ass_path))
            backend.set_reference(ref, prompt, "en")
            backend.voice_label = f"{channel_of(video)}(cloned)"
            voice = getattr(backend, "voice", "") or backend.voice_label
        except Exception as err:
            return DubResult(video, out, ok=False, voice=voice,
                             error=f"reference voice setup failed: {err}")

    log.info("dub: synthesizing %d lines with %s", len(cues), voice or "voice backend")
    try:
        with tempfile.TemporaryDirectory(prefix="transdub-dub-") as tmp:
            track = build_dub_track(
                cues, backend, Path(tmp) / "dub.wav",
                workdir=Path(tmp), on_progress=on_progress,
            )
            mux_audio(video, track, out)
    except Exception as err:
        return DubResult(video, out, ok=False, voice=voice, error=str(err))

    return DubResult(video, out, ok=True, voice=voice)
