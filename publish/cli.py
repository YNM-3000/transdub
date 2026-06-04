"""Command-line entry point: generate the publish package for a video."""

from __future__ import annotations

import sys
from pathlib import Path

import argparse

from dotenv import load_dotenv

from .backend import get_metadata_backend
from .content import chinese_from_ass
from .package import DEFAULT_OUTPUT_DIR, build_package


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

    pkg = build_package(
        args.video,
        content,
        backend=backend,
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


if __name__ == "__main__":
    raise SystemExit(main())
