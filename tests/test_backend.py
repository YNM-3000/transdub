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


def test_get_backend_resolves_claude_and_rejects_unknown():
    assert isinstance(get_backend("claude"), ClaudeBackend)
    assert isinstance(get_backend(""), ClaudeBackend)  # defaults to claude
    with pytest.raises(ValueError):
        get_backend("nope")
