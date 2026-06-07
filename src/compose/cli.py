"""Command-line entry point: compose a final video from video + subtitles."""

from __future__ import annotations

import sys
from pathlib import Path

import argparse

import obs
from .ffmpeg import (
    DEFAULT_AUDIO,
    DEFAULT_CRF,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PRESET,
    compose,
)
from .models import AAC, BURN, COPY, SOFT

_log = obs.logger("compose")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="recreator-compose",
        description="Burn (or soft-mux) bilingual subtitles into a final video.",
    )
    parser.add_argument("video", help="source video file")
    parser.add_argument("subtitle", help="bilingual .ass subtitle file")
    parser.add_argument(
        "-o", "--output", help="explicit output path (overrides --output-dir)"
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="output root; mirrors <date>/<channel> from the source (default: output/)",
    )
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
    obs.add_verbose_arg(parser)
    args = parser.parse_args(argv)
    obs.configure(args.verbose)

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
        output_dir=args.output_dir,
        preview_seconds=args.preview,
        on_progress=lambda pct: _log.info("compose: %d%%", pct),
    )

    if not result.ok:
        print(f"✗ compose failed [{result.mode}]\n    {result.error}", file=sys.stderr)
        return 1
    print(f"✓ {result.out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
