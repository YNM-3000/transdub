"""Tests for the local dedicated-MT backend and auto MT preference (no network)."""

from __future__ import annotations

import pytest

from translate.ollama_mt_backend import OllamaMTBackend


def test_translate_chunk_one_to_one_and_ordered():
    table = {"hello": "你好", "world": "世界"}
    be = OllamaMTBackend(transport=lambda t: table[t], max_workers=2)
    assert be.translate_chunk(["hello", "world"], "ctx") == ["你好", "世界"]


def test_translate_chunk_preserves_blanks_and_count():
    be = OllamaMTBackend(transport=lambda t: "译", max_workers=1)
    assert be.translate_chunk(["a", "  ", "b"], "") == ["译", "", "译"]


def test_empty_translation_is_retried_then_raises():
    be = OllamaMTBackend(transport=lambda t: "   ", max_retries=2,
                         sleep=lambda _s: None, max_workers=1)
    with pytest.raises(RuntimeError, match="ollama-mt translation failed"):
        be.translate_chunk(["x"], "")


def test_describe_labels_hunyuan():
    be = OllamaMTBackend(model="hf.co/x/Hunyuan-MT-7B-GGUF:Q4_K_M", transport=lambda t: t)
    assert be.describe() == "local · hunyuan-mt"


def test_find_mt_model_detects_hunyuan():
    from translate.backend import _find_mt_model

    assert _find_mt_model(["qwen3.5:9b", "hf.co/x/Hunyuan-MT-7B-GGUF:Q4_K_M"]) \
        == "hf.co/x/Hunyuan-MT-7B-GGUF:Q4_K_M"
    assert _find_mt_model(["qwen3.5:9b", "llama3.1:8b"]) is None


def test_get_backend_hunyuan_and_auto_preference(monkeypatch):
    import translate.backend as be_mod
    from translate.backend import FallbackBackend, get_backend

    assert isinstance(get_backend("hunyuan"), OllamaMTBackend)

    # auto prefers the local MT model when one is pulled
    monkeypatch.setattr(
        "translate.ollama_backend.available_models",
        lambda *a, **k: ["qwen3.5:9b", "hf.co/x/Hunyuan-MT-7B-GGUF:Q4_K_M"],
    )
    auto = get_backend("auto")
    assert isinstance(auto, FallbackBackend)
    assert isinstance(auto._primary, OllamaMTBackend)
