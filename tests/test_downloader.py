"""Downloader tests using a fake yt-dlp runner (no network, no real process)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from download.downloader import (
    DEFAULT_FORMAT,
    build_command,
    download_many,
    download_one,
    _find_subtitle,
    _parse_info,
)


def _proc(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class FakeRunner:
    """Simulates yt-dlp: writes the output files and prints info JSON.

    Honors the `-o` template so produced paths match what download_one expects.
    """

    def __init__(self, *, channel="Cool Channel", title="My Video"):
        self.channel = channel
        self.title = title
        self.commands: list[list[str]] = []

    def __call__(self, cmd: list[str]):
        self.commands.append(cmd)
        url = cmd[-1]
        tmpl = cmd[cmd.index("-o") + 1]  # "<base>/<day>/%(channel)s/%(title)s.%(ext)s"
        root = tmpl.split("/%(channel)s/")[0]
        folder = Path(root) / self.channel
        folder.mkdir(parents=True, exist_ok=True)
        video = folder / f"{self.title}.mp4"
        video.write_bytes(b"fake-video")
        (folder / f"{self.title}.en.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n")
        info = {
            "id": "vid123",
            "title": self.title,
            "channel": self.channel,
            "webpage_url": url,
            "view_count": 4200,
            "like_count": 99,
            "duration": 612,
            "upload_date": "20260101",
            "requested_downloads": [{"filepath": str(video)}],
        }
        return _proc(stdout="[youtube] noise\n" + json.dumps(info))


def test_build_command_encodes_structure_and_flags():
    cmd = build_command("URL", "downloads", "2026-06-04", DEFAULT_FORMAT, "chrome")
    assert cmd[-1] == "URL"
    assert "--remote-components" in cmd and "ejs:npm" in cmd
    assert ["--cookies-from-browser", "chrome"] == cmd[cmd.index("--cookies-from-browser") : cmd.index("--cookies-from-browser") + 2]
    out = cmd[cmd.index("-o") + 1]
    assert out == "downloads/2026-06-04/%(channel)s/%(title)s.%(ext)s"
    assert "--dump-json" in cmd and "--no-simulate" in cmd
    assert "--write-info-json" in cmd  # source-metadata sidecar for publish


def test_build_command_omits_cookies_when_disabled():
    cmd = build_command("URL", "downloads", "2026-06-04", DEFAULT_FORMAT, None)
    assert "--cookies-from-browser" not in cmd


def test_download_one_success(tmp_path):
    runner = FakeRunner()
    res = download_one(
        "https://yt/watch?v=vid123",
        base_dir=tmp_path / "downloads",
        day="2026-06-04",
        runner=runner,
    )
    assert res.ok
    assert res.video_path.is_file()
    assert res.subtitle_path.name == "My Video.en.srt"
    assert res.subtitle_path.is_file()
    assert res.info.channel == "Cool Channel"
    assert res.info.view_count == 4200
    assert res.info.duration_s == 612
    # Directory structure: <base>/<day>/<channel>/
    assert res.video_path.parent.name == "Cool Channel"
    assert res.video_path.parent.parent.name == "2026-06-04"


def test_download_one_nonzero_returncode_returns_error(tmp_path):
    res = download_one(
        "URL",
        base_dir=tmp_path,
        day="2026-06-04",
        runner=lambda cmd: _proc(returncode=1, stderr="ERROR: bot check"),
    )
    assert not res.ok
    assert "bot check" in res.error
    assert res.video_path is None


def test_download_one_handles_runner_exception(tmp_path):
    def boom(cmd):
        raise OSError("yt-dlp not found")

    res = download_one("URL", base_dir=tmp_path, day="d", runner=boom)
    assert not res.ok
    assert "yt-dlp not found" in res.error


def test_download_one_bad_json_returns_error(tmp_path):
    res = download_one(
        "URL", base_dir=tmp_path, day="d", runner=lambda cmd: _proc(stdout="no json here")
    )
    assert not res.ok
    assert "no JSON" in res.error


def test_download_many_preserves_order_and_runs_all(tmp_path):
    runner = FakeRunner()
    urls = [f"https://yt/{i}" for i in range(5)]
    results = download_many(
        urls, max_workers=3, base_dir=tmp_path, day="2026-06-04", runner=runner
    )
    assert [r.url for r in results] == urls
    assert all(r.ok for r in results)
    assert len(runner.commands) == 5


def test_download_many_empty():
    assert download_many([]) == []


def test_resolve_video_path_falls_back_to_filename():
    from download.downloader import _resolve_video_path

    # No requested_downloads/filepath (as with --dump-json) — use _filename.
    info = {"_filename": "downloads/2026-06-04/Zeus/clip.mp4"}
    assert _resolve_video_path(info) == Path("downloads/2026-06-04/Zeus/clip.mp4")
    assert _resolve_video_path({}) is None


def test_parse_info_picks_last_json_line():
    out = '[info] downloading\n{"id": "a"}\n{"id": "b", "title": "last"}'
    assert _parse_info(out)["id"] == "b"


def test_find_subtitle_returns_none_when_absent(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    assert _find_subtitle(video) is None
    assert _find_subtitle(None) is None


def test_cli_reports_success_and_failure(tmp_path, monkeypatch, capsys):
    from download import cli
    from download.models import DownloadResult, VideoInfo

    info = VideoInfo(id="i", title="Great Video", channel="C", url="u")
    fake = [
        DownloadResult(url="u1", ok=True, video_path=tmp_path / "v.mp4",
                       subtitle_path=tmp_path / "v.en.srt", info=info),
        DownloadResult(url="u2", ok=False, error="boom"),
    ]
    monkeypatch.setattr(cli, "download_many", lambda *a, **k: fake)

    rc = cli.main(["u1", "u2"])

    out = capsys.readouterr()
    assert rc == 1  # at least one failure
    assert "Great Video" in out.out
    assert "boom" in out.err


def test_cli_all_success_returns_zero(monkeypatch):
    from download import cli
    from download.models import DownloadResult, VideoInfo

    monkeypatch.setattr(
        cli, "download_many",
        lambda *a, **k: [DownloadResult(url="u", ok=True, info=VideoInfo("i", "t", "c", "u"))],
    )
    assert cli.main(["u"]) == 0
