"""Tiny observability helper: configure terminal logging for the CLIs.

Stages log under the ``recreator.*`` namespace via stdlib logging; the CLIs
call ``configure()`` to route those to stderr (so stdout result lines stay
clean). INFO shows stage notices + percentages; ``--verbose`` adds DEBUG.
"""

from __future__ import annotations

import argparse
import logging
import sys

ROOT = "recreator"


def configure(verbose: bool = False) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger(ROOT)
    root.handlers[:] = [handler]
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.propagate = False


def add_verbose_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="show debug logs"
    )


def logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{ROOT}.{name}")


def make_progress(label: str, log: logging.Logger | None = None):
    """Return a progress sink `fn(pct, detail="")`.

    On a terminal it rewrites a single line (`\\r{label}: {pct}% {detail}`),
    clearing to end-of-line so a shrinking detail leaves no stale text, and
    finishing with a newline at 100%. When stderr isn't a TTY (piped/background),
    it falls back to one log line per update so file logs stay readable.
    """
    sink_log = log or logger("progress")
    is_tty = sys.stderr.isatty()

    def progress(pct: int, detail: str = "") -> None:
        suffix = f" {detail}" if detail else ""
        if is_tty:
            end = "\n" if pct >= 100 else ""
            # \033[K clears from the cursor to the end of the line.
            sys.stderr.write(f"\r{label}: {pct}%{suffix}\033[K{end}")
            sys.stderr.flush()
        else:
            sink_log.info("%s: %d%%%s", label, pct, suffix)

    return progress
