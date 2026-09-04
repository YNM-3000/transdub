"""Discover and sample available Chinese voices."""

from __future__ import annotations

import asyncio
from pathlib import Path

# Chinese voices shipped in Kokoro's voices-v1.0.bin (zf_ = female, zm_ = male).
KOKORO_CHINESE_VOICES = [
    "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
    "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
]

SAMPLE_TEXT = "大家好，这是中文配音的声音示例，希望你会喜欢。"


def edge_chinese_voices() -> list[tuple[str, str]]:
    """(ShortName, description) for edge-tts zh voices; [] if edge-tts absent."""
    try:
        import edge_tts
    except ImportError:
        return []
    voices = asyncio.run(edge_tts.list_voices())
    out = [
        (v.get("ShortName", ""), f"{v.get('Gender', '')} · {v.get('FriendlyName', '')}")
        for v in voices
        if v.get("ShortName", "").startswith("zh-")
    ]
    return sorted(out)


def write_samples(voices: list[str], make_backend, out_dir: str | Path,
                  text: str = SAMPLE_TEXT) -> list[Path]:
    """Synthesize `text` in each voice into `out_dir`; return written paths.

    `make_backend(voice)` returns a VoiceBackend for that voice.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for voice in voices:
        path = out / f"{voice}.wav"
        try:
            make_backend(voice).synthesize(text, path)
            written.append(path)
        except Exception:  # skip a voice that fails, keep going
            continue
    return written
