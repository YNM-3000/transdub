"""Assemble the dub audio track with ffmpeg and mux it into the video."""

from __future__ import annotations

import logging
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .backend import SAMPLE_RATE, VoiceBackend
from .models import VoiceCue
from .timeline import plan_timeline

log = logging.getLogger("recreator.dub")

Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]
ProgressFn = Callable[[int], None]


def _run(cmd: list[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(cmd, capture_output=True, text=True)


def _check(proc, what: str) -> None:
    if proc.returncode != 0:
        raise RuntimeError(f"{what} failed: {(proc.stderr or '')[-400:]}")


def probe_duration(path: Path, runner: Runner = _run) -> float:
    proc = runner([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path),
    ])
    _check(proc, "ffprobe")
    return float(proc.stdout.strip())


def _silence(out: Path, seconds: float, runner: Runner) -> None:
    proc = runner([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"anullsrc=channel_layout=mono:sample_rate={SAMPLE_RATE}",
        "-t", f"{seconds:.3f}", "-c:a", "pcm_s16le", str(out),
    ])
    _check(proc, "ffmpeg silence")


def _fit(clip: Path, tempo: float, out: Path, runner: Runner) -> None:
    """Time-stretch a clip (tempo>1 speeds up) and normalize its format."""
    filt = ["-filter:a", f"atempo={tempo:.4f}"] if abs(tempo - 1.0) > 1e-3 else []
    proc = runner([
        "ffmpeg", "-y", "-i", str(clip), *filt,
        "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(out),
    ])
    _check(proc, "ffmpeg atempo")


def _concat(segments: list[Path], out: Path, workdir: Path, runner: Runner) -> None:
    listing = workdir / "concat.txt"
    listing.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in segments), encoding="utf-8"
    )
    proc = runner([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
        "-c:a", "pcm_s16le", str(out),
    ])
    _check(proc, "ffmpeg concat")


def build_dub_track(
    cues: list[VoiceCue],
    backend: VoiceBackend,
    out_wav: Path,
    *,
    workdir: Path,
    runner: Runner = _run,
    on_progress: ProgressFn | None = None,
) -> Path:
    """Synthesize each cue, fit it to its window, and concat into `out_wav`."""
    total = len(cues)
    clips = [workdir / f"clip{i:04d}.wav" for i in range(total)]
    _synthesize_all(cues, clips, backend, on_progress)

    durations = [probe_duration(c, runner) for c in clips]
    pieces = plan_timeline(cues, durations)

    segments: list[Path] = []
    for p in pieces:
        seg = workdir / f"seg{len(segments):04d}.wav"
        if p.kind == "silence":
            _silence(seg, p.seconds, runner)
        else:
            _fit(clips[p.clip_index], p.tempo, seg, runner)
        segments.append(seg)

    _concat(segments, out_wav, workdir, runner)
    if on_progress is not None:
        on_progress(100)
    return out_wav


def _synthesize_all(cues, clips, backend, on_progress) -> None:
    """Synthesize every cue, concurrently when the backend allows it.

    Network-bound backends (edge-tts) set `max_workers > 1` to hide per-request
    latency; local backends (Kokoro) default to 1. Ordering is by clip path, so
    concurrency doesn't affect the timeline.
    """
    total = len(cues)
    workers = max(1, int(getattr(backend, "max_workers", 1)))

    if workers == 1:
        for i, cue in enumerate(cues):
            backend.synthesize(cue.text, clips[i])
            if on_progress is not None:
                on_progress(min(99, int((i + 1) * 100 / total)))
        return

    done = 0
    lock = threading.Lock()

    def synth(i: int) -> None:
        nonlocal done
        backend.synthesize(cues[i].text, clips[i])
        with lock:
            done += 1
            if on_progress is not None:
                on_progress(min(99, int(done * 100 / total)))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for _ in pool.map(synth, range(total)):  # re-raises the first failure
            pass


def mux_audio(video: Path, audio: Path, out: Path, runner: Runner = _run) -> None:
    """Replace the video's audio with `audio` (video stream copied, audio AAC).

    The dub track ends at the last cue, so it's padded with trailing silence to
    the video's exact duration (`apad=whole_dur`) and the output is capped with
    `-t` — the full video is kept, and the mux terminates (a bare `apad` +
    `-shortest` produces an infinite stream that never ends).
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    duration = probe_duration(video, runner)
    proc = runner([
        "ffmpeg", "-y", "-i", str(video), "-i", str(audio),
        "-filter_complex", f"[1:a]apad=whole_dur={duration:.3f}[a]",
        "-map", "0:v:0", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.3f}",
        str(out),
    ])
    _check(proc, "ffmpeg mux")


def default_dub_output(video: Path) -> Path:
    """`X.final.mp4` → `X.final.dubbed.mp4`, alongside the subtitled version."""
    return video.with_name(f"{video.stem}.dubbed{video.suffix}")
