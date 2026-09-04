"""Command-line entry point: dub a video with a Chinese voice."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

import obs
from .backend import get_voice_backend
from .pipeline import dub_video
from .voices import KOKORO_CHINESE_VOICES, SAMPLE_TEXT, edge_chinese_voices, write_samples

_log = obs.logger("dub")


def _list_voices() -> int:
    edge = edge_chinese_voices()
    if edge:
        print("edge-tts Chinese voices (use with --voice):")
        for short, desc in edge:
            print(f"    {short:<28} {desc}")
    else:
        print("edge-tts not installed (uv sync --extra dub).")
    print("\nKokoro Chinese voices (when Kokoro is configured):")
    print("    " + ", ".join(KOKORO_CHINESE_VOICES))
    print(
        "\nListen online without installing anything:\n"
        "    edge-tts / Azure voices: https://speech.microsoft.com/portal/voicegallery\n"
        "    Kokoro demo:             https://huggingface.co/spaces/hexgrad/Kokoro-TTS"
    )
    return 0


def _write_samples(out_dir: str, text: str) -> int:
    from .edge_backend import EdgeBackend

    voices = [s for s, _ in edge_chinese_voices()]
    if not voices:
        print("error: edge-tts not installed (uv sync --extra dub)", file=sys.stderr)
        return 2
    print(f"synthesizing {len(voices)} voice samples into {out_dir}/ …")
    written = write_samples(voices, lambda v: EdgeBackend(voice=v), out_dir, text)
    print(f"✓ wrote {len(written)} samples — open the folder and listen, then pass --voice <name>")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="recreator-dub",
        description="Replace a video's audio with a Chinese TTS voice, driven by "
                    "the bilingual subtitle. Writes <video>.dubbed.<ext> alongside it.",
    )
    parser.add_argument("video", nargs="?", help="the (final) video file to dub")
    parser.add_argument("subtitle", nargs="?", help="bilingual .ass subtitle (the dub script)")
    parser.add_argument("-o", "--output", help="explicit output path")
    parser.add_argument("--voice", help="override the voice (engine-specific)")
    parser.add_argument(
        "--list-voices", action="store_true",
        help="list available Chinese voices (and where to listen) and exit",
    )
    parser.add_argument(
        "--samples", metavar="DIR",
        help="synthesize a short clip in every edge-tts Chinese voice into DIR and exit",
    )
    parser.add_argument("--sample-text", default=SAMPLE_TEXT, help="text for --samples")
    obs.add_verbose_arg(parser)
    args = parser.parse_args(argv)
    obs.configure(args.verbose)

    if args.list_voices:
        return _list_voices()
    if args.samples:
        return _write_samples(args.samples, args.sample_text)

    if not (args.video and args.subtitle):
        print("error: video and subtitle are required (or use --list-voices)", file=sys.stderr)
        return 2

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
