"""Command-line entry point: compose a final video from video + subtitles."""

from __future__ import annotations

import sys
from pathlib import Path

import argparse

from .ffmpeg import DEFAULT_AUDIO, DEFAULT_CRF, DEFAULT_PRESET, compose
from .models import AAC, BURN, COPY, SOFT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="recreator-compose",
        description="Burn (or soft-mux) bilingual subtitles into a final video.",
    )
    parser.add_argument("video", help="source video file")
    parser.add_argument("subtitle", help="bilingual .ass subtitle file")
    parser.add_argument("-o", "--output", help="output path (default: <video>.final.<ext>)")
    parser.add_argument(
        "--mode", choices=[BURN, SOFT], default=BURN,
        help="burn = hard subs into mp4 (default); soft = ASS track in mkv",
    )
    parser.add_argument("--crf", type=int, default=DEFAULT_CRF, help="x264 CRF (burn mode)")
    parser.add_argument("--preset", default=DEFAULT_PRESET, help="x264 preset (burn mode)")
    parser.add_argument(
        "--audio", choices=[AAC, COPY], default=DEFAULT_AUDIO,
        help="aac = transcode for platform compatibility (default); copy = passthrough",
    )
    parser.add_argument(
        "--preview", type=int, metavar="SECONDS",
        help="only render the first N seconds (fast check before a full encode)",
    )
    args = parser.parse_args(argv)

    for path in (args.video, args.subtitle):
        if not Path(path).is_file():
            print(f"error: not found: {path}", file=sys.stderr)
            return 2

    result = compose(
        args.video,
        args.subtitle,
        args.output,
        mode=args.mode,
        crf=args.crf,
        preset=args.preset,
        audio=args.audio,
        preview_seconds=args.preview,
    )

    if not result.ok:
        print(f"✗ compose failed [{result.mode}]\n    {result.error}", file=sys.stderr)
        return 1
    print(f"✓ {result.out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
