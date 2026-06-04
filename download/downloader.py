"""Download videos + subtitles via the yt-dlp CLI.

The CLI (not the Python API) is used deliberately: YouTube's auth and
JS-challenge flags (`--cookies-from-browser`, `--remote-components ejs:npm`)
are well-supported there and already proven to work in this environment. The
subprocess runner is injectable so tests need no network.
"""

from __future__ import annotations

import glob
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date as _date
from pathlib import Path
from typing import Callable

from .models import DownloadResult, VideoInfo

YTDLP = "yt-dlp"
# Prefer <=1080p; merge to mp4. Falls back gracefully if the exact combo is
# unavailable.
DEFAULT_FORMAT = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
# EJS npm solver is required to solve YouTube's n-challenge; without it only
# storyboard images are offered.
REMOTE_COMPONENTS = "ejs:npm"

Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def _default_runner(cmd: list[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(cmd, capture_output=True, text=True)


def build_command(
    url: str,
    base_dir: str | Path,
    day: str,
    fmt: str = DEFAULT_FORMAT,
    cookies_browser: str | None = "chrome",
) -> list[str]:
    """Assemble the yt-dlp argv for one video.

    Output template encodes the date/channel directory structure; yt-dlp
    creates the directories. `--dump-json` with `--no-simulate` downloads and
    emits the info JSON (incl. final file paths) to stdout.
    """
    outtmpl = f"{base_dir}/{day}/%(channel)s/%(title)s.%(ext)s"
    cmd = [YTDLP, "--no-progress", "--no-playlist"]
    if cookies_browser:
        cmd += ["--cookies-from-browser", cookies_browser]
    cmd += [
        "--remote-components", REMOTE_COMPONENTS,
        "--write-subs", "--write-auto-subs", "--sub-langs", "en.*,en",
        "--convert-subs", "srt",
        "--write-info-json",  # persist source metadata sidecar for later stages
        "-f", fmt,
        "--merge-output-format", "mp4",
        "-o", outtmpl,
        "--no-simulate", "--dump-json",
        url,
    ]
    return cmd


def download_one(
    url: str,
    *,
    base_dir: str | Path = "downloads",
    day: str | None = None,
    fmt: str = DEFAULT_FORMAT,
    cookies_browser: str | None = "chrome",
    runner: Runner = _default_runner,
) -> DownloadResult:
    """Download a single video + subtitles. Never raises — errors are returned."""
    day = day or _date.today().isoformat()
    cmd = build_command(url, base_dir, day, fmt, cookies_browser)
    try:
        proc = runner(cmd)
    except Exception as err:  # runner/process launch failure
        return DownloadResult(url=url, ok=False, error=str(err))

    if proc.returncode != 0:
        return DownloadResult(url=url, ok=False, error=_tail(proc.stderr))

    try:
        info = _parse_info(proc.stdout)
    except ValueError as err:
        return DownloadResult(url=url, ok=False, error=str(err))

    video_path = _resolve_video_path(info)
    return DownloadResult(
        url=url,
        ok=True,
        video_path=video_path,
        subtitle_path=_find_subtitle(video_path),
        info=_video_info(info),
    )


def download_many(
    urls: list[str],
    *,
    max_workers: int = 3,
    **kwargs,
) -> list[DownloadResult]:
    """Download several videos in parallel, preserving input order."""
    if not urls:
        return []
    workers = max(1, min(max_workers, len(urls)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda u: download_one(u, **kwargs), urls))


def _parse_info(stdout: str) -> dict:
    """Return the last JSON object yt-dlp printed (one per video)."""
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError("no JSON info found in yt-dlp output")


def _resolve_video_path(info: dict) -> Path | None:
    """Resolve the final video path from yt-dlp's info.

    `--dump-json` prints before the download completes, so requested_downloads
    / filepath are usually absent; `_filename` (the rendered output template)
    is the reliable fallback and matches the merged .mp4 on disk.
    """
    downloads = info.get("requested_downloads") or []
    filepath = (
        (downloads[0].get("filepath") if downloads else None)
        or info.get("filepath")
        or info.get("_filename")
    )
    return Path(filepath) if filepath else None


def _find_subtitle(video_path: Path | None) -> Path | None:
    """Locate the converted .srt sitting next to the video (e.g. *.en.srt)."""
    if video_path is None:
        return None
    pattern = glob.escape(str(video_path.with_suffix(""))) + "*.srt"
    matches = sorted(glob.glob(pattern))
    return Path(matches[0]) if matches else None


def _video_info(info: dict) -> VideoInfo:
    return VideoInfo(
        id=info.get("id", ""),
        title=info.get("title", ""),
        channel=info.get("channel") or info.get("uploader") or "",
        url=info.get("webpage_url") or info.get("original_url") or "",
        upload_date=info.get("upload_date"),
        view_count=info.get("view_count"),
        like_count=info.get("like_count"),
        duration_s=info.get("duration"),
    )


def _tail(text: str | None, limit: int = 600) -> str:
    text = (text or "").strip()
    return text[-limit:]
