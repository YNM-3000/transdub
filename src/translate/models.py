"""Immutable data models for the translation slice."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class Cue:
    """A single subtitle cue.

    Times are in milliseconds, matching pysubs2's internal representation.
    `index` is the cue's 0-based position among kept cues (see load_cues).
    """

    index: int
    start_ms: int
    end_ms: int
    text: str

    def with_text(self, text: str) -> "Cue":
        """Return a copy of this cue with replaced text (immutable update)."""
        return replace(self, text=text)


@dataclass(frozen=True, slots=True)
class Chunk:
    """A contiguous group of cues sent to the backend as one translation unit.

    `cues` are the cues to translate. `lead` / `trail` are neighbouring cues
    included only as context to keep translations coherent across boundaries;
    they are not re-translated.
    """

    cues: tuple[Cue, ...]
    lead: tuple[Cue, ...] = ()
    trail: tuple[Cue, ...] = ()

    @property
    def context(self) -> str:
        """Surrounding text (lead + trail only) for coherence.

        Excludes `cues` themselves — those go in the translate list, so
        repeating them here would only invite the model to echo the source.
        """
        parts = [c.text for c in (*self.lead, *self.trail)]
        return "\n".join(parts)
