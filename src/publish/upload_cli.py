"""Command-line entry point: upload a finished video to Bilibili via biliup.

Deliberately separate from the pipeline — uploading publishes to a real account,
so it's an explicit, human-run step after you've reviewed the result. Defaults to
a dry run that just prints the command; pass --publish to actually upload.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

import obs
from .upload import (
    COPYRIGHT_ORIGINAL,
    COPYRIGHT_REPOST,
    DEFAULT_BINARY,
    DEFAULT_COOKIES,
    DEFAULT_TID,
    upload_video,
)

_log = obs.logger("publish")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="transdub-upload",
        description="Upload a finished video to Bilibili via the biliup CLI, using "
                    "the sibling <video>.metadata.json + .cover.jpg. One-time setup: "
                    "install biliup and run `biliup login` to create cookies.json.",
    )
    parser.add_argument("video", help="the final (or dubbed) video file to upload")
    parser.add_argument("-m", "--metadata", help="metadata JSON (default: <video>.metadata.json)")
    parser.add_argument("--cover", help="cover image (default: <video>.cover.jpg)")
    parser.add_argument("--cookies", default=DEFAULT_COOKIES,
                        help=f"biliup credentials file (default: {DEFAULT_COOKIES}, $BILIUP_COOKIES)")
    parser.add_argument("--binary", default=DEFAULT_BINARY,
                        help=f"biliup executable (default: {DEFAULT_BINARY}, $BILIUP_BIN)")
    parser.add_argument("--tid", type=int, default=DEFAULT_TID,
                        help=f"Bilibili partition/category id (default: {DEFAULT_TID})")
    parser.add_argument("--original", action="store_true",
                        help="mark as original (原创); default is repost (转载) with source attribution")
    parser.add_argument("--source", help="override the source URL for the 转载 attribution")
    parser.add_argument("--line", help="upload route (bda2/ws/qn/kodo/cos)")
    parser.add_argument("--publish", action="store_true",
                        help="actually upload (default is a dry run that only prints the command)")
    obs.add_verbose_arg(parser)
    args = parser.parse_args(argv)
    obs.configure(args.verbose)

    if not Path(args.video).is_file():
        print(f"error: not found: {args.video}", file=sys.stderr)
        return 2

    result = upload_video(
        args.video,
        metadata_path=args.metadata,
        cover_path=args.cover,
        cookies=args.cookies,
        binary=args.binary,
        tid=args.tid,
        copyright=COPYRIGHT_ORIGINAL if args.original else COPYRIGHT_REPOST,
        source_url=args.source,
        line=args.line,
        dry_run=not args.publish,
    )

    if not result.ok:
        print(f"✗ upload failed: {result.error}", file=sys.stderr)
        return 1
    if not args.publish:
        print("dry run — would run (add --publish to upload):\n    " + " ".join(result.command))
        return 0
    print(f"✓ uploaded{f' → {result.bvid}' if result.bvid else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
