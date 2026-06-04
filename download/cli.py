"""Command-line entry point: download videos + subtitles."""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from .downloader import DEFAULT_FORMAT, download_many


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="recreator-download",
        description="Download YouTube videos + subtitles into downloads/<date>/<channel>/.",
    )
    parser.add_argument("urls", nargs="+", help="one or more video URLs")
    parser.add_argument(
        "--base-dir", default="downloads", help="root output directory"
    )
    parser.add_argument("--format", default=DEFAULT_FORMAT, help="yt-dlp format selector")
    parser.add_argument(
        "--cookies-browser",
        default="chrome",
        help="browser to read cookies from (use '' to disable)",
    )
    parser.add_argument(
        "--jobs", type=int, default=3, help="parallel downloads (default: 3)"
    )
    args = parser.parse_args(argv)

    results = download_many(
        args.urls,
        max_workers=args.jobs,
        base_dir=args.base_dir,
        fmt=args.format,
        cookies_browser=args.cookies_browser or None,
    )

    failures = 0
    for r in results:
        if r.ok:
            title = r.info.title if r.info else r.url
            print(f"✓ {title}")
            print(f"    video: {r.video_path}")
            print(f"    subs:  {r.subtitle_path}")
        else:
            failures += 1
            print(f"✗ {r.url}\n    {r.error}", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
