"""Tests for the publish package terminal renderer."""

from __future__ import annotations

from pathlib import Path

from publish.models import PublishMetadata, PublishPackage
from publish.render import format_package


def _pkg(description="line one\n\nline two", **over):
    meta = PublishMetadata(
        title="标题",
        description=description,
        tags=("甲", "乙"),
        category="生活技巧",
    )
    return PublishPackage(
        video_path=Path("v.mp4"),
        ok=True,
        metadata=meta,
        metadata_path=Path("m.json"),
        cover_path=Path("c.jpg"),
        **over,
    )


def test_format_package_includes_all_fields_and_raw_description():
    out = format_package(_pkg())
    assert "✓ 标题" in out
    assert "category: 生活技巧" in out
    assert "甲, 乙" in out
    assert "m.json" in out and "c.jpg" in out
    # Description printed raw with its real newlines (copy-pasteable).
    assert "line one\n\nline two" in out
    assert "description:" in out


def test_format_package_omits_description_block_when_empty():
    out = format_package(_pkg(description="   "))
    assert "description:" not in out
    assert "✓ 标题" in out


def test_format_package_failure():
    pkg = PublishPackage(video_path=Path("v.mp4"), ok=False, error="boom")
    out = format_package(pkg)
    assert "✗ publish failed" in out and "boom" in out
