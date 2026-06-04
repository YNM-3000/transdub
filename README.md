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

## Download + translate (end to end)

```bash
uv run recreator-run "https://www.youtube.com/watch?v=VIDEO_ID"
```

Downloads the video + subtitles into `downloads/<date>/<channel>/`, then
translates them, writing `*.bilingual.ass` next to the video. Accepts multiple
URLs (parallel downloads via `--jobs`).

## Individual stages

Download only:

```bash
uv run recreator-download "https://www.youtube.com/watch?v=VIDEO_ID"
```

Translate an existing subtitle:

```bash
uv run recreator-translate samples/demo.srt -o out/demo.bilingual.ass
```

Compose the final video (burn the bilingual subs into the frames; `--mode
soft` muxes a selectable ASS track into MKV instead). Use `--preview N` for a
fast N-second check before a full encode:

```bash
uv run recreator-compose video.mp4 video.bilingual.ass -o out/final.mp4
```

The translation backend is pluggable (`--backend`, default `claude`). A local
LLM backend can be added later without touching the pipeline or CLI.

YouTube **auto-generated captions** use a "rolling" format (each cue repeats
the previous line plus one new line). These are de-rolled into clean,
sequential cues before translation; pass `--no-clean` to disable.

To obtain a real subtitle to test with (YouTube now requires browser cookies
to pass its bot check, and a JS runtime such as `deno` for challenge solving):

```bash
yt-dlp --cookies-from-browser chrome --ignore-no-formats-error \
  --write-subs --write-auto-subs --sub-lang en --skip-download \
  --convert-subs srt -o "samples/%(title)s.%(ext)s" <youtube_url>
```

## Tests

```bash
uv run pytest --cov=translate
```

## Architecture

Flat, feature-named top-level packages (no `src/` nesting). Each stage is a
pure function with clear inputs/outputs so the flow can later move onto a
workflow framework. Future stages (`monitor/`, `dubbing/`, `compose/`, …) join
as sibling packages.

- `download/` — yt-dlp wrapper → video + subtitles, parallel downloads
- `translate/` — subtitle → bilingual ASS
  - `models.py` immutable `Cue`/`Chunk`; `subtitle.py` load + de-roll + chunk;
    `backend.py` `TranslationBackend` protocol; `claude_backend.py` Claude impl;
    `styler.py` bilingual ASS; `pipeline.py` orchestration; `cli.py` entry point
- `compose/` — ffmpeg burn-in / soft-mux of bilingual subs into a final video
- `orchestrate/` — composes the stages (download → translate handoff); the seam
  a workflow framework would later replace
