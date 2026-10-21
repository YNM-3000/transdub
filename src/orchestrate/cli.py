"""Single entry point: run the pipeline (or a monitor scan), optionally scheduled."""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

import obs
from data.store import DataStore
from download.downloader import DEFAULT_FORMAT
from monitor.cli import main as monitor_main
from dub.backend import get_voice_backend
from publish.backend import get_metadata_backend
from publish.render import format_package
from transcribe.backend import get_transcriber
from translate.backend import get_backend

from .flow import AWAITING_REVIEW, COMPLETED, run_full
from .manifest import write_run_manifest
from .retry import RetryPolicy
from .scheduler import run_periodically


_ENGINE_ORDER = ("download", "subtitle", "translate", "dub", "publish")


def _print_engines(engines: dict) -> None:
    if not engines:
        return
    print("─" * 60)
    print("engines (local vs cloud):")
    for phase in _ENGINE_ORDER:
        if phase in engines:
            print(f"    {phase + ':':<11} {engines[phase]}")
    print("─" * 60)


def _print_flow(result) -> None:
    if result.status == COMPLETED:
        print(f"✓ {result.url} [completed]")
        if result.compose:
            print(f"    video:    {result.compose.out_path}")
        if result.dub and result.dub.ok:
            print(f"    dubbed:   {result.dub.out_path}  [{result.dub.voice}]")
        if result.publish and result.publish.metadata:
            print(format_package(result.publish))
        _print_engines(result.engines)
    elif result.status == AWAITING_REVIEW:
        subs = result.translation.ass_path if result.translation else None
        print(f"⏸ {result.url} [awaiting review]  subs: {subs}")
        _print_engines(result.engines)
    else:
        print(f"✗ {result.url} [{result.status}]  {result.error}", file=sys.stderr)


def _run_monitor(args) -> int:
    extra = ["--dry-run"] if args.dry_run else []
    return monitor_main(["--config", args.config, "--db", args.db, *extra])


def _run_pipeline(args) -> int:
    try:
        backend = get_backend(args.backend)
        metadata_backend = None if args.no_publish else get_metadata_backend(args.backend)
    except Exception as err:
        print(f"error: {err}", file=sys.stderr)
        return 2

    transcriber = None
    if not args.no_asr:
        transcriber = get_transcriber()
        if transcriber is None:
            print(
                "warning: faster-whisper not installed; videos without captions "
                "will be skipped. Install with: uv sync --extra asr",
                file=sys.stderr,
            )

    voice_backend = None
    voice_server = None
    if not args.no_dub:
        voice_backend = get_voice_backend(args.voice, args.dub_engine)
        if voice_backend is None:
            print(
                "warning: no voice backend available; skipping dub. Install with: "
                "uv sync --extra dub  (edge-tts) or set up Kokoro.",
                file=sys.stderr,
            )
        elif getattr(voice_backend, "name", "") == "gpt-sovits":
            from dub.server import VoiceServer  # auto-start/stop the local server

            voice_server = VoiceServer()

    policy = RetryPolicy(attempts=args.attempts, base_delay=args.retry_delay)
    download_kwargs = {
        "base_dir": "downloads",
        "fmt": DEFAULT_FORMAT,
        "cookies_browser": args.cookies_browser or None,
    }
    store = None if args.no_data else DataStore(args.db)

    failures = 0
    try:
        for url in args.urls:
            result = run_full(
                url,
                backend=backend,
                metadata_backend=metadata_backend,
                transcriber=transcriber,
                voice_backend=voice_backend,
                voice_server=voice_server,
                policy=policy,
                output_dir=args.output_dir,
                store=store,
                stop_after=args.stop_after,
                download_kwargs=download_kwargs,
            )
            _print_flow(result)
            manifest = write_run_manifest(result, args.output_dir)
            if manifest is not None:
                print(f"    run info: {manifest}")
            failures += 0 if result.ok else 1
    finally:
        if store is not None:
            store.close()
        if voice_server is not None:
            voice_server.close()  # auto-stop the server if we started it
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="transdub-run",
        description="Run the transdub pipeline end to end, or a monitor scan; optionally scheduled.",
    )
    parser.add_argument("urls", nargs="*", help="video URLs to process")
    parser.add_argument("--monitor", action="store_true", help="run a channel monitor scan instead")
    parser.add_argument("--config", default="channels.json", help="monitor watchlist (with --monitor)")
    parser.add_argument("--db", default="transdub.db", help="state/metrics SQLite path")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument(
        "--backend", default="auto",
        help="translate backend: auto (local Ollama→Claude), ollama, or claude "
             "(publish metadata always uses Claude)",
    )
    parser.add_argument(
        "--stop-after", choices=["translate", "compose"],
        help="halt early (translate = stop at the human review gate)",
    )
    parser.add_argument("--no-publish", action="store_true", help="skip the publish stage")
    parser.add_argument("--no-data", action="store_true", help="skip recording metrics")
    parser.add_argument(
        "--no-asr", action="store_true",
        help="don't transcribe audio when captions are missing (skip such videos)",
    )
    parser.add_argument(
        "--no-dub", action="store_true",
        help="don't produce the Chinese-voice dubbed variant (on by default)",
    )
    parser.add_argument(
        "--voice",
        help="edge/kokoro: a voice name (e.g. zh-CN-YunxiNeural); "
             "gpt-sovits: a reference-clip path (default: auto-cut channel voice)",
    )
    parser.add_argument(
        "--dub-engine",
        help="dub engine: gpt-sovits, edge, or kokoro "
             "(default: auto = GPT-SoVITS if its server is up, else edge)",
    )
    parser.add_argument("--attempts", type=int, default=3, help="retry attempts per stage")
    parser.add_argument("--retry-delay", type=float, default=2.0, help="base retry backoff (seconds)")
    parser.add_argument("--cookies-browser", default="chrome")
    parser.add_argument("--schedule", type=float, metavar="SECONDS", help="repeat on this interval")
    parser.add_argument("--max-runs", type=int, help="stop after N scheduled runs")
    parser.add_argument("--dry-run", action="store_true", help="(monitor) print digest without emailing")
    obs.add_verbose_arg(parser)
    args = parser.parse_args(argv)
    obs.configure(args.verbose)

    if args.monitor:
        task = lambda: _run_monitor(args)  # noqa: E731
    else:
        if not args.urls:
            print("error: provide URLs to process, or use --monitor", file=sys.stderr)
            return 2
        task = lambda: _run_pipeline(args)  # noqa: E731

    if args.schedule:
        print(f"scheduling every {args.schedule:g}s"
              + (f" for {args.max_runs} run(s)" if args.max_runs else ""))
        run_periodically(
            task, args.schedule, max_runs=args.max_runs,
            on_error=lambda exc: print(f"run error: {exc}", file=sys.stderr),
        )
        return 0
    return task()


if __name__ == "__main__":
    raise SystemExit(main())
