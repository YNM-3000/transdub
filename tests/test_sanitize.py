"""Tests for translator-note stripping."""

from __future__ import annotations

from translate.sanitize import strip_translator_notes


def test_removes_note_parenthetical():
    assert strip_translator_notes("你好（注：这是一个说明）世界") == "你好世界"


def test_removes_halfwidth_and_translator_markers():
    assert strip_translator_notes("A(注:foo)B") == "AB"
    assert strip_translator_notes("X（译注：bar）Y") == "XY"


def test_handles_nested_brackets_in_note():
    text = "开始（注：某说明（如“Foo”）继续）结束"
    assert strip_translator_notes(text) == "开始结束"


def test_keeps_legitimate_parentheticals():
    assert strip_translator_notes("这个测试（很重要）保留") == "这个测试（很重要）保留"


def test_collapses_stray_double_spaces_and_trims():
    assert strip_translator_notes("  hello（注：x）  world  ") == "hello world"


def test_plain_text_unchanged():
    assert strip_translator_notes("普通的一行字幕") == "普通的一行字幕"


def test_strips_meta_commentary_about_garbled_source():
    # The exact failure seen in a dub: MT hedging about garbled ASR input.
    note = "（此处内容似乎不完整或存在语法错误……）根据相关法规"
    assert strip_translator_notes(note) == "根据相关法规"
    assert strip_translator_notes("开启SSO（原文如此）功能") == "开启SSO功能"
