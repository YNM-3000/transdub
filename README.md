# Recreator

System to repurpose overseas (YouTube) videos for Chinese platforms:
monitor → notify → download → transcribe → translate → compose → dub → publish →
data. See `instruction.md` for the full spec.

The pipeline runs **local-first**: translation and publish metadata prefer a
local Ollama model and fall back to Claude; captions are transcribed locally
with Whisper when YouTube withholds them; the Chinese dub uses edge-tts (or
local Kokoro). Every backend is behind a small protocol, so cloud and local
engines are interchangeable.

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

### Local models (optional but preferred)

Translation and publish metadata prefer a local [Ollama](https://ollama.com)
model when the server is reachable, and otherwise use Claude.

```bash
ollama serve                     # start the local server
ollama pull qwen3.5:9b           # a Chinese-capable model (qwen recommended)
export OLLAMA_MODEL=qwen3.5:9b   # otherwise auto-picks a qwen/yi/glm/… model
```

Also good: `llama3.1:8b`, or Hunyuan-MT via
`ollama pull hf.co/mradermacher/Hunyuan-MT-7B-GGUF:Q4_K_M`. qwen tends to give
the best publish metadata.

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
uv run recreator-run "https://www.youtube.com/watch?v=VIDEO_ID"
```

Runs every stage end to end — **download → (transcribe if no captions) →
translate → compose → dub → publish → record metrics** — each retried on
transient failure. It prints the final metadata and a per-phase
**local-vs-cloud engine summary**:

```
engines (local vs cloud):
    download:   yt-dlp
    subtitle:   local · whisper:small        (or "YouTube captions")
    translate:  local · ollama:qwen3.5:9b (3/3 chunks)
    dub:        online · edge-tts:zh-CN-XiaoxiaoNeural
    publish:    local · ollama:qwen3.5:9b
```

Useful flags:

- `--no-dub` skip the Chinese voice dub (on by default)
- `--voice zh-CN-YunxiNeural` pick the dub voice
- `--backend auto|ollama|claude` translation engine (default `auto` =
  local-first with Claude fallback; publish metadata mirrors this)
- `--stop-after translate` halt at the human subtitle-review gate (then run
  `recreator-compose` / `recreator-dub` / `recreator-publish` after review)
- `--stop-after compose` stop before publishing
- `--no-publish` / `--no-data` skip those stages
- `--attempts N` / `--retry-delay S` tune the retry policy
- `--schedule SECONDS` (+ optional `--max-runs N`) repeat on an interval
- `-v` verbose (debug) logging

## Monitor channels + notify

Maintain a category-grouped watchlist (`channels.json`, see
`channels.example.json`), then scan for new and trending videos and email a
digest. Needs `YOUTUBE_API_KEY` and `SMTP_*` in `.env`.

```bash
uv run recreator-monitor --config channels.json            # scan + email
uv run recreator-monitor --config channels.json --dry-run  # scan + print only
uv run recreator-run --monitor --schedule 3600             # scan + email hourly
```

## Individual stages

Each stage is also a standalone command (run one, review, run the next):

```bash
# Download video + subtitles (+ info.json + thumbnail)
uv run recreator-download "https://www.youtube.com/watch?v=VIDEO_ID"

# Translate a subtitle → bilingual ASS (EN + 中文). --backend auto|ollama|claude
uv run recreator-translate samples/demo.srt -o out/demo.bilingual.ass

# Compose: burn bilingual subs into the video (--mode soft = MKV track;
# --preview N = fast N-second check before a full encode)
uv run recreator-compose video.mp4 video.bilingual.ass -o out/final.mp4

# Dub: replace audio with a Chinese voice, driven by the bilingual subtitle,
# writing <video>.dubbed.mp4 alongside the subtitled version
uv run recreator-dub out/final.mp4 video.bilingual.ass
uv run recreator-dub --list-voices          # list Chinese voices + where to preview
uv run recreator-dub --samples ./samples-out # synth one clip per voice to listen

# Publish: Chinese title/description/tags + a cover, into output/<date>/<channel>/
uv run recreator-publish out/final.mp4 -s video.bilingual.ass

# Data: record source vs. re-upload metrics and compare
uv run recreator-data record-source downloads
uv run recreator-data record-upload --source-id VIDEO_ID --platform bilibili --views 8200 --likes 430
uv run recreator-data show VIDEO_ID
```

## How captions, translation, and dubbing work

- **Captions**: YouTube increasingly withholds auto-captions without a PO
  token. When no subtitle downloads, the audio is transcribed locally with
  **Whisper** (`--extra asr`) into an English SRT that feeds translation — so
  caption-less videos still work. Auto-generated captions that *do* download
  use a "rolling" format (each cue repeats the previous line plus one new
  line); these are de-rolled before translation (`recreator-translate
  --no-clean` to disable).
- **Translation** uses a numbered-line text protocol (not JSON — robust to
  punctuation). `auto` runs a local Ollama model per chunk and falls back to
  Claude on any chunk it flubs.
- **Dubbing** synthesizes each Chinese line and fits it to its cue's time
  window (speed-up capped) so speech stays locked to the picture, then replaces
  the audio. The default (`auto`) uses **GPT-SoVITS channel-voice cloning** when
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
dubbed in the same cloned voice. Hand-pick a cleaner reference with
`--voice /path/clip.wav` (a sibling `clip.txt` supplies its transcript).

When GPT-SoVITS is used inside `recreator-run`, the local Ollama model is
unloaded first to free memory before the (heavier) dub.

GPT-SoVITS is heavy PyTorch, so it runs as its own local server (works on
Apple Silicon) and recreator talks to it over HTTP:

```bash
# one-time: set up GPT-SoVITS and download its pretrained models, then:
python api_v2.py                      # serves 127.0.0.1:9880 (see GPT-SoVITS docs)

# point recreator at it and dub:
export DUB_ENGINE=gpt-sovits          # or:  --dub-engine gpt-sovits
export GPT_SOVITS_URL=http://127.0.0.1:9880   # default
uv run recreator-run "https://www.youtube.com/watch?v=VIDEO_ID"
```

If the server isn't running, the dub stage fails per-video (non-fatal) with a
clear "server unreachable" message.

Downloading real YouTube subtitles requires browser cookies (bot check) and a
JS runtime such as `deno` (challenge solving); the pipeline handles this via
`--cookies-from-browser` and `--remote-components ejs:npm`.

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
  Claude + Ollama impls and a local-first `FallbackBackend`
- `compose/` — ffmpeg burn-in / soft-mux of bilingual subs into a final video
- `dub/` — Chinese TTS voice track (edge-tts / Kokoro `VoiceBackend`) fitted to
  the subtitle timeline, replacing the audio
- `publish/` — Chinese title/description/tags (`MetadataBackend`: Claude +
  Ollama, local-first) + cover frame
- `data/` — SQLite store of source vs. re-upload metric snapshots
- `monitor/` — YouTube Data API channel watch + new/trending detection + email
- `obs/` — terminal logging + single-line progress
- `orchestrate/` — wires the stages into one flow (`flow.run_full`) with a
  retry policy, an interval scheduler, and the engine summary; the seam a
  workflow framework would later replace
