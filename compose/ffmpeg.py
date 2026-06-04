"""Compose final videos with ffmpeg.

Burn mode renders the styled bilingual ASS into the frames (re-encode); soft
mode muxes the ASS as a selectable track into MKV (no re-encode).

The ffmpeg `ass` filter is run from a temp directory holding a copy of the
subtitle under a safe ASCII name, so filenames full of spaces / parens /
full-width characters never need filtergraph escaping.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from .models import AAC, BURN, COPY, SOFT, ComposeResult

FFMPEG = "ffmpeg"
DEFAULT_CRF = 20
DEFAULT_PRESET = "medium"
DEFAULT_AUDIO = AAC
AUDIO_BITRATE = "192k"
_SAFE_SUB_NAME = "subtitle.ass"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def _audio_args(audio: str) -> list[str]:
    """ffmpeg args for the chosen audio handling.

    Default AAC transcode keeps the output broadly playable (YouTube's best
    audio is often Opus, which some Chinese platforms reject in MP4).
    """
    if audio == COPY:
        return ["-c:a", "copy"]
    return ["-c:a", "aac", "-b:a", AUDIO_BITRATE]


def _default_runner(cmd: list[str], cwd: str | None = None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def default_output(video_path: str | Path, mode: str = BURN) -> Path:
    """Final-video path next to the source (`*.final.mp4` / `*.final.mkv`)."""
    video = Path(video_path)
    ext = "mkv" if mode == SOFT else "mp4"
    return video.with_suffix(f".final.{ext}")


def compose(
    video_path: str | Path,
    subtitle_path: str | Path,
    out_path: str | Path | None = None,
    *,
    mode: str = BURN,
    crf: int = DEFAULT_CRF,
    preset: str = DEFAULT_PRESET,
    audio: str = DEFAULT_AUDIO,
    preview_seconds: int | None = None,
    runner: Runner = _default_runner,
) -> ComposeResult:
    """Compose a final video. Never raises — failures are returned."""
    video = Path(video_path)
    subtitle = Path(subtitle_path)
    out = Path(out_path) if out_path else default_output(video, mode)
    out.parent.mkdir(parents=True, exist_ok=True)

    if audio not in (AAC, COPY):
        return ComposeResult(video, subtitle, out, mode, ok=False, error=f"unknown audio: {audio!r}")
    if mode == SOFT:
        return _mux_soft(video, subtitle, out, audio, preview_seconds, runner)
    if mode == BURN:
        return _burn(video, subtitle, out, crf, preset, audio, preview_seconds, runner)
    return ComposeResult(video, subtitle, out, mode, ok=False, error=f"unknown mode: {mode!r}")


def build_burn_command(
    video: Path,
    out: Path,
    crf: int = DEFAULT_CRF,
    preset: str = DEFAULT_PRESET,
    audio: str = DEFAULT_AUDIO,
    preview_seconds: int | None = None,
    sub_name: str = _SAFE_SUB_NAME,
) -> list[str]:
    """ffmpeg argv for burning subs. `sub_name` is resolved relative to cwd."""
    cmd = [FFMPEG, "-y", "-i", str(video.resolve())]
    if preview_seconds:
        cmd += ["-t", str(preview_seconds)]
    cmd += [
        "-vf", f"ass={sub_name}",
        "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
        *_audio_args(audio),
        str(out.resolve()),
    ]
    return cmd


def build_soft_command(
    video: Path,
    subtitle: Path,
    out: Path,
    audio: str = DEFAULT_AUDIO,
    preview_seconds: int | None = None,
) -> list[str]:
    """ffmpeg argv for muxing a soft ASS track into MKV (video not re-encoded)."""
    cmd = [FFMPEG, "-y", "-i", str(video.resolve()), "-i", str(subtitle.resolve())]
    if preview_seconds:
        cmd += ["-t", str(preview_seconds)]
    cmd += [
        "-map", "0:v", "-map", "0:a?", "-map", "1",
        "-c:v", "copy", *_audio_args(audio), "-c:s", "ass",
        str(out.resolve()),
    ]
    return cmd


def _burn(video, subtitle, out, crf, preset, audio, preview_seconds, runner) -> ComposeResult:
    tmpdir = Path(tempfile.mkdtemp(prefix="recreator-compose-"))
    try:
        shutil.copyfile(subtitle, tmpdir / _SAFE_SUB_NAME)
        cmd = build_burn_command(video, out, crf, preset, audio, preview_seconds)
        proc = runner(cmd, cwd=str(tmpdir))
        return _result(video, subtitle, out, BURN, proc)
    except Exception as err:
        return ComposeResult(video, subtitle, out, BURN, ok=False, error=str(err))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _mux_soft(video, subtitle, out, audio, preview_seconds, runner) -> ComposeResult:
    try:
        cmd = build_soft_command(video, subtitle, out, audio, preview_seconds)
        proc = runner(cmd)
        return _result(video, subtitle, out, SOFT, proc)
    except Exception as err:
        return ComposeResult(video, subtitle, out, SOFT, ok=False, error=str(err))


def _result(video, subtitle, out, mode, proc) -> ComposeResult:
    if proc.returncode != 0:
        return ComposeResult(video, subtitle, out, mode, ok=False, error=_tail(proc.stderr))
    return ComposeResult(video, subtitle, out, mode, ok=True)


def _tail(text: str | None, limit: int = 800) -> str:
    return (text or "").strip()[-limit:]
