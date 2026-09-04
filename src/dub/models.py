"""Immutable models for the dub stage."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class VoiceCue:
    """One line of the dub script with its target time window (seconds)."""

    start: float
    end: float
    text: str


@dataclass(frozen=True, slots=True)
class Piece:
    """One segment of the assembled dub timeline.

    kind == "silence": a gap of `seconds`.
    kind == "clip":    synthesized clip `clip_index`, time-stretched by `tempo`
                       (>1 speeds it up to fit the cue window).
    """

    kind: str
    seconds: float
    clip_index: int = -1
    tempo: float = 1.0


@dataclass(frozen=True, slots=True)
class DubResult:
    """Outcome of dubbing one video."""

    video_path: Path
    out_path: Path
    ok: bool
    voice: str = ""
    error: str | None = None
