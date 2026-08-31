"""Immutable data model for a transcription segment."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Segment:
    """One timed span of transcribed speech (seconds)."""

    start: float
    end: float
    text: str
