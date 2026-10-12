"""Cut a reference voice clip from the source video for voice cloning.

Zero-shot cloning (GPT-SoVITS) needs a short clean speech sample of the target
speaker plus its transcript. We already have both: a window of English cues
gives the timing (audio range) and the text. The clip is cached per channel
(`models/refs/<channel>.wav` + `.txt`) so every video from the same channel is
dubbed in the same cloned voice.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from .models import VoiceCue

log = logging.getLogger("transdub.dub")

DEFAULT_REFS_DIR = "models/refs"
REF_SAMPLE_RATE = 32_000
MIN_SECONDS = 4.0   # GPT-SoVITS wants a 3–10s reference
MAX_SECONDS = 10.0


REGISTER_MAX_SECONDS = 10.0  # GPT-SoVITS prefers a short reference


def register_reference(
    media: str | Path,
    transcriber,
    *,
    name: str | None = None,
    refs_dir: str | Path = DEFAULT_REFS_DIR,
    max_seconds: float = REGISTER_MAX_SECONDS,
    runner=subprocess.run,
) -> tuple[Path, str, str]:
    """Register a custom reference voice from any audio/video file.

    Extracts a short clean clip to `models/refs/<name>.wav`, transcribes it with
    `transcriber` (Whisper) into `<name>.txt`, and records the detected language
    in `<name>.lang`. Returns (wav, transcript, lang). `name` defaults to the
    media's filename; reuse it later via `--voice <name>`.
    """
    media = Path(media)
    stem = name or media.stem
    out = Path(refs_dir) / f"{stem}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)

    _extract_audio(media, 0.0, max_seconds, out, runner)  # -t caps at max_seconds
    segments = transcriber.transcribe(out)
    transcript = " ".join(s.text.strip() for s in segments if s.text.strip()).strip()
    lang = getattr(transcriber, "detected_language", None) or "auto"

    out.with_suffix(".txt").write_text(transcript, encoding="utf-8")
    out.with_suffix(".lang").write_text(lang, encoding="utf-8")
    log.info("dub: registered reference voice %r (%s): %s", stem, lang, transcript[:60])
    return out, transcript, lang


def channel_of(video: Path) -> str:
    """Channel name = the video's enclosing directory (mirrors the layout)."""
    return video.parent.name or "voice"


def channel_reference(video: Path, refs_dir: str | Path = DEFAULT_REFS_DIR) -> Path:
    return Path(refs_dir) / f"{channel_of(video)}.wav"


def ensure_reference(
    video: str | Path,
    english_cues: list[VoiceCue],
    *,
    refs_dir: str | Path = DEFAULT_REFS_DIR,
    runner=subprocess.run,
) -> tuple[Path, str]:
    """Return (reference_wav, transcript), reusing a cached per-channel clip.

    Cuts a ~4–10s speech window from the middle of the video the first time a
    channel is seen, then reuses it.
    """
    video = Path(video)
    ref = channel_reference(video, refs_dir)
    txt = ref.with_suffix(".txt")
    if ref.is_file() and ref.stat().st_size > 0 and txt.is_file():
        log.info("dub: reusing channel reference %s", ref.name)
        return ref, txt.read_text(encoding="utf-8").strip()

    if not english_cues:
        raise ValueError("no cues available to cut a reference voice clip")

    window = pick_reference_window(english_cues)
    ref.parent.mkdir(parents=True, exist_ok=True)
    _extract_audio(video, window.start, window.end, ref, runner)
    txt.write_text(window.text, encoding="utf-8")
    log.info("dub: cut channel reference %s (%.1fs) from %s",
             ref.name, window.end - window.start, channel_of(video))
    return ref, window.text


def pick_reference_window(cues: list[VoiceCue]) -> VoiceCue:
    """Choose a contiguous ~4–10s speech window from the middle of the video.

    Starting a third of the way in skips intros/music; consecutive cues are
    merged until the window is long enough.
    """
    start_idx = min(len(cues) // 3, len(cues) - 1)
    first = cues[start_idx]
    start, end = first.start, first.end
    parts = [first.text]
    j = start_idx + 1
    while end - start < MIN_SECONDS and j < len(cues) and cues[j].end - start <= MAX_SECONDS:
        parts.append(cues[j].text)
        end = cues[j].end
        j += 1
    return VoiceCue(start, end, " ".join(parts))


def _extract_audio(video: Path, start: float, end: float, out: Path, runner) -> None:
    cmd = [
        "ffmpeg", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
        "-i", str(video), "-vn", "-ac", "1", "-ar", str(REF_SAMPLE_RATE),
        "-c:a", "pcm_s16le", str(out),
    ]
    proc = runner(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"reference extraction failed: {(proc.stderr or '')[-400:]}")
