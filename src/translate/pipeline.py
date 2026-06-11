"""Orchestrate: load subtitle → chunk → translate → bilingual ASS.

Depends only on the `TranslationBackend` abstraction, so it is trivially
testable with a fake backend and unaffected by which engine is used.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from .backend import TranslationBackend
from .models import Cue
from .styler import build_bilingual
from .subtitle import chunk_cues, load_cues

log = logging.getLogger("recreator.translate")

ProgressFn = Callable[[int], None]


def translate_cues(
    cues: list[Cue],
    backend: TranslationBackend,
    *,
    on_progress: ProgressFn | None = None,
) -> list[str]:
    """Translate every cue, preserving order and one-to-one mapping.

    `on_progress(pct)` receives the per-chunk completion percentage.
    """
    chunks = chunk_cues(cues)
    total = len(chunks)
    log.info("translate: %d cues in %d chunks", len(cues), total)
    translations: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        source = [c.text for c in chunk.cues]
        translated = backend.translate_chunk(source, chunk.context)
        if len(translated) != len(source):
            raise RuntimeError(
                f"backend returned {len(translated)} lines for {len(source)} cues"
            )
        translations.extend(translated)
        log.debug("translate: chunk %d/%d", i, total)
        if on_progress is not None:
            on_progress(round(i * 100 / total))
    return translations


def translate_file(
    in_path: str | Path,
    out_path: str | Path,
    backend: TranslationBackend,
    clean: bool = True,
    *,
    on_progress: ProgressFn | None = None,
) -> Path:
    """Translate a subtitle file and write a bilingual ASS to `out_path`.

    `clean` de-rolls YouTube auto-captions before translating (see load_cues).
    """
    cues = load_cues(in_path, clean=clean)
    if not cues:
        raise ValueError(f"no usable cues found in {in_path}")

    translations = translate_cues(cues, backend, on_progress=on_progress)
    subs = build_bilingual(cues, translations)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    subs.save(str(out))
    return out
