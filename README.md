# Transdub

**English** · [简体中文](README.zh-CN.md)

> Translate and dub foreign videos into Chinese, end to end — local-first.

Found a video you wish your Chinese-speaking friends could enjoy? Transdub turns
a foreign (YouTube) video into a share-ready Chinese version — accurate bilingual
subtitles *and* a natural Chinese voice-over — from a single command. It handles
the whole journey so you don't have to stitch tools together:

**download → transcribe → translate → compose → dub → publish**, then upload to
Bilibili as a separate, deliberate step. You pick the videos to process yourself
(channel monitoring exists but is optional — see below). See `instruction.md` for
the full spec.

It runs **local-first**, so you can do most of it on your own machine for free:
translation and publish text prefer a local Ollama model and fall back to Claude
only when needed; missing captions are transcribed locally with Whisper; and the
Chinese dub can use edge-tts, local Kokoro, or GPT-SoVITS voice cloning. Every
backend hides behind a small protocol, so local and cloud engines are drop-in
interchangeable.

> [!IMPORTANT]
> **Intended use & your responsibility.** Transdub is a localization tool for
> content you have the right to use — your own videos, or others' videos **with
> the creator's permission**. Downloading from YouTube may violate its Terms of
> Service, and re-uploading someone else's work without a licence infringes
> copyright, even with attribution. The project ships a permission-request
> workflow for exactly this reason: **ask first.** You are solely responsible for
> securing the rights to anything you process and publish, and for complying with
> the terms of every platform and model you use. The authors provide this
> software as-is and accept no liability for how it is used (see `LICENSE`).

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — Python 3.13+ environment/runner
- **ffmpeg** — audio/video processing (every media stage)
- **[deno](https://deno.com/)** — YouTube JS-challenge solving for downloads
- *Optional:* **[Ollama](https://ollama.com)** (local translation/metadata),
  a local **GPT-SoVITS** server (voice cloning), and an **Anthropic API key**
  (cloud fallback). Each is optional and degrades gracefully.

## Setup

```bash
uv sync                          # core deps
uv sync --extra asr              # + Whisper (faster-whisper) caption fallback
uv sync --extra dub              # + edge-tts Chinese dubbing
uv sync --extra dub-kokoro       # + local offline Kokoro voice (optional)
cp .env.example .env             # fill in keys (see below)
```

Everything except the core install is optional and degrades gracefully — a
missing extra just skips its stage with a warning.

### Models

**Translation** no longer uses an LLM — it uses dedicated machine translation
(online Google by default, or a local Hunyuan-MT), which translates per cue so
the line count never drifts. Chat models (qwen, llama) over-expand dense content
and drop/merge lines, so they're not used for translation. See `--backend`.

```bash
# Optional: local translation via a dedicated MT model (no cloud, auto-detected)
ollama pull hf.co/mradermacher/Hunyuan-MT-7B-GGUF:Q4_K_M
```

**Publish metadata** is the only LLM step. It defaults to a free local
**`qwen3.5:9b`** via [Ollama](https://ollama.com) (good Chinese metadata),
falling back to Claude if Ollama is unavailable. Override with `PUBLISH_MODEL` —
any Ollama model, local or a `:cloud` one (cloud models need `ollama signin` and,
for paid ones like `minimax-m3.1-flash:cloud`, usage credits):

```bash
ollama pull qwen3.5:9b                 # the default publish model (free, local)
# export PUBLISH_MODEL=gpt-oss:20b-cloud   # or a cloud model (ollama signin first)
```

### Environment (`.env`)

| Var | Used for |
|-----|----------|
| `ANTHROPIC_API_KEY` | Claude (translate/publish fallback, or when Ollama is off) |
| `YOUTUBE_API_KEY`, `SMTP_*` | monitor + email digest |
| `OLLAMA_MODEL`, `OLLAMA_HOST` | local translation/publish model + server |
| `WHISPER_MODEL` | Whisper ASR model (default `small`) |
| `DUB_ENGINE`, `DUB_VOICE`, `DUB_WORKERS` | dub engine / voice / concurrency |
| `KOKORO_MODEL`, `KOKORO_VOICES`, `KOKORO_VOICE` | local Kokoro voice files/voice |

## Full pipeline (one flow, with retries)

```bash
uv run transdub-run "https://www.youtube.com/watch?v=VIDEO_ID"
```

Runs every stage end to end — **download → (transcribe if no captions) →
translate → compose → dub → publish → record metrics** — each retried on
transient failure. It prints the final metadata and a per-phase
**local-vs-cloud engine summary**:

```
engines (local vs cloud):
    download:   yt-dlp
    subtitle:   YouTube captions            (or "local · whisper:small")
    translate:  online · google-translate
    dub:        online · edge-tts:zh-CN-XiaoxiaoNeural
    publish:    local · ollama:qwen3.5:9b
```

The same summary — plus each stage's status, the dub voice, and any errors — is
saved next to the output as **`<video>.final.run.json`** (a run manifest),
including for failed runs, so you can check which engine produced each phase when
something looks off later.

**Defaults** (opt out as noted): sentence-merge **on** (`--no-sentences`),
hardware compose **on** (`--no-hw`), Chinese voice dub **on** (`--no-dub`) via
**edge-tts** (`--dub-engine gpt-sovits|kokoro|auto` to change). So
`transdub-run <url>` already gives readable merged subtitles, a fast burn, and an
edge-tts dub. Add `--whisper` when you want the cleanest sentence boundaries.

Useful flags:

- `--no-sentences` translate per caption fragment instead of merging sentences
  (merge is **on** by default: more readable subtitles, better dub timing)
- `--no-hw` use the CPU x264 encoder instead of the hardware encoder (on by
  default: fast and not starved by other apps — important for long videos)
- `--no-dub` skip the Chinese voice dub (on by default, edge-tts)
- `--dub-engine edge|gpt-sovits|kokoro|auto` pick the dub engine (default `edge`)
- `--voice zh-CN-YunxiNeural` pick the dub voice
- `--backend auto|google|hunyuan|ollama|claude` translation engine. `auto`
  (default) prefers **free online Google MT** when reachable (faithful, concise,
  per-cue so the line count never drifts), falling back to a local engine
  offline; offline it uses a local Hunyuan-MT if pulled, else a chat model, then
  Claude. `google` / `hunyuan` force those dedicated MT engines; `ollama` /
  `claude` force a chat model. (Chat models over-expand dense content and can
  drop/merge lines — dedicated MT is more reliable.)
- `--whisper` transcribe the audio with Whisper even when captions exist.
  YouTube auto-captions have no punctuation, so sentence-merge can only split on
  pauses/length and may straddle sentences; Whisper restores punctuation, giving
  clean sentence boundaries. Needs the `asr` extra and is slower (writes
  `<video>.whisper.srt`).
- `--stop-after translate` halt at the human subtitle-review gate (then run
  `transdub-compose` / `transdub-dub` / `transdub-publish` after review)
- `--stop-after compose` stop before publishing
- `--no-publish` / `--no-data` skip those stages
- `--attempts N` / `--retry-delay S` tune the retry policy
- `--schedule SECONDS` (+ optional `--max-runs N`) repeat on an interval
- `-v` verbose (debug) logging

### Resuming an interrupted run

There's no separate resume command — **just run the same URL again**. The flow
keeps no checkpoint state, but every stage writes its output as a *sibling file*
next to the video and reuses it, so a re-run skips the work already done and
continues from where it stopped:

| Stage | Output reused on re-run |
|-------|-------------------------|
| download | existing `<video>.mp4` (yt-dlp skips the re-download; info JSON only) |
| subtitle | existing `<video>.en.srt` (Whisper won't re-transcribe) |
| translate | existing `<video>.bilingual.ass` is overwritten (cheap) |
| compose | `<video>.final.mp4` |
| dub | `<video>.final.dubbed.mp4` |

```bash
uv run transdub-run "https://www.youtube.com/watch?v=VIDEO_ID"   # picks up where it left off
```

Runs most often stop in the **dub** stage. If the default GPT-SoVITS engine runs
out of memory, continue with a lighter path:

```bash
uv run transdub-run "…VIDEO…" --dub-engine edge     # cloud edge-tts, no local model
uv run transdub-run "…VIDEO…" --stop-after compose  # finish the subtitled video, dub later
```

Once a subtitle exists (downloaded or Whisper-made), you can also resume by hand
with the individual stage commands below — there's no standalone transcribe
command, so a caption-less video needs one full-flow run first to generate the
`<video>.en.srt`.

## Publishing to Bilibili

The publish stage produces the metadata + cover; a separate command uploads the
finished video with [biliup](https://github.com/biliup/biliup). It's kept out of
the automated pipeline on purpose — uploading publishes to a real account, so you
run it deliberately after reviewing the result.

One-time setup: install biliup (standalone binary, `pip install biliup`, or
`cargo install biliup`) and log in once to create `cookies.json`:

```bash
biliup login          # scan the QR code in the Bilibili app
```

Then upload (defaults to a **dry run** that only prints the command — add
`--publish` to actually upload). It reads the sibling `<video>.metadata.json` and
`.cover.jpg`, and attributes the source as a repost (转载):

```bash
uv run transdub-upload "output/.../My Video.final.dubbed.mp4"            # dry run
uv run transdub-upload "output/.../My Video.final.dubbed.mp4" --publish  # upload
# --tid <id> category · --original (原创 instead of 转载) · --source <url> override
```

`transdub-run` prints the ready-to-run upload command in its completion summary.
Uploading the `.dubbed` video automatically uses the metadata + cover generated
beside the subtitled `.final` video.

## Monitor channels (optional)

Picking videos by hand is the default workflow — just pass URLs to `transdub-run`.
If you'd rather automate discovery, there's an optional channel monitor: maintain
a watchlist (`channels.json`, see `channels.example.json`) and scan for new and
trending videos, emailing a digest. Needs `YOUTUBE_API_KEY` and `SMTP_*` in
`.env`.

```bash
uv run transdub-monitor --config channels.json            # scan + email
uv run transdub-monitor --config channels.json --dry-run  # scan + print only
```

## Individual stages

Each stage is also a standalone command (run one, review, run the next):

```bash
# Download video + subtitles (+ info.json + thumbnail)
uv run transdub-download "https://www.youtube.com/watch?v=VIDEO_ID"

# Translate a subtitle → bilingual ASS (EN + 中文). --backend auto|ollama|claude
uv run transdub-translate samples/demo.srt -o out/demo.bilingual.ass

# Compose: burn bilingual subs into the video (--mode soft = MKV track;
# --preview N = fast N-second check before a full encode)
uv run transdub-compose video.mp4 video.bilingual.ass -o out/final.mp4

# Dub: replace audio with a Chinese voice, driven by the bilingual subtitle,
# writing <video>.dubbed.mp4 alongside the subtitled version
uv run transdub-dub out/final.mp4 video.bilingual.ass
uv run transdub-dub --list-voices          # list Chinese voices + where to preview
uv run transdub-dub --samples ./samples-out # synth one clip per voice to listen

# Publish: Chinese title/description/tags + a cover, into output/<date>/<channel>/
uv run transdub-publish out/final.mp4 -s video.bilingual.ass
# Upload the result to Bilibili (see "Publishing to Bilibili" above)
uv run transdub-upload out/final.dubbed.mp4            # dry run; --publish to upload

# Data: record source vs. re-upload metrics and compare
uv run transdub-data record-source downloads
uv run transdub-data record-upload --source-id VIDEO_ID --platform bilibili --views 8200 --likes 430
uv run transdub-data show VIDEO_ID
```

## How captions, translation, and dubbing work

- **Captions**: YouTube increasingly withholds auto-captions without a PO
  token. When no subtitle downloads, the audio is transcribed locally with
  **Whisper** (`--extra asr`) into an English SRT that feeds translation — so
  caption-less videos still work. Auto-generated captions that *do* download
  use a "rolling" format (each cue repeats the previous line plus one new
  line); these are de-rolled before translation (`transdub-translate
  --no-clean` to disable).
- **Translation** has two engine shapes. *Chat models* (qwen/llama via Ollama,
  or Claude) use a numbered-line text protocol (not JSON — robust to punctuation)
  and translate a chunk at a time; bad responses (dropped, blank, or repeated
  lines) are detected and retried/failed-over. *Dedicated MT* (Hunyuan-MT locally,
  or Google online) translates **one cue at a time**, so the line count can never
  drift — far more reliable on dense material, which is why `auto` prefers a
  pulled Hunyuan-MT. Pass **`--sentences`** to merge caption fragments into whole
  sentences first — more readable, and better input for every engine.
- **Dubbing** first **merges the caption fragments into whole sentences** (the
  bilingual subtitle is chopped into ~2s reading windows mid-sentence, which
  dubs badly), synthesizes each sentence, and fits it to its time window
  (speed-up capped at 2.0×). Fitting is measured against the time left to each
  cue's end, so a line that overran is compressed to **absorb the drift** rather
  than let it accumulate — speech stays locked to the picture even on fast
  talkers. Then it replaces the audio. The default (`auto`) uses **GPT-SoVITS
  channel-voice cloning** when
  its server is reachable (see below), otherwise **edge-tts** (`zh-CN-Xiaoxiao`,
  synthesized concurrently to hide network latency); local **Kokoro** is the
  offline option (`DUB_ENGINE=kokoro`, needs `--extra dub-kokoro` + Kokoro model
  files). Pick explicitly with `--dub-engine` / `$DUB_ENGINE`.

### Voice cloning — dub in the channel's own voice (GPT-SoVITS)

GPT-SoVITS clones the **original creator's voice** for the Chinese dub, and is
the **default engine** when its server is reachable (`auto` falls back to
edge-tts otherwise). A short reference clip is cut automatically from the source
audio (using a mid-video subtitle window as the transcript) and cached per
channel under `models/refs/<channel>.wav`, so every video from a channel is
dubbed in the same cloned voice.

To use a **custom voice**, register any audio/video clip once — it extracts a
short reference, auto-transcribes it with Whisper, and stores it under
`models/refs/` (needs `--extra asr`):

```bash
uv run transdub-dub --register "clip.mp4" [--name MyVoice]
uv run transdub-run "…VIDEO…" --voice MyVoice     # reuse by name
```

Or hand-pick a reference inline with `--voice /path/clip.wav` (a sibling
`clip.txt` supplies its transcript, `clip.lang` its language).

When GPT-SoVITS is used inside `transdub-run`, the local Ollama model is
unloaded first to free memory before the (heavier) dub.

GPT-SoVITS is heavy PyTorch, so it runs as its own local server (works on
Apple Silicon) and transdub talks to it over HTTP:

```bash
# one-time: set up GPT-SoVITS and download its pretrained models, then:
python api_v2.py                      # serves 127.0.0.1:9880 (see GPT-SoVITS docs)

# point transdub at it and dub:
export DUB_ENGINE=gpt-sovits          # or:  --dub-engine gpt-sovits
export GPT_SOVITS_URL=http://127.0.0.1:9880   # default
uv run transdub-run "https://www.youtube.com/watch?v=VIDEO_ID"
```

If the server isn't running, the dub stage fails per-video (non-fatal) with a
clear "server unreachable" message.

Downloading real YouTube subtitles requires browser cookies (bot check) and a
JS runtime such as `deno` (challenge solving); the pipeline handles this via
`--cookies-from-browser` and `--remote-components ejs:npm`.

**If downloads fail with `The page needs to be reloaded.`** (or a similar
`[youtube]` extraction error), yt-dlp is out of date — YouTube changes its
player regularly and only recent yt-dlp releases can solve the new challenge.
Update it and retry:

```bash
uv lock --upgrade-package yt-dlp && uv sync
```

(Already-downloaded videos are reused from disk, so a re-run of an interrupted
flow never hits this — see "Resuming an interrupted run" above.)

## Tests

```bash
uv run pytest                    # all tests (no network/API/model needed)
```

## Architecture

Feature-named packages live under `src/` (code separate from runtime dirs like
`downloads/`, `output/`, `models/`); `tests/` is at the repo root. Each stage
is a pure-ish function with clear inputs/outputs and a swappable backend
behind a protocol, so the flow can later move onto a workflow framework.

- `download/` — yt-dlp wrapper → video + subtitles (+ info.json, thumbnail)
- `transcribe/` — Whisper ASR fallback → English SRT when captions are missing
- `translate/` — subtitle → bilingual ASS; `TranslationBackend` protocol with
  chat impls (Claude, Ollama) and per-cue dedicated-MT impls (Hunyuan-MT local,
  Google online), wired local-first via `FallbackBackend`
- `compose/` — ffmpeg burn-in / soft-mux of bilingual subs into a final video
- `dub/` — Chinese TTS voice track (edge-tts / Kokoro `VoiceBackend`) fitted to
  the subtitle timeline, replacing the audio
- `publish/` — Chinese title/description/tags (`MetadataBackend`: Claude +
  Ollama, local-first) + cover frame + a `biliup` upload wrapper (`transdub-upload`)
- `data/` — SQLite store of source vs. re-upload metric snapshots
- `monitor/` — YouTube Data API channel watch + new/trending detection + email
- `obs/` — terminal logging + single-line progress
- `orchestrate/` — wires the stages into one flow (`flow.run_full`) with a
  retry policy, an interval scheduler, and the engine summary; the seam a
  workflow framework would later replace

## Contributing

Issues and PRs welcome — see `CONTRIBUTING.md`. Tests need no network, API keys,
or models: `uv run pytest`.

## License

[MIT](LICENSE). Note the **Intended use & your responsibility** section above —
the licence covers the software, not the rights to any video you process.
