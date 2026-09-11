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


def _register_voice(media: str, name: str | None) -> int:
    from pathlib import Path

    from transcribe.backend import get_transcriber
    from .reference import register_reference

    if not Path(media).is_file():
        print(f"error: not found: {media}", file=sys.stderr)
        return 2
    transcriber = get_transcriber(language=None)  # auto-detect the speaker's language
    if transcriber is None:
        print("error: faster-whisper not installed (uv sync --extra asr)", file=sys.stderr)
        return 2

    print(f"registering reference voice from {media} …")
    wav, transcript, lang = register_reference(media, transcriber, name=name)
    print(f"✓ registered '{wav.stem}' ({lang})")
    print(f"    clip: {wav}")
    print(f"    text: {transcript}")
    print(f'    use:  recreator-dub … --voice "{wav.stem}"')
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
    parser.add_argument(
        "--voice",
        help="edge/kokoro: a voice name; gpt-sovits: a reference-clip path "
             "(default: auto-cut channel voice)",
    )
    parser.add_argument(
        "--engine",
        help="voice engine: gpt-sovits, edge, or kokoro "
             "(default: auto = GPT-SoVITS if its server is up, else edge)",
    )
    parser.add_argument(
        "--list-voices", action="store_true",
        help="list available Chinese voices (and where to listen) and exit",
    )
    parser.add_argument(
        "--samples", metavar="DIR",
        help="synthesize a short clip in every edge-tts Chinese voice into DIR and exit",
    )
    parser.add_argument("--sample-text", default=SAMPLE_TEXT, help="text for --samples")
    parser.add_argument(
        "--register", metavar="MEDIA",
        help="register MEDIA (audio/video) as a reusable GPT-SoVITS reference "
             "voice under models/refs/, then exit (use later via --voice <name>)",
    )
    parser.add_argument("--name", help="name for --register (default: the file name)")
    obs.add_verbose_arg(parser)
    args = parser.parse_args(argv)
    obs.configure(args.verbose)

    if args.list_voices:
        return _list_voices()
    if args.samples:
        return _write_samples(args.samples, args.sample_text)
    if args.register:
        return _register_voice(args.register, args.name)

    if not (args.video and args.subtitle):
        print("error: video and subtitle are required (or use --list-voices)", file=sys.stderr)
        return 2

    for path in (args.video, args.subtitle):
        if not Path(path).is_file():
            print(f"error: not found: {path}", file=sys.stderr)
            return 2

    backend = get_voice_backend(args.voice, args.engine)
    if backend is None:
        print(
            "error: no voice backend available. Install one with: "
            "uv sync --extra dub   (edge-tts) or set up Kokoro model files.",
            file=sys.stderr,
        )
        return 2

    # GPT-SoVITS: auto-start its server if down, and stop it when we're done.
    server = None
    if getattr(backend, "name", "") == "gpt-sovits":
        from .server import VoiceServer

        server = VoiceServer()
        server.ensure()

    try:
        result = dub_video(
            args.video, args.subtitle, backend, args.output,
            on_progress=obs.make_progress("dub", _log),
        )
    finally:
        if server is not None:
            server.close()

    if not result.ok:
        print(f"✗ dub failed\n    {result.error}", file=sys.stderr)
        return 1
    print(f"✓ {result.out_path}  [{result.voice}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
