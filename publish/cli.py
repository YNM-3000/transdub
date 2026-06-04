"""Command-line entry point: generate the publish package for a video."""

from __future__ import annotations

import sys
from pathlib import Path

import argparse

from dotenv import load_dotenv

from .backend import get_metadata_backend
from .content import chinese_from_ass
from .package import DEFAULT_OUTPUT_DIR, build_package
from .source import SourceInfo, find_info_json


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

    source = _resolve_source(args)

    pkg = build_package(
        args.video,
        content,
        backend=backend,
        source=source,
        output_dir=args.output_dir,
        cover_at=args.cover_at,
    )

    if not pkg.ok:
        print(f"✗ publish failed\n    {pkg.error}", file=sys.stderr)
        return 1

    print(f"✓ {pkg.metadata.title}")
    print(f"    tags:  {', '.join(pkg.metadata.tags)}")
    print(f"    meta:  {pkg.metadata_path}")
    print(f"    cover: {pkg.cover_path}")
    return 0


def _resolve_source(args) -> SourceInfo | None:
    """Build SourceInfo from an info.json (explicit or auto-detected) + overrides."""
    source = SourceInfo()
    info_path = args.info_json or find_info_json(args.subtitle, args.video)
    if info_path and Path(info_path).is_file():
        source = SourceInfo.from_ytdlp_json(info_path)

    overridden = SourceInfo(
        url=args.source_url or source.url,
        title=args.source_title or source.title,
        uploader=args.uploader or source.uploader,
        upload_date=args.upload_date or source.upload_date,
    )
    return None if overridden.is_empty() else overridden


if __name__ == "__main__":
    raise SystemExit(main())
