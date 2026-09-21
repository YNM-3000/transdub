"""Pure timeline planning: lay synthesized clips onto the video's timeline.

Kept free of ffmpeg so the fit/placement logic is unit-testable. Each cue's
clip is placed at the cue start; if the synthesized speech is longer than the
cue window it is sped up (bounded by MAX_TEMPO) rather than allowed to drift.
"""

from __future__ import annotations

from .models import Piece, VoiceCue

# Cap speed-up so fast lines stay intelligible; beyond this a clip may overrun
# its window slightly rather than turn into chipmunk speech. Chinese dubs of
# fast talkers routinely need >1.6x, so the cap sits at 2.0 (still intelligible
# for most voices) to keep drift from accumulating.
MAX_TEMPO = 2.0
_EPS = 0.001


def tempo_for(clip_seconds: float, target_seconds: float, max_tempo: float = MAX_TEMPO) -> float:
    """Speed factor to fit `clip_seconds` into `target_seconds` (>=1, capped)."""
    if target_seconds <= 0 or clip_seconds <= target_seconds:
        return 1.0
    return min(max_tempo, clip_seconds / target_seconds)


def plan_timeline(
    cues: list[VoiceCue],
    clip_durations: list[float],
    *,
    max_tempo: float = MAX_TEMPO,
) -> list[Piece]:
    """Build the ordered silence/clip pieces for the whole dub track.

    Cues are assumed sorted and non-overlapping (as ASS cues are). Each clip is
    fitted against the time remaining until *its own cue end* measured from the
    current running position — so when a previous clip overran, this one is
    compressed harder (up to the tempo cap) to absorb the drift rather than let
    it accumulate. When there's a gap before a cue, silence re-anchors the dub
    exactly to that cue's start.
    """
    pieces: list[Piece] = []
    position = 0.0
    for i, (cue, dur) in enumerate(zip(cues, clip_durations)):
        gap = cue.start - position
        if gap > _EPS:
            pieces.append(Piece("silence", gap))
            position += gap

        # Absorb any carried-over drift: fit into what's left of this window.
        target = max(_EPS, cue.end - position)
        tempo = tempo_for(dur, target, max_tempo)
        fitted = dur / tempo
        pieces.append(Piece("clip", fitted, clip_index=i, tempo=tempo))
        position += fitted
    return pieces
