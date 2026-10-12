"""Download videos + subtitles via the yt-dlp CLI.

The CLI (not the Python API) is used deliberately: YouTube's auth and
JS-challenge flags (`--cookies-from-browser`, `--remote-components ejs:npm`)
are well-supported there and already proven to work in this environment. The
subprocess runner is injectable so tests need no network.
"""

from __future__ import annotations

import glob
import json
import logging
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date as _date
from pathlib import Path
from typing import Callable

from .models import DownloadResult, VideoInfo

log = logging.getLogger("transdub.download")

YTDLP = "yt-dlp"
# Prefer <=1080p; merge to mp4. Falls back gracefully if the exact combo is
# unavailable.
DEFAULT_FORMAT = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
# EJS npm solver is required to solve YouTube's n-challenge; without it only
# storyboard images are offered.
REMOTE_COMPONENTS = "ejs:npm"

Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]
ProgressFn = Callable[[int], None]

# yt-dlp `--newline` progress lines, e.g. "[download]  42.7% of   12.3MiB ...".
# The size (estimate may be prefixed with `~`) is captured when present.
_DL_PCT = re.compile(
    r"\[download\]\s+([\d.]+)%(?:\s+of\s+~?\s*([\d.]+\s*[KMGT]i?B))?"
)


def normalize_url(url: str) -> str:
    """Clean shell-mangled URLs.

    A backslash is never valid in a URL, but it's easy to paste one in at the
    shell (e.g. `watch\\?v\\=…` when `?`/`=` get escaped inside quotes). Left in,
    yt-dlp fails to recognise the YouTube URL and falls back to its `[generic]`
    extractor. Strip stray backslashes and surrounding whitespace.
    """
    return url.strip().replace("\\", "")


_VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".mov")
_INFO_SUFFIX = ".info.json"


def video_id(url: str) -> str | None:
    """Extract the 11-char YouTube video id from a URL (or a bare id)."""
    url = normalize_url(url)
    match = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([0-9A-Za-z_-]{11})", url)
    if match:
        return match.group(1)
    bare = re.fullmatch(r"[0-9A-Za-z_-]{11}", url)
    return bare.group(0) if bare else None


def find_local_download(
    url: str, base_dir: str | Path = "downloads"
) -> tuple[dict, Path] | None:
    """Locate an already-downloaded video for `url` under `base_dir`.

    A finished download leaves `<name>.info.json` beside the merged video.
    Finding both lets the pipeline skip yt-dlp entirely on a re-run — faster,
    and it sidesteps YouTube's bot challenge ("page needs to be reloaded") that
    a fresh info extraction would otherwise trip. Returns (info, video_path), or
    None when no complete download exists (missing either sidecar = incomplete).
    """
    vid = video_id(url)
    if not vid:
        return None
    tag = f'"{vid}"'  # cheap pre-filter before parsing a possibly-large info.json
    for info_path in sorted(Path(base_dir).glob(f"**/*{_INFO_SUFFIX}")):
        stem = info_path.name[: -len(_INFO_SUFFIX)]
        video = next(
            (p for ext in _VIDEO_EXTS if (p := info_path.with_name(stem + ext)).is_file()),
            None,
        )
        if video is None:
            continue
        try:
            text = info_path.read_text(encoding="utf-8")
        except OSError:
            continue
        if tag not in text:
            continue
        try:
            info = json.loads(text)
        except json.JSONDecodeError:
            continue
        if info.get("id") == vid:
            return info, video
    return None


def _default_runner(cmd: list[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(cmd, capture_output=True, text=True)


def build_command(
    url: str,
    base_dir: str | Path,
    day: str,
    fmt: str = DEFAULT_FORMAT,
    cookies_browser: str | None = "chrome",
    progress: bool = False,
) -> list[str]:
    """Assemble the yt-dlp argv for one video.

    Output template encodes the date/channel directory structure; yt-dlp
    creates the directories. `--dump-json` with `--no-simulate` downloads and
    emits the info JSON (incl. final file paths) to stdout.

    `progress=True` emits download progress one line per update (parseable
    while streaming). `--progress` is required because `--dump-json` otherwise
    suppresses progress output entirely; `--newline` makes each update its own
    line instead of carriage-return overwrites.
    """
    outtmpl = f"{base_dir}/{day}/%(channel)s/%(title)s.%(ext)s"
    cmd = [YTDLP, "--no-playlist"]
    cmd += ["--newline", "--progress"] if progress else ["--no-progress"]
    if cookies_browser:
        cmd += ["--cookies-from-browser", cookies_browser]
    cmd += [
        "--remote-components", REMOTE_COMPONENTS,
        "--write-subs", "--write-auto-subs", "--sub-langs", "en.*,en",
        "--convert-subs", "srt",
        "--write-info-json",  # persist source metadata sidecar for later stages
        "--write-thumbnail", "--convert-thumbnails", "jpg",  # source thumbnail
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
    on_progress: ProgressFn | None = None,
    runner: Runner = _default_runner,
) -> DownloadResult:
    """Download a single video + subtitles. Never raises — errors are returned.

    `on_progress(pct)` streams download percentages; only honoured with the
    default runner (tests inject a runner and bypass streaming).
    """
    url = normalize_url(url)
    # Resume/idempotency: if this video is already on disk, reuse it and skip
    # yt-dlp (and the YouTube round-trip that may now hit a bot challenge).
    local = find_local_download(url, base_dir)
    if local is not None:
        info, video_path = local
        log.info("download: reusing already-downloaded %s", video_path.name)
        if on_progress is not None and runner is _default_runner:
            on_progress(100)
        return DownloadResult(
            url=url,
            ok=True,
            video_path=video_path,
            subtitle_path=_find_subtitle(video_path),
            info=_video_info(info),
        )

    day = day or _date.today().isoformat()
    stream = on_progress is not None and runner is _default_runner
    cmd = build_command(url, base_dir, day, fmt, cookies_browser, progress=stream)
    log.info("download: fetching %s", url)
    log.debug("yt-dlp %s", " ".join(cmd))
    try:
        proc = _run_with_progress(cmd, on_progress) if stream else runner(cmd)
    except Exception as err:  # runner/process launch failure
        return DownloadResult(url=url, ok=False, error=str(err))

    if proc.returncode != 0:
        return DownloadResult(url=url, ok=False, error=_tail(proc.stderr))
    if stream:
        on_progress(100)  # close the single progress line

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


def _run_with_progress(cmd: list[str], on_progress: ProgressFn):
    """Run yt-dlp, streaming `[download] NN%` to `on_progress`.

    stdout is buffered (the trailing JSON line is parsed afterwards) while
    percentages are reported live. A video+audio merge reports two 0→99 passes;
    percent is capped at 99 so the caller's single line never closes early.
    """
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out: list[str] = []
    last = -5
    for line in proc.stdout or ():
        out.append(line)
        match = _DL_PCT.search(line)
        if match:
            pct = min(99, int(float(match.group(1))))
            if pct < last or pct >= last + 5:  # advanced, or a new stream reset
                last = pct
                size = (match.group(2) or "").replace(" ", "")
                on_progress(pct, f"of {size}" if size else "")
    proc.wait()
    stderr = proc.stderr.read() if proc.stderr else ""
    return subprocess.CompletedProcess(cmd, proc.returncode, "".join(out), stderr)


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
