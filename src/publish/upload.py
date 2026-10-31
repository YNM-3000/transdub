"""Upload a finished video to Bilibili by shelling out to the `biliup` CLI.

The publish stage produces the metadata JSON + cover; this turns that into an
actual upload. We don't reimplement Bilibili's churny, risk-controlled upload
API — `biliup` (https://github.com/biliup/biliup) is the maintained community
tool and exposes every field we need as flags, including 转载 attribution
(`--copyright 2 --source <url>`). Auth is a one-time `biliup login` that writes
`cookies.json`; thereafter uploads are headless.

Uploading publishes to a real account, so this is a deliberate, separate command
(`transdub-upload`) — never part of the automated pipeline — and defaults to a
dry run that only prints the command.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

log = logging.getLogger("transdub.publish")

Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]

DEFAULT_BINARY = os.environ.get("BILIUP_BIN", "biliup")
DEFAULT_COOKIES = os.environ.get("BILIUP_COOKIES", "cookies.json")
DEFAULT_TID = 171          # biliup's own default partition
COPYRIGHT_REPOST = 2       # 转载 (repost) — the default for translated re-uploads
COPYRIGHT_ORIGINAL = 1

_BVID = re.compile(r"\bBV[0-9A-Za-z]{10}\b")


@dataclass(frozen=True, slots=True)
class UploadResult:
    ok: bool
    command: list[str]
    bvid: str | None = None
    error: str | None = None


def build_upload_command(
    video: str | Path,
    meta: dict,
    *,
    cover: str | Path | None = None,
    cookies: str | Path = DEFAULT_COOKIES,
    binary: str = DEFAULT_BINARY,
    tid: int = DEFAULT_TID,
    copyright: int = COPYRIGHT_REPOST,
    source_url: str | None = None,
    line: str | None = None,
) -> list[str]:
    """Assemble the `biliup upload` argv from a metadata dict. Pure/testable.

    `source_url` defaults to the original video URL recorded in `meta["source"]`.
    For a repost (copyright 2) a source URL is required by Bilibili.
    """
    title = (meta.get("title") or Path(video).stem).strip()
    desc = (meta.get("description") or "").strip()
    tags = ",".join(t for t in (meta.get("tags") or []) if t)
    src = source_url or (meta.get("source") or {}).get("url")

    if copyright == COPYRIGHT_REPOST and not src:
        raise ValueError(
            "a source URL is required for a repost (copyright=2); none in metadata"
        )

    cmd = [binary, "-u", str(cookies), "upload",
           "--title", title, "--tid", str(tid), "--copyright", str(copyright)]
    if desc:
        cmd += ["--desc", desc]
    if tags:
        cmd += ["--tag", tags]
    if cover:
        cmd += ["--cover", str(cover)]
    if copyright == COPYRIGHT_REPOST and src:
        cmd += ["--source", src]
    if line:
        cmd += ["--line", line]
    cmd.append(str(video))
    return cmd


def _sibling(video: Path, suffix: str) -> Path:
    """Metadata/cover path beside the video, e.g. `<video>.metadata.json`.

    Publish writes those next to the *composed* video (`X.final.mp4`), so when
    uploading the dubbed variant (`X.final.dubbed.mp4`) we fall back to the
    un-dubbed sibling (`X.final.metadata.json`) when the direct name is absent.
    """
    base = video.with_suffix("")  # drop the video extension (.mp4)
    direct = base.with_name(base.name + suffix)
    if direct.is_file():
        return direct
    if base.name.endswith(".dubbed"):
        alt = base.with_name(base.name[: -len(".dubbed")] + suffix)
        if alt.is_file():
            return alt
    return direct  # non-existent direct path, for a clear error message


def _default_runner(cmd: list[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(cmd, capture_output=True, text=True)


def upload_video(
    video_path: str | Path,
    *,
    metadata_path: str | Path | None = None,
    cover_path: str | Path | None = None,
    cookies: str | Path = DEFAULT_COOKIES,
    binary: str = DEFAULT_BINARY,
    tid: int = DEFAULT_TID,
    copyright: int = COPYRIGHT_REPOST,
    source_url: str | None = None,
    line: str | None = None,
    dry_run: bool = True,
    runner: Runner = _default_runner,
) -> UploadResult:
    """Upload `video_path` to Bilibili via biliup. Never raises.

    Reads the sibling `<video>.metadata.json` (title/desc/tags/source) and
    `<video>.cover.jpg` unless given explicitly. With `dry_run` (the default) it
    only builds the command — nothing is published.
    """
    video = Path(video_path)
    meta_path = Path(metadata_path) if metadata_path else _sibling(video, ".metadata.json")
    if not meta_path.is_file():
        return UploadResult(False, [], error=f"metadata not found: {meta_path}")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as err:
        return UploadResult(False, [], error=f"bad metadata JSON: {err}")

    cover = Path(cover_path) if cover_path else _sibling(video, ".cover.jpg")
    if not cover.is_file():
        cover = None

    try:
        cmd = build_upload_command(
            video, meta, cover=cover, cookies=cookies, binary=binary, tid=tid,
            copyright=copyright, source_url=source_url, line=line,
        )
    except ValueError as err:
        return UploadResult(False, [], error=str(err))

    if dry_run:
        return UploadResult(True, cmd)

    if not Path(cookies).is_file():
        return UploadResult(
            False, cmd,
            error=f"no credentials at {cookies}; run `biliup login` first",
        )

    try:
        proc = runner(cmd)
    except FileNotFoundError:
        return UploadResult(False, cmd, error=f"`{binary}` not found; install biliup")
    if proc.returncode != 0:
        return UploadResult(False, cmd, error=(proc.stderr or proc.stdout or "")[-400:])
    match = _BVID.search((proc.stdout or "") + (proc.stderr or ""))
    return UploadResult(True, cmd, bvid=match.group(0) if match else None)
