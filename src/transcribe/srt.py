"""Write transcription segments to an SRT file (via pysubs2, already a dep)."""

from __future__ import annotations

from pathlib import Path

import pysubs2

from .models import Segment


def write_srt(segments: list[Segment], out_path: str | Path) -> Path:
    """Write `segments` to `out_path` as SRT and return the path.

    Empty/whitespace segments are dropped; raises ValueError if nothing usable
    remains (a silent or music-only clip yields no translatable subtitle).
    """
    subs = pysubs2.SSAFile()
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        subs.append(
            pysubs2.SSAEvent(
                start=int(seg.start * 1000),
                end=int(seg.end * 1000),
                text=text,
            )
        )
    if not subs:
        raise ValueError("no speech transcribed")

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    subs.save(str(out), format_="srt")
    return out
