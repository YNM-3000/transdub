"""Publish stage tests: metadata parsing, cover, packaging (no API/ffmpeg)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from publish.backend import get_metadata_backend
from publish.claude_backend import ClaudeMetadataBackend, _parse_metadata
from publish.content import chinese_from_ass
from publish.cover import cover_timestamp, extract_cover, probe_duration
from publish.models import PublishMetadata
from publish.package import build_package, mirrored_dir
from publish.source import SourceInfo, attribution_block, find_info_json


# --- metadata parsing / Claude backend ---------------------------------------

SAMPLE = """\
TITLE: USB-C 的真相：为什么苹果被迫妥协
TAGS: USB-C, 苹果, 数码, 充电线, 科技
DESCRIPTION:
一个关于 USB-C 接口的科普视频。
讲解了它如何统一了混乱的线缆世界。
"""


def test_parse_metadata_extracts_all_sections():
    md = _parse_metadata(SAMPLE)
    assert md.title == "USB-C 的真相：为什么苹果被迫妥协"
    assert md.tags == ("USB-C", "苹果", "数码", "充电线", "科技")
    assert "统一了混乱的线缆世界" in md.description


def test_parse_metadata_handles_chinese_punctuation_separators():
    text = "TITLE: 标题\nTAGS: 甲、乙，丙\nDESCRIPTION:\n正文"
    md = _parse_metadata(text)
    assert md.tags == ("甲", "乙", "丙")


def test_parse_metadata_raises_without_title():
    with pytest.raises(ValueError):
        _parse_metadata("TAGS: a, b\nDESCRIPTION:\nx")


class _Msg:
    def __init__(self, text):
        self.content = [SimpleNamespace(text=text)]


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Msg(self._responses.pop(0))


def test_claude_backend_generate_happy_path():
    backend = ClaudeMetadataBackend(client=FakeClient([SAMPLE]), sleep=lambda _s: None)
    md = backend.generate("What Exactly Is USB-C", "一些中文内容")
    assert md.title.startswith("USB-C")
    assert len(md.tags) == 5


def test_claude_backend_retries_then_succeeds():
    bad = "no labels here"
    backend = ClaudeMetadataBackend(
        client=FakeClient([bad, SAMPLE]), sleep=lambda _s: None
    )
    md = backend.generate("t", "c")
    assert md.title.startswith("USB-C")


def test_get_metadata_backend_resolves_and_rejects():
    assert isinstance(get_metadata_backend("claude"), ClaudeMetadataBackend)
    with pytest.raises(ValueError):
        get_metadata_backend("nope")


# --- content extraction ------------------------------------------------------

def test_chinese_from_ass_takes_top_line(tmp_path):
    ass = tmp_path / "b.ass"
    ass.write_text(
        "[Script Info]\n\n[V4+ Styles]\n"
        "Format: Name\nStyle: Default\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        r"Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,{\fs22}你好世界\N{\fs13}hello world"
        "\n",
        encoding="utf-8",
    )
    assert chinese_from_ass(ass) == "你好世界"


# --- cover -------------------------------------------------------------------

def test_cover_timestamp_explicit_value_wins():
    assert cover_timestamp(Path("v.mp4"), 42.0, runner=None) == 42.0


def test_cover_timestamp_uses_fraction_of_duration():
    runner = lambda cmd: SimpleNamespace(returncode=0, stdout="100.0\n", stderr="")
    assert cover_timestamp(Path("v.mp4"), None, runner=runner) == 30.0


def test_cover_timestamp_falls_back_when_probe_fails():
    runner = lambda cmd: SimpleNamespace(returncode=0, stdout="not-a-number", stderr="")
    assert cover_timestamp(Path("v.mp4"), None, runner=runner) == 10.0


def test_extract_cover_builds_command_and_writes(tmp_path):
    calls = []

    def runner(cmd):
        calls.append(cmd)
        Path(cmd[-1]).write_bytes(b"jpg")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    out = tmp_path / "sub" / "cover.jpg"
    ok, err = extract_cover(Path("/v.mp4"), out, 12.5, runner)
    assert ok and err is None and out.is_file()
    assert calls[0][calls[0].index("-ss") + 1] == "12.5"


def test_extract_cover_reports_failure(tmp_path):
    runner = lambda cmd: SimpleNamespace(returncode=1, stdout="", stderr="bad")
    ok, err = extract_cover(Path("/v.mp4"), tmp_path / "c.jpg", 1.0, runner)
    assert not ok and "bad" in err


# --- packaging ---------------------------------------------------------------

class FakeBackend:
    def __init__(self):
        self.calls = []

    def generate(self, source_title, content):
        self.calls.append((source_title, content))
        return PublishMetadata("中文标题", "简介内容", ("标签1", "标签2"))


@pytest.fixture
def final_video(tmp_path):
    folder = tmp_path / "output" / "2026-06-04" / "Zeus"
    folder.mkdir(parents=True)
    video = folder / "Clip.final.mp4"
    video.write_bytes(b"video")
    return video


def _cover_runner():
    def runner(cmd):
        if cmd[0] == "ffmpeg":
            Path(cmd[-1]).write_bytes(b"jpg")
        return SimpleNamespace(returncode=0, stdout="120.0\n", stderr="")
    return runner


def test_mirrored_dir_mirrors_date_channel():
    got = mirrored_dir(Path("downloads/2026-06-04/Zeus/Clip.mp4"), "output")
    assert got == Path("output/2026-06-04/Zeus")


def test_build_package_writes_metadata_and_cover(final_video, tmp_path):
    backend = FakeBackend()
    pkg = build_package(
        final_video,
        "一些中文字幕内容",
        backend=backend,
        output_dir=tmp_path / "pub",
        runner=_cover_runner(),
    )

    assert pkg.ok
    assert pkg.metadata.title == "中文标题"
    assert pkg.metadata_path.is_file()
    data = json.loads(pkg.metadata_path.read_text(encoding="utf-8"))
    assert data["title"] == "中文标题"
    assert data["tags"] == ["标签1", "标签2"]
    assert data["source_title"] == "Clip.final"
    assert pkg.cover_path is not None and pkg.cover_path.is_file()
    # Output mirrors <date>/<channel>.
    assert pkg.metadata_path.parent == tmp_path / "pub" / "2026-06-04" / "Zeus"


def test_build_package_appends_source_attribution(final_video, tmp_path):
    source = SourceInfo(
        url="https://youtu.be/abc",
        title="What Exactly Is USB-C",
        uploader="Zeus",
        upload_date="20250115",
    )
    pkg = build_package(
        final_video, "内容", backend=FakeBackend(),
        source=source, output_dir=tmp_path / "p", runner=_cover_runner(),
    )
    assert pkg.ok
    desc = pkg.metadata.description
    assert "—— 原视频信息 ——" in desc
    assert "原标题：What Exactly Is USB-C" in desc
    assert "UP主：Zeus" in desc
    assert "发布日期：2025-01-15" in desc  # YYYYMMDD formatted
    assert "原链接：https://youtu.be/abc" in desc
    data = json.loads(pkg.metadata_path.read_text(encoding="utf-8"))
    assert data["source"]["url"] == "https://youtu.be/abc"


def test_build_package_metadata_failure_is_returned(final_video, tmp_path):
    class Boom:
        def generate(self, *a):
            raise RuntimeError("api down")

    pkg = build_package(final_video, "c", backend=Boom(), output_dir=tmp_path / "p")
    assert not pkg.ok and "api down" in pkg.error


def test_build_package_cover_failure_is_nonfatal(final_video, tmp_path):
    def runner(cmd):
        # probe ok, ffmpeg fails
        rc = 1 if cmd[0] == "ffmpeg" else 0
        return SimpleNamespace(returncode=rc, stdout="100.0\n", stderr="x")

    pkg = build_package(
        final_video, "c", backend=FakeBackend(), output_dir=tmp_path / "p", runner=runner
    )
    assert pkg.ok  # metadata still produced
    assert pkg.cover_path is None
    assert pkg.metadata_path.is_file()


# --- source attribution ------------------------------------------------------

def test_source_info_from_ytdlp_json(tmp_path):
    info = tmp_path / "Clip.info.json"
    info.write_text(json.dumps({
        "webpage_url": "https://youtu.be/x", "title": "T",
        "channel": "Ch", "upload_date": "20240102",
    }), encoding="utf-8")
    src = SourceInfo.from_ytdlp_json(info)
    assert src.url == "https://youtu.be/x"
    assert src.uploader == "Ch"
    assert src.upload_date == "20240102"


def test_attribution_block_omits_missing_fields():
    block = attribution_block(SourceInfo(url="u", title="t"))
    assert "原标题：t" in block and "原链接：u" in block
    assert "UP主" not in block and "发布日期" not in block


def test_find_info_json_matches_by_stem_prefix(tmp_path):
    (tmp_path / "Clip.info.json").write_text("{}", encoding="utf-8")
    (tmp_path / "Other.info.json").write_text("{}", encoding="utf-8")
    subtitle = tmp_path / "Clip.bilingual.ass"
    subtitle.write_text("x", encoding="utf-8")
    assert find_info_json(subtitle).name == "Clip.info.json"


def test_find_info_json_returns_none_when_absent(tmp_path):
    assert find_info_json(tmp_path / "nope.ass", None) is None


# --- CLI ---------------------------------------------------------------------

def test_cli_missing_video_returns_2():
    from publish import cli

    assert cli.main(["/no/such.mp4"]) == 2


def test_cli_success(final_video, monkeypatch, capsys):
    from publish import cli
    from publish.models import PublishPackage

    pkg = PublishPackage(
        final_video, ok=True,
        metadata=PublishMetadata("标题", "简介", ("a", "b")),
        metadata_path=final_video.with_suffix(".metadata.json"),
        cover_path=final_video.with_suffix(".cover.jpg"),
    )
    monkeypatch.setattr(cli, "get_metadata_backend", lambda name: object())
    monkeypatch.setattr(cli, "build_package", lambda *a, **k: pkg)

    rc = cli.main([str(final_video)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "标题" in out and "a, b" in out
