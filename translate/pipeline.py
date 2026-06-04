"""Orchestrate: load subtitle → chunk → translate → bilingual ASS.

Depends only on the `TranslationBackend` abstraction, so it is trivially
testable with a fake backend and unaffected by which engine is used.
"""

from __future__ import annotations

from pathlib import Path

from .backend import TranslationBackend
from .models import Cue
from .styler import build_bilingual
from .subtitle import chunk_cues, load_cues


def translate_cues(cues: list[Cue], backend: TranslationBackend) -> list[str]:
    """Translate every cue, preserving order and one-to-one mapping."""
    translations: list[str] = []
    for chunk in chunk_cues(cues):
        source = [c.text for c in chunk.cues]
        translated = backend.translate_chunk(source, chunk.context)
        if len(translated) != len(source):
            raise RuntimeError(
                f"backend returned {len(translated)} lines for {len(source)} cues"
            )
        translations.extend(translated)
    return translations


def translate_file(
    in_path: str | Path,
    out_path: str | Path,
    backend: TranslationBackend,
) -> Path:
    """Translate a subtitle file and write a bilingual ASS to `out_path`."""
    cues = load_cues(in_path)
    if not cues:
        raise ValueError(f"no usable cues found in {in_path}")

    translations = translate_cues(cues, backend)
    subs = build_bilingual(cues, translations)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    subs.save(str(out))
    return out
