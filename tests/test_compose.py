"""Compose stage tests using a fake ffmpeg runner (no encoding)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from compose.ffmpeg import (
    build_burn_command,
    build_soft_command,
    compose,
    default_output,
)
from compose.models import BURN, SOFT


@pytest.fixture
def media(tmp_path):
    video = tmp_path / "Clip.mp4"
    video.write_bytes(b"video")
    subs = tmp_path / "Clip.bilingual.ass"
    subs.write_text("[Script Info]\n", encoding="utf-8")
    return video, subs


class FakeRunner:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr
        self.calls = []

    def __call__(self, cmd, cwd=None):
        self.calls.append((cmd, cwd))
        return SimpleNamespace(returncode=self.returncode, stdout="", stderr=self.stderr)


def test_default_output_extensions():
    assert default_output("a/b/Clip.mp4", BURN).name == "Clip.final.mp4"
    assert default_output("a/b/Clip.mp4", SOFT).name == "Clip.final.mkv"


def test_build_burn_command_uses_relative_safe_sub_and_reencodes():
    cmd = build_burn_command(Path("/v/Clip.mp4"), Path("/o/out.mp4"), crf=18, preset="fast")
    assert "-vf" in cmd and "ass=subtitle.ass" in cmd  # relative safe name
    assert cmd[cmd.index("-crf") + 1] == "18"
    assert cmd[cmd.index("-preset") + 1] == "fast"
    assert cmd[cmd.index("-c:a") + 1] == "copy"  # audio passthrough


def test_build_burn_command_preview_inserts_duration():
    cmd = build_burn_command(Path("/v.mp4"), Path("/o.mp4"), preview_seconds=15)
    assert cmd[cmd.index("-t") + 1] == "15"


def test_build_soft_command_muxes_ass_track_without_reencode():
    cmd = build_soft_command(Path("/v.mp4"), Path("/s.ass"), Path("/o.mkv"))
    assert cmd[cmd.index("-c:s") + 1] == "ass"
    assert cmd[cmd.index("-c:v") + 1] == "copy"


def test_compose_burn_success_runs_from_tempdir(media):
    video, subs = media
    runner = FakeRunner()
    res = compose(video, subs, mode=BURN, runner=runner)

    assert res.ok and res.mode == BURN
    assert res.out_path == video.with_suffix(".final.mp4")
    cmd, cwd = runner.calls[0]
    assert cwd is not None  # burn runs from the temp dir holding the safe-named sub
    assert "ass=subtitle.ass" in cmd


def test_compose_soft_success(media):
    video, subs = media
    runner = FakeRunner()
    res = compose(video, subs, mode=SOFT, runner=runner)
    assert res.ok and res.out_path.suffix == ".mkv"
    _, cwd = runner.calls[0]
    assert cwd is None  # soft mux needs no temp dir


def test_compose_propagates_ffmpeg_failure(media):
    video, subs = media
    res = compose(video, subs, mode=BURN, runner=FakeRunner(returncode=1, stderr="boom"))
    assert not res.ok
    assert "boom" in res.error


def test_compose_rejects_unknown_mode(media):
    video, subs = media
    res = compose(video, subs, mode="weird", runner=FakeRunner())
    assert not res.ok
    assert "unknown mode" in res.error


def test_compose_writes_to_explicit_output(media, tmp_path):
    video, subs = media
    out = tmp_path / "nested" / "final.mp4"
    res = compose(video, subs, out, mode=BURN, runner=FakeRunner())
    assert res.out_path == out
    assert out.parent.is_dir()  # parent created


def test_cli_missing_input_returns_2(media, monkeypatch):
    from compose import cli

    video, subs = media
    assert cli.main([str(video), str(subs / "nope.ass")]) == 2


def test_cli_success(media, monkeypatch, capsys):
    from compose import cli
    from compose.models import ComposeResult

    video, subs = media
    monkeypatch.setattr(
        cli, "compose",
        lambda *a, **k: ComposeResult(video, subs, video.with_suffix(".final.mp4"), BURN, ok=True),
    )
    rc = cli.main([str(video), str(subs)])
    assert rc == 0
    assert "final.mp4" in capsys.readouterr().out
