"""Tests for the backend resolver and the Claude backend (mocked client)."""

from __future__ import annotations

import pytest

from translate.backend import LengthMismatchError, get_backend
from translate.claude_backend import ClaudeBackend, _parse_numbered


class _TextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _Message:
    """A plain-text response carrying the model's numbered output."""

    def __init__(self, text: str) -> None:
        self.content = [_TextBlock(text)]


def _numbered(lines: list[str]) -> str:
    return "\n".join(f"{i + 1}. {line}" for i, line in enumerate(lines))


class FakeClient:
    """Stand-in for anthropic.Anthropic returning scripted text responses."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Message(self._responses.pop(0))


def _backend(responses, **kw):
    return ClaudeBackend(client=FakeClient(responses), sleep=lambda _s: None, **kw)


def test_translate_chunk_happy_path():
    backend = _backend([_numbered(["你好", "世界"])])
    out = backend.translate_chunk(["Hello", "World"], context="ctx")
    assert out == ["你好", "世界"]


def test_translate_chunk_empty_returns_empty_without_call():
    client = FakeClient([])
    backend = ClaudeBackend(client=client)
    assert backend.translate_chunk([], "") == []
    assert client.calls == []


def test_translate_chunk_retries_on_length_mismatch_then_succeeds():
    backend = _backend([_numbered(["只有一行"]), _numbered(["第一行", "第二行"])])
    out = backend.translate_chunk(["a", "b"], context="")
    assert out == ["第一行", "第二行"]


def test_translate_chunk_raises_after_exhausting_retries():
    backend = _backend([_numbered(["x"])] * 3, max_retries=3)
    with pytest.raises(RuntimeError):
        backend.translate_chunk(["a", "b"], context="")


def test_request_uses_cache_control_and_model():
    backend = _backend([_numbered(["t"])], model="claude-test")
    backend.translate_chunk(["x"], context="")
    call = backend.client.calls[0]
    assert call["model"] == "claude-test"
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_translate_chunk_tolerates_quotes_and_commas():
    # The exact content that broke JSON parsing now flows through unharmed.
    tricky = ['他说："这是,一个,测试"', "USB-C 的「真相」"]
    backend = _backend([_numbered(tricky)])
    assert backend.translate_chunk(["a", "b"], context="") == tricky


def test_parse_numbered_basic():
    assert _parse_numbered("1. 甲\n2. 乙", 2) == ["甲", "乙"]


def test_parse_numbered_ignores_preamble_and_blank_lines():
    text = "Here are the translations:\n\n1. 甲\n\n2. 乙\n"
    assert _parse_numbered(text, 2) == ["甲", "乙"]


def test_parse_numbered_folds_wrapped_continuation_lines():
    text = "1. first part\ncontinued here\n2. second"
    assert _parse_numbered(text, 2) == ["first part continued here", "second"]


def test_parse_numbered_raises_on_empty_line():
    # An empty translation (model merged it into a neighbour) must be rejected
    # so the backend retries / falls back, not silently produce a blank cue.
    with pytest.raises(LengthMismatchError):
        _parse_numbered("1. 甲\n2. \n3. 丙", 3)


def test_parse_numbered_raises_on_missing_index():
    with pytest.raises(LengthMismatchError):
        _parse_numbered("1. 甲\n3. 丙", 3)  # missing #2


def test_non_retryable_4xx_surfaces_immediately():
    class AuthError(Exception):
        status_code = 401

    class FailingClient:
        def __init__(self):
            self.messages = self
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            raise AuthError("unauthorized")

    client = FailingClient()
    backend = ClaudeBackend(client=client, sleep=lambda _s: None)
    with pytest.raises(AuthError):
        backend.translate_chunk(["a"], context="")
    assert client.calls == 1  # did not retry a 401


def test_length_mismatch_error_fields():
    err = LengthMismatchError(3, 2)
    assert err.expected == 3 and err.got == 2


def test_get_backend_resolves_claude_ollama_and_rejects_unknown():
    from translate.ollama_backend import OllamaBackend

    assert isinstance(get_backend("claude"), ClaudeBackend)
    assert isinstance(get_backend("ollama"), OllamaBackend)
    assert isinstance(get_backend("local"), OllamaBackend)
    with pytest.raises(ValueError):
        get_backend("nope")


def test_get_backend_auto_prefers_ollama_then_falls_back(monkeypatch):
    import translate.backend as backend_mod
    from translate.backend import FallbackBackend
    from translate.ollama_backend import OllamaBackend

    monkeypatch.setattr("translate.ollama_backend.ollama_available", lambda **k: True)
    auto = backend_mod.get_backend("auto")  # local primary, Claude fallback
    assert isinstance(auto, FallbackBackend)
    assert isinstance(auto._primary, OllamaBackend)
    assert isinstance(backend_mod.get_backend(""), FallbackBackend)  # default is auto

    monkeypatch.setattr("translate.ollama_backend.ollama_available", lambda **k: False)
    assert isinstance(backend_mod.get_backend("auto"), ClaudeBackend)


def test_ollama_backend_translates_via_transport():
    from translate.ollama_backend import OllamaBackend

    seen = {}

    def transport(user: str) -> str:
        seen["user"] = user
        return "1. 你好\n2. 世界"

    backend = OllamaBackend(model="qwen", transport=transport)
    assert backend.translate_chunk(["Hi", "World"], "ctx") == ["你好", "世界"]
    assert "1. Hi" in seen["user"] and "2. World" in seen["user"]


def test_ollama_backend_retries_on_length_mismatch():
    from translate.ollama_backend import OllamaBackend

    calls = {"n": 0}

    def transport(user: str) -> str:
        calls["n"] += 1
        return "1. 只有一行" if calls["n"] == 1 else "1. 甲\n2. 乙"

    backend = OllamaBackend(model="qwen", transport=transport, sleep=lambda _s: None)
    assert backend.translate_chunk(["a", "b"], "") == ["甲", "乙"]
    assert calls["n"] == 2


def test_fallback_backend_uses_primary_then_secondary():
    from translate.backend import FallbackBackend

    class Primary:
        def __init__(self):
            self.calls = 0

        def translate_chunk(self, cues, context):
            self.calls += 1
            raise RuntimeError("dropped a line")

    class Secondary:
        def translate_chunk(self, cues, context):
            return [f"译:{c}" for c in cues]

    made = {"n": 0}

    def make_secondary():
        made["n"] += 1
        return Secondary()

    primary = Primary()
    fb = FallbackBackend(primary, make_secondary)
    assert fb.translate_chunk(["a", "b"], "") == ["译:a", "译:b"]
    assert primary.calls == 1 and made["n"] == 1

    # Secondary is created lazily once and reused on the next fallback.
    fb.translate_chunk(["c"], "")
    assert made["n"] == 1


def test_fallback_backend_prefers_primary_when_it_succeeds():
    from translate.backend import FallbackBackend

    class Primary:
        def translate_chunk(self, cues, context):
            return ["本地"]

    def boom():
        raise AssertionError("secondary should not be built")

    fb = FallbackBackend(Primary(), boom)
    assert fb.translate_chunk(["x"], "") == ["本地"]


def test_ollama_pick_model_prefers_chinese_capable():
    from translate.ollama_backend import pick_model

    assert pick_model(["llama3:8b", "qwen3.5:9b"]) == "qwen3.5:9b"
    assert pick_model(["mistral:7b"]) == "mistral:7b"  # falls back to first
    assert pick_model([]) is None
