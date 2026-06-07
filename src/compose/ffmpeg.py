"""Compose final videos with ffmpeg.

Burn mode renders the styled bilingual ASS into the frames (re-encode); soft
mode muxes the ASS as a selectable track into MKV (no re-encode).

The ffmpeg `ass` filter is run from a temp directory holding a copy of the
subtitle under a safe ASCII name, so filenames full of spaces / parens /
full-width characters never need filtergraph escaping.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from .models import AAC, BURN, COPY, SOFT, ComposeResult

log = logging.getLogger("recreator.compose")

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
DEFAULT_CRF = 20
DEFAULT_PRESET = "medium"
DEFAULT_AUDIO = AAC
AUDIO_BITRATE = "192k"
DEFAULT_OUTPUT_DIR = "output"
_SAFE_SUB_NAME = "subtitle.ass"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]
ProgressFn = Callable[[int], None]

_PROGRESS_US = re.compile(r"out_time_us=(\d+)")


def _parse_progress_us(line: str) -> int | None:
    """Parse ffmpeg `-progress` output, returning encoded microseconds."""
    match = _PROGRESS_US.search(line)
    return int(match.group(1)) if match else None


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


def default_output(
    video_path: str | Path,
    mode: str = BURN,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> Path:
    """Final-video path under `output_dir`, mirroring the download layout.

    `downloads/<date>/<channel>/Title.mp4` →
    `output/<date>/<channel>/Title.final.<ext>`. The `<date>/<channel>` mirror
    is taken from the source video's two enclosing directories.
    """
    video = Path(video_path)
    ext = "mkv" if mode == SOFT else "mp4"
    name = f"{video.stem}.final.{ext}"

    parts = video.parent.parts
    if parts and parts[0] == video.parent.anchor and video.parent.anchor:
        parts = parts[1:]  # drop the filesystem root so the join stays relative
    mirror = Path(*parts[-2:]) if len(parts) >= 2 else Path()
    return Path(output_dir) / mirror / name


def compose(
    video_path: str | Path,
    subtitle_path: str | Path,
    out_path: str | Path | None = None,
    *,
    mode: str = BURN,
    crf: int = DEFAULT_CRF,
    preset: str = DEFAULT_PRESET,
    audio: str = DEFAULT_AUDIO,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    preview_seconds: int | None = None,
    on_progress: ProgressFn | None = None,
    runner: Runner = _default_runner,
) -> ComposeResult:
    """Compose a final video. Never raises — failures are returned.

    `on_progress(pct)` (burn mode) receives encode-progress percentages.
    """
    video = Path(video_path)
    subtitle = Path(subtitle_path)
    out = Path(out_path) if out_path else default_output(video, mode, output_dir)
    out.parent.mkdir(parents=True, exist_ok=True)

    if audio not in (AAC, COPY):
        return ComposeResult(video, subtitle, out, mode, ok=False, error=f"unknown audio: {audio!r}")
    if mode == SOFT:
        return _mux_soft(video, subtitle, out, audio, preview_seconds, runner)
    if mode == BURN:
        return _burn(video, subtitle, out, crf, preset, audio, preview_seconds, on_progress, runner)
    return ComposeResult(video, subtitle, out, mode, ok=False, error=f"unknown mode: {mode!r}")


def build_burn_command(
    video: Path,
    out: Path,
    crf: int = DEFAULT_CRF,
    preset: str = DEFAULT_PRESET,
    audio: str = DEFAULT_AUDIO,
    preview_seconds: int | None = None,
    sub_name: str = _SAFE_SUB_NAME,
    progress: bool = False,
) -> list[str]:
    """ffmpeg argv for burning subs. `sub_name` is resolved relative to cwd."""
    cmd = [FFMPEG, "-y"]
    if progress:
        cmd += ["-progress", "pipe:1", "-nostats"]
    cmd += ["-i", str(video.resolve())]
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


def _burn(video, subtitle, out, crf, preset, audio, preview_seconds, on_progress, runner) -> ComposeResult:
    tmpdir = Path(tempfile.mkdtemp(prefix="recreator-compose-"))
    try:
        shutil.copyfile(subtitle, tmpdir / _SAFE_SUB_NAME)
        if on_progress is not None:
            cmd = build_burn_command(video, out, crf, preset, audio, preview_seconds, progress=True)
            log.debug("ffmpeg: %s", " ".join(cmd))
            duration = float(preview_seconds) if preview_seconds else _probe_duration(video, runner)
            ok, err = _run_with_progress(cmd, str(tmpdir), duration, on_progress)
            return ComposeResult(video, subtitle, out, BURN, ok=ok, error=err)
        cmd = build_burn_command(video, out, crf, preset, audio, preview_seconds)
        log.debug("ffmpeg: %s", " ".join(cmd))
        proc = runner(cmd, cwd=str(tmpdir))
        return _result(video, subtitle, out, BURN, proc)
    except Exception as err:
        return ComposeResult(video, subtitle, out, BURN, ok=False, error=str(err))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _probe_duration(video: Path, runner: Runner) -> float | None:
    cmd = [
        FFPROBE, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(video.resolve()),
    ]
    try:
        return float(runner(cmd).stdout.strip())
    except Exception:
        return None


def _run_with_progress(cmd, cwd, duration, on_progress) -> tuple[bool, str | None]:
    """Stream ffmpeg `-progress`, reporting percentage against `duration`."""
    proc = subprocess.Popen(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    last = -10
    for line in proc.stdout or ():
        micros = _parse_progress_us(line)
        if micros is not None and duration:
            pct = min(99, int(micros / 1_000_000 / duration * 100))
            if pct >= last + 10:
                last = pct
                on_progress(pct)
    proc.wait()
    if proc.returncode == 0:
        on_progress(100)
        return True, None
    err = (proc.stderr.read() if proc.stderr else "") or ""
    return False, err.strip()[-800:]


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
