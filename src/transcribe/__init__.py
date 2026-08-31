"""Speech-to-text fallback: generate subtitles when YouTube captions are absent.

Many YouTube videos now withhold their auto-captions unless a PO token is
presented (see the download stage). Rather than depend on that fragile,
server-backed token flow, this package transcribes the downloaded audio
locally with Whisper and emits an SRT the translate stage can consume — so a
caption-less video is still repurposable, and so are videos that genuinely
have no captions at all.

The Whisper engine is behind a `Transcriber` Protocol and lazily imported, so
the core install and the test suite never need the heavy dependency.
"""
