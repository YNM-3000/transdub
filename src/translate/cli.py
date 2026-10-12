"""Command-line entry point: translate a subtitle file to bilingual ASS."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

import obs
from .backend import get_backend
from .pipeline import translate_file

_log = obs.logger("translate")


def _default_out(in_path: str) -> str:
    stem = Path(in_path).stem
    return str(Path("out") / f"{stem}.bilingual.ass")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="transdub-translate",
        description="Translate a subtitle file into a bilingual ASS (EN + 中文).",
    )
    parser.add_argument("input", help="source subtitle file (.srt/.vtt/.ass)")
    parser.add_argument(
        "-o", "--output", help="output .ass path (default: out/<name>.bilingual.ass)"
    )
    parser.add_argument(
        "--backend",
        default=os.environ.get("TRANSLATE_BACKEND", "auto"),
        help="translation backend: auto (local Ollama→Claude), ollama, or claude "
             "(default: auto, or $TRANSLATE_BACKEND)",
    )
    parser.add_argument(
        "--no-clean",
        dest="clean",
        action="store_false",
        help="do not de-roll YouTube auto-captions before translating",
    )
    obs.add_verbose_arg(parser)
    args = parser.parse_args(argv)
    obs.configure(args.verbose)

    in_path = args.input
    if not Path(in_path).is_file():
        print(f"error: input not found: {in_path}", file=sys.stderr)
        return 2

    out_path = args.output or _default_out(in_path)
    try:
        backend = get_backend(args.backend)
        result = translate_file(
            in_path, out_path, backend, clean=args.clean,
            on_progress=obs.make_progress("translate", _log),
        )
    except Exception as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    print(f"wrote {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
