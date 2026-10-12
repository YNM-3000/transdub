"""Tiny observability helper: configure terminal logging for the CLIs.

Stages log under the ``transdub.*`` namespace via stdlib logging; the CLIs
call ``configure()`` to route those to stderr (so stdout result lines stay
clean). INFO shows stage notices + percentages; ``--verbose`` adds DEBUG.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

ROOT = "transdub"

# Non-TTY (piped/background) progress is logged one line at a time; only emit
# every Nth percent so a long stage doesn't spew hundreds of near-identical
# lines into a file log.
_LOG_STEP = 10


def _fmt_duration(seconds: float) -> str:
    """mm:ss (or h:mm:ss past an hour) — compact elapsed/ETA for progress."""
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


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


def make_progress(
    label: str,
    log: logging.Logger | None = None,
    *,
    step: int = _LOG_STEP,
    clock=time.monotonic,
):
    """Return a progress sink `fn(pct, detail="")`.

    On a terminal it rewrites a single line (`\\r{label}: {pct}% {detail}
    [elapsed<eta]`), clearing to end-of-line so a shrinking detail leaves no
    stale text, and finishing with a newline at 100%. The ETA is a simple linear
    projection from elapsed time and percent, matching tqdm's `[mm:ss<mm:ss]`.

    When stderr isn't a TTY (piped/background), it logs instead — but only every
    `step` percent (and at 100%), so a long stage doesn't flood the file log with
    hundreds of near-identical lines.
    """
    sink_log = log or logger("progress")
    is_tty = sys.stderr.isatty()
    start: float | None = None
    last_logged = -step  # so the first update always emits a baseline line

    def progress(pct: int, detail: str = "") -> None:
        nonlocal start, last_logged
        now = clock()
        if start is None:
            start = now
        elapsed = now - start
        suffix = f" {detail}" if detail else ""

        if is_tty:
            if 0 < pct < 100:
                eta = elapsed * (100 - pct) / pct
                timing = f" [{_fmt_duration(elapsed)}<{_fmt_duration(eta)}]"
            elif pct >= 100:
                timing = f" [{_fmt_duration(elapsed)}]"
            else:
                timing = ""
            end = "\n" if pct >= 100 else ""
            # \033[K clears from the cursor to the end of the line.
            sys.stderr.write(f"\r{label}: {pct}%{suffix}{timing}\033[K{end}")
            sys.stderr.flush()
        elif pct >= 100:
            last_logged = pct
            sink_log.info("%s: %d%%%s (%s)", label, pct, suffix, _fmt_duration(elapsed))
        elif pct - last_logged >= step:
            last_logged = pct
            sink_log.info("%s: %d%%%s", label, pct, suffix)

    return progress
