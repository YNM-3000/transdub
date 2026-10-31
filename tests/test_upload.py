"""Tests for the Bilibili upload (biliup) integration — no network, no biliup."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from publish.upload import build_upload_command, upload_video


META = {
    "title": "测试标题",
    "description": "测试简介",
    "tags": ["标签A", "标签B"],
    "source": {"url": "https://www.youtube.com/watch?v=abc"},
}


def test_build_command_repost_includes_source_and_fields():
    cmd = build_upload_command(
        "v.mp4", META, cover="v.cover.jpg", cookies="cookies.json", tid=188,
    )
    joined = " ".join(cmd)
    assert cmd[0] == "biliup" and "upload" in cmd
    assert "--title" in cmd and "测试标题" in cmd
    assert "--tag" in cmd and "标签A,标签B" in cmd
    assert "--cover" in cmd and "v.cover.jpg" in cmd
    assert "--copyright 2" in joined                      # 转载 by default
    assert "--source https://www.youtube.com/watch?v=abc" in joined
    assert cmd[-1] == "v.mp4"                              # video is the positional tail


def test_build_command_original_omits_source():
    cmd = build_upload_command("v.mp4", META, copyright=1)
    assert "--copyright 1" in " ".join(cmd)
    assert "--source" not in cmd


def test_build_command_repost_requires_a_source():
    with pytest.raises(ValueError, match="source URL is required"):
        build_upload_command("v.mp4", {"title": "t", "tags": []})  # no source


def test_upload_video_dry_run_builds_without_running(tmp_path):
    video = tmp_path / "v.final.mp4"
    video.write_bytes(b"x")
    (tmp_path / "v.final.metadata.json").write_text(json.dumps(META), encoding="utf-8")

    called = []
    result = upload_video(video, dry_run=True, runner=lambda c: called.append(c))

    assert result.ok and called == []            # nothing executed on a dry run
    assert "--copyright" in result.command


def test_upload_video_runs_and_parses_bvid(tmp_path):
    video = tmp_path / "v.final.mp4"
    video.write_bytes(b"x")
    (tmp_path / "v.final.metadata.json").write_text(json.dumps(META), encoding="utf-8")
    cookies = tmp_path / "cookies.json"
    cookies.write_text("{}")

    def runner(cmd):
        return SimpleNamespace(returncode=0, stdout="submitted BV1xy4y1z7AB ok", stderr="")

    result = upload_video(video, cookies=cookies, dry_run=False, runner=runner)
    assert result.ok and result.bvid == "BV1xy4y1z7AB"


def test_upload_video_errors_without_credentials(tmp_path):
    video = tmp_path / "v.final.mp4"
    video.write_bytes(b"x")
    (tmp_path / "v.final.metadata.json").write_text(json.dumps(META), encoding="utf-8")

    result = upload_video(video, cookies=tmp_path / "missing.json", dry_run=False)
    assert not result.ok and "credentials" in result.error
