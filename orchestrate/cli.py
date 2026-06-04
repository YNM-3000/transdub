"""Command-line entry point: download + translate in one run."""

from __future__ import annotations

import sys

import argparse

from dotenv import load_dotenv

from download.downloader import DEFAULT_FORMAT
from translate.backend import get_backend

from .models import TRANSLATED
from .pipeline import process_urls


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="recreator-run",
        description="Download YouTube videos and translate them to bilingual subtitles.",
    )
    parser.add_argument("urls", nargs="+", help="one or more video URLs")
    parser.add_argument("--base-dir", default="downloads", help="root output directory")
    parser.add_argument("--format", default=DEFAULT_FORMAT, help="yt-dlp format selector")
    parser.add_argument(
        "--cookies-browser",
        default="chrome",
        help="browser to read cookies from (use '' to disable)",
    )
    parser.add_argument("--jobs", type=int, default=3, help="parallel downloads")
    parser.add_argument(
        "--backend",
        default="claude",
        help="translation backend (default: claude)",
    )
    parser.add_argument(
        "--no-clean",
        dest="clean",
        action="store_false",
        help="do not de-roll YouTube auto-captions before translating",
    )
    args = parser.parse_args(argv)

    try:
        backend = get_backend(args.backend)
    except Exception as err:
        print(f"error: {err}", file=sys.stderr)
        return 2

    results = process_urls(
        args.urls,
        backend,
        max_workers=args.jobs,
        clean=args.clean,
        base_dir=args.base_dir,
        fmt=args.format,
        cookies_browser=args.cookies_browser or None,
    )

    failures = 0
    for r in results:
        if r.status == TRANSLATED:
            print(f"✓ {r.url}\n    subtitles: {r.ass_path}")
        else:
            failures += 1
            print(f"✗ {r.url}  [{r.status}]\n    {r.error}", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
