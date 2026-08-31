"""Command-line entry point: generate the publish package for a video."""

from __future__ import annotations

import sys
from pathlib import Path

import argparse

from dotenv import load_dotenv

from .backend import get_metadata_backend
from .content import chinese_from_ass
from .package import DEFAULT_OUTPUT_DIR, build_package
from .render import format_package
from .source import (
    SourceInfo,
    find_info_json,
    source_thumbnail_for,
    source_video_for,
)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="recreator-publish",
        description="Generate Chinese title/description/tags + a cover for upload.",
    )
    parser.add_argument("video", help="the (final) video file")
    parser.add_argument(
        "-s", "--subtitle",
        help="bilingual .ass to source Chinese content from (recommended)",
    )
    parser.add_argument("--backend", default="claude", help="metadata backend (default: claude)")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="output root")
    parser.add_argument(
        "--cover-at", type=float, metavar="SECONDS",
        help="timestamp for the cover frame (default: ~30%% of duration)",
    )
    parser.add_argument("--thumbnail", help="image to use as the cover (overrides auto-detect)")
    parser.add_argument(
        "--cover-frame", action="store_true",
        help="extract a video frame instead of using the source thumbnail",
    )
    parser.add_argument(
        "--info-json",
        help="yt-dlp info.json for source attribution (auto-detected near the subtitle)",
    )
    parser.add_argument("--source-url", help="override source URL")
    parser.add_argument("--source-title", help="override original title")
    parser.add_argument("--uploader", help="override uploader/channel")
    parser.add_argument("--upload-date", help="override publish date (YYYYMMDD)")
    args = parser.parse_args(argv)

    if not Path(args.video).is_file():
        print(f"error: video not found: {args.video}", file=sys.stderr)
        return 2

    content = ""
    if args.subtitle:
        if not Path(args.subtitle).is_file():
            print(f"error: subtitle not found: {args.subtitle}", file=sys.stderr)
            return 2
        content = chinese_from_ass(args.subtitle)

    try:
        backend = get_metadata_backend(args.backend)
    except Exception as err:
        print(f"error: {err}", file=sys.stderr)
        return 2

    info_path = args.info_json or find_info_json(args.subtitle, args.video)
    source = _resolve_source(args, info_path)
    # Cover preference: source thumbnail → clean pre-burn source frame.
    thumbnail = None if args.cover_frame else (args.thumbnail or source_thumbnail_for(info_path))
    cover_video = source_video_for(info_path)

    pkg = build_package(
        args.video,
        content,
        backend=backend,
        source=source,
        thumbnail=thumbnail,
        cover_video=cover_video,
        output_dir=args.output_dir,
        cover_at=args.cover_at,
    )

    if not pkg.ok:
        print(f"✗ publish failed\n    {pkg.error}", file=sys.stderr)
        return 1

    print(format_package(pkg))
    return 0


def _resolve_source(args, info_path) -> SourceInfo | None:
    """Build SourceInfo from an info.json (explicit or auto-detected) + overrides."""
    source = SourceInfo()
    if info_path and Path(info_path).is_file():
        source = SourceInfo.from_ytdlp_json(info_path)

    overridden = SourceInfo(
        url=args.source_url or source.url,
        title=args.source_title or source.title,
        uploader=args.uploader or source.uploader,
        upload_date=args.upload_date or source.upload_date,
        description=source.description,  # keep for repo extraction
    )
    return None if overridden.is_empty() else overridden


if __name__ == "__main__":
    raise SystemExit(main())
