# Recreator

System to repurpose overseas (YouTube) videos for Chinese platforms:
monitor → notify → download → translate → calibrate → review → (dubbing) →
upload → data. See `instruction.md` for the full spec.

**Current status: validation phase.** The first validated slice is the
**translator** — it turns a source subtitle into a bilingual ASS file
(English on top, slightly larger Chinese below).

## Setup

```bash
uv sync
cp .env.example .env   # then fill in ANTHROPIC_API_KEY
```

## Translate a subtitle

```bash
uv run recreator-translate samples/demo.srt -o out/demo.bilingual.ass
```

The translation backend is pluggable (`--backend`, default `claude`). A local
LLM backend can be added later without touching the pipeline or CLI.

To obtain a real subtitle to test with:

```bash
yt-dlp --write-auto-subs --skip-download --sub-lang en -o "samples/%(title)s" <youtube_url>
```

## Tests

```bash
uv run pytest --cov=translate
```

## Architecture

Flat, feature-named top-level packages (no `src/` nesting). The translator
lives in `translate/`; future stages (`download/`, `monitor/`, `dubbing/`,
`compose/`, …) join as sibling packages. Each stage is a pure function with
clear inputs/outputs so the pipeline can later move onto a workflow framework.

- `translate/models.py` — immutable `Cue` / `Chunk`
- `translate/subtitle.py` — load + chunk (pysubs2)
- `translate/backend.py` — `TranslationBackend` protocol + resolver
- `translate/claude_backend.py` — Claude implementation
- `translate/styler.py` — bilingual ASS builder
- `translate/pipeline.py` — orchestration
- `translate/cli.py` — CLI entry point
