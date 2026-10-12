# Contributing to Transdub

Thanks for your interest! Contributions of all kinds are welcome.

## Development setup

```bash
uv sync --all-extras --dev   # install everything, including optional stages
uv run pytest                # tests need no network, API keys, or models
```

## Guidelines

- **Tests pass, with coverage.** Add tests for new behavior; the suite runs
  fully offline (subprocess runners, transports, and model backends are injected
  or stubbed — keep it that way so CI stays network-free).
- **Match the architecture.** Each stage is a small, pure-ish module under `src/`
  with a swappable backend behind a `Protocol` (`TranslationBackend`,
  `VoiceBackend`, `Transcriber`, `MetadataBackend`). New engines should implement
  the relevant protocol rather than branching existing code.
- **Keep files small and focused** (~200–400 lines), prefer immutable data, and
  handle errors explicitly.
- **Conventional commits**: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`,
  `chore:`, `perf:`, `ci:`.

## Scope & responsibility

Transdub is a localization tool for content you have the right to use. Please
don't contribute features whose primary purpose is to circumvent platform terms,
strip attribution, or enable republishing without permission. See the **Intended
use & your responsibility** section in the README.
