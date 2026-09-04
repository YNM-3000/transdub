"""Dubbing stage: replace the original voice with a Chinese TTS voice.

Uses the reviewed bilingual subtitle as the script — each Chinese cue is
synthesized, fitted to its cue's time window (so speech stays locked to the
picture), and assembled into one audio track that replaces the original.
The TTS engine sits behind a `VoiceBackend` protocol (Kokoro local, edge-tts
fallback), mirroring the translate/transcribe backends.
"""
