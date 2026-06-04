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

## Monitor channels + notify

Maintain a category-grouped watchlist (`channels.json`, see
`channels.example.json`), then scan for new and trending videos and email a
digest. Needs `YOUTUBE_API_KEY` and `SMTP_*` in `.env`.

```bash
uv run recreator-monitor --config channels.json            # scan + email
uv run recreator-monitor --config channels.json --dry-run  # scan + print only
```

## Full pipeline (one flow, with retries)

```bash
uv run recreator-run "https://www.youtube.com/watch?v=VIDEO_ID"
```

Runs every stage end to end — download → translate → compose → publish → record
metrics — each retried on transient failure. Useful flags:

- `--stop-after translate` halt at the human subtitle-review gate (then run
  `recreator-compose` / `recreator-publish` after review)
- `--stop-after compose` stop before publishing
- `--no-publish` / `--no-data` skip those stages
- `--attempts N` / `--retry-delay S` tune the retry policy
- `--schedule SECONDS` (+ optional `--max-runs N`) repeat on an interval

Run a scheduled monitor scan instead of processing URLs:

```bash
uv run recreator-run --monitor --schedule 3600        # scan + email hourly
```

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

Generate the upload package (Chinese title/description/tags + a cover frame)
into `output/<date>/<channel>/`:

```bash
uv run recreator-publish video.mp4 -s video.bilingual.ass
```

Track metrics — ingest source data from the downloaded info.json, record your
upload's numbers, and compare:

```bash
uv run recreator-data record-source downloads
uv run recreator-data record-upload --source-id VIDEO_ID --platform bilibili --views 8200 --likes 430
uv run recreator-data show VIDEO_ID
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
- `publish/` — Chinese title/description/tags (pluggable LLM) + cover frame
- `data/` — SQLite store of source vs. re-upload metric snapshots
- `monitor/` — YouTube Data API channel watch + new/trending detection + email digest
- `orchestrate/` — wires the stages into one flow (`flow.run_full`) with a
  retry policy and an interval scheduler; the seam a workflow framework would
  later replace
