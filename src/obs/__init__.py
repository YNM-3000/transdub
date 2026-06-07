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
