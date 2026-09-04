"""Command-line entry point: dub a video with a Chinese voice."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

import obs
from .backend import get_voice_backend
from .pipeline import dub_video

_log = obs.logger("dub")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="recreator-dub",
        description="Replace a video's audio with a Chinese TTS voice, driven by "
                    "the bilingual subtitle. Writes <video>.dubbed.<ext> alongside it.",
    )
    parser.add_argument("video", help="the (final) video file to dub")
    parser.add_argument("subtitle", help="bilingual .ass subtitle (the dub script)")
    parser.add_argument("-o", "--output", help="explicit output path")
    parser.add_argument("--voice", help="override the voice (engine-specific)")
    obs.add_verbose_arg(parser)
    args = parser.parse_args(argv)
    obs.configure(args.verbose)

    for path in (args.video, args.subtitle):
        if not Path(path).is_file():
            print(f"error: not found: {path}", file=sys.stderr)
            return 2

    backend = get_voice_backend(args.voice)
    if backend is None:
        print(
            "error: no voice backend available. Install one with: "
            "uv sync --extra dub   (edge-tts) or set up Kokoro model files.",
            file=sys.stderr,
        )
        return 2

    result = dub_video(
        args.video, args.subtitle, backend, args.output,
        on_progress=obs.make_progress("dub", _log),
    )
    if not result.ok:
        print(f"✗ dub failed\n    {result.error}", file=sys.stderr)
        return 1
    print(f"✓ {result.out_path}  [{result.voice}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
