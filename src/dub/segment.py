"""Merge caption fragments into whole-sentence dub cues.

Auto-caption windows are chopped into ~2-second fragments mid-sentence, which
is fine for reading but terrible for dubbing: each fragment is synthesized and
time-fitted on its own, so a dense fragment hits the tempo cap, overruns, and
pushes every later clip back (cumulative drift). Merging consecutive fragments
into sentence-level cues gives the TTS natural prosody and averages out the
per-fragment length mismatch, so the dub stays anchored to the picture.

This only regroups the dub script; the burned subtitle keeps its own fragments.
"""

from __future__ import annotations

from .models import VoiceCue

# Chinese/…/Latin sentence terminators. A cue ending on one of these closes the
# current sentence; otherwise fragments keep accreting.
_ENDERS = "。！？…!?"
# Never let a merged cue span longer than this — keeps the dub re-anchoring to
# the picture often enough, and bounds any single clip's catch-up burden.
MAX_SPAN_SECONDS = 12.0


def merge_into_sentences(
    cues: list[VoiceCue], *, max_span: float = MAX_SPAN_SECONDS
) -> list[VoiceCue]:
    """Merge consecutive cues into sentence-level cues.

    A sentence is flushed when the accumulated text ends on a terminator, or
    when adding the next fragment would exceed `max_span`. The merged cue spans
    from the first fragment's start to the last fragment's end, so it stays
    anchored where the sentence actually begins.
    """
    merged: list[VoiceCue] = []
    buf: VoiceCue | None = None
    for cue in cues:
        if buf is None:
            buf = cue
            continue
        ends_sentence = buf.text[-1:] in _ENDERS
        too_long = (cue.end - buf.start) > max_span
        if ends_sentence or too_long:
            merged.append(buf)
            buf = cue
        else:
            buf = VoiceCue(buf.start, cue.end, buf.text + cue.text)
    if buf is not None:
        merged.append(buf)
    return merged
