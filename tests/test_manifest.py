"""Tests for the per-run diagnostic manifest."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from orchestrate.flow import COMPLETED, DOWNLOAD_FAILED, FlowResult
from orchestrate.manifest import build_manifest, write_run_manifest


def _completed_result(out_path: Path) -> FlowResult:
    return FlowResult(
        url="https://youtu.be/abc",
        status=COMPLETED,
        download=SimpleNamespace(ok=True, video_path=Path("downloads/d/Chan/v.mp4")),
        translation=SimpleNamespace(ok=True, subtitle_source="asr"),
        compose=SimpleNamespace(ok=True, out_path=out_path),
        dub=SimpleNamespace(ok=True, voice="zh-CN-XiaoxiaoNeural",
                            out_path=out_path.with_name("v.final.dubbed.mp4"), error=None),
        publish=SimpleNamespace(ok=True, metadata_path=out_path.with_name("v.final.metadata.json")),
        engines={
            "download": "yt-dlp",
            "subtitle": "local · whisper:small",
            "translate": "local · ollama:qwen3.5:9b (3/3 chunks)",
            "dub": "online · edge-tts:zh-CN-XiaoxiaoNeural",
            "publish": "local · ollama:qwen3.5:9b",
        },
    )


def test_build_manifest_captures_engines_and_stages():
    m = build_manifest(_completed_result(Path("output/d/Chan/v.final.mp4")))

    assert m["status"] == COMPLETED
    assert m["engines"]["dub"] == "online · edge-tts:zh-CN-XiaoxiaoNeural"
    assert m["stages"]["dub"]["voice"] == "zh-CN-XiaoxiaoNeural"
    assert m["stages"]["translate"]["subtitle_source"] == "asr"
    assert "generated_at" in m


def test_write_run_manifest_sits_beside_final_video(tmp_path):
    out = tmp_path / "out" / "d" / "Chan" / "v.final.mp4"
    out.parent.mkdir(parents=True)

    path = write_run_manifest(_completed_result(out), tmp_path / "out")

    assert path == out.with_suffix(".run.json")  # v.final.run.json next to the video
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["engines"]["translate"].startswith("local · ollama")
    assert data["stages"]["publish"]["ok"] is True


def test_write_run_manifest_records_failures_too(tmp_path):
    # A dub that failed should be captured with its error, even on a run that
    # otherwise completed — this is the case worth debugging.
    result = _completed_result(tmp_path / "out" / "d" / "Chan" / "v.final.mp4")
    (tmp_path / "out" / "d" / "Chan").mkdir(parents=True)
    result = FlowResult(
        url=result.url, status=result.status, download=result.download,
        translation=result.translation, compose=result.compose,
        dub=SimpleNamespace(ok=False, voice="", out_path=None,
                            error="server unreachable"),
        engines={"download": "yt-dlp", "translate": "local · ollama:qwen3.5:9b"},
    )
    path = write_run_manifest(result, tmp_path / "out")
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["stages"]["dub"]["ok"] is False
    assert data["stages"]["dub"]["error"] == "server unreachable"
    assert "dub" not in data["engines"]  # never recorded an engine for a failed dub


def test_write_run_manifest_skips_when_nothing_located():
    # A download that never produced a file has no place to anchor the manifest.
    result = FlowResult(url="u", status=DOWNLOAD_FAILED,
                        download=SimpleNamespace(ok=False, video_path=None))
    assert write_run_manifest(result, "output") is None
