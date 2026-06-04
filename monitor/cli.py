"""Command-line entry point: scan watched channels and notify."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .config import load_config
from .models import NEW
from .notify import EmailSettings, build_digest, notify
from .scanner import scan
from .state import SeenStore
from .youtube_api import YouTubeClient

DEFAULT_CONFIG = "channels.json"
DEFAULT_DB = "recreator.db"


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="recreator-monitor",
        description="Scan watched YouTube channels for new/trending videos and email a digest.",
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG, help=f"watchlist JSON (default: {DEFAULT_CONFIG})")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"state DB (default: {DEFAULT_DB})")
    parser.add_argument("--dry-run", action="store_true", help="print alerts; do not send email")
    args = parser.parse_args(argv)

    if not Path(args.config).is_file():
        print(f"error: config not found: {args.config}", file=sys.stderr)
        return 2

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("error: YOUTUBE_API_KEY is not set", file=sys.stderr)
        return 2

    config = load_config(args.config)
    client = YouTubeClient(api_key)
    with SeenStore(args.db) as state:
        alerts = scan(config, client, state)

    if not alerts:
        print("no new or trending videos")
        return 0

    subject, body = build_digest(alerts)
    print(subject)
    print(body)

    if args.dry_run:
        print("\n(dry-run: email not sent)")
        return 0

    settings = EmailSettings.from_env()
    if not settings.is_complete():
        print("\nwarning: SMTP not configured (set SMTP_HOST/SMTP_FROM/SMTP_TO) — email skipped", file=sys.stderr)
        return 0

    notify(alerts, settings)
    print(f"\nemailed {len(alerts)} alert(s) to {settings.to}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
