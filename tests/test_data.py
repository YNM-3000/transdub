"""Tests for the metrics datastore (SQLite, ingest, CLI)."""

from __future__ import annotations

import json

import pytest

from data.ingest import find_info_jsons, source_record_from_info_json
from data.models import SourceRecord, UploadRecord
from data.store import DataStore


@pytest.fixture
def store(tmp_path):
    with DataStore(tmp_path / "test.db") as s:
        yield s


def _source(sid="vid1", views=1000, **kw):
    return SourceRecord(source_id=sid, view_count=views, title="T", **kw)


# --- store -------------------------------------------------------------------

def test_record_and_latest_source(store):
    store.record_source(_source(views=500, captured_at="2026-01-01T00:00:00+00:00"))
    latest = store.latest_source("vid1")
    assert latest.view_count == 500
    assert latest.title == "T"


def test_latest_source_returns_newest_snapshot(store):
    store.record_source(_source(views=100, captured_at="2026-01-01T00:00:00+00:00"))
    store.record_source(_source(views=900, captured_at="2026-02-01T00:00:00+00:00"))
    assert store.latest_source("vid1").view_count == 900


def test_latest_source_none_when_absent(store):
    assert store.latest_source("missing") is None


def test_record_and_latest_upload(store):
    store.record_upload(UploadRecord(
        source_id="vid1", platform="bilibili", url="u", view_count=42,
        captured_at="2026-03-01T00:00:00+00:00",
    ))
    up = store.latest_upload("vid1")
    assert up.platform == "bilibili" and up.view_count == 42


def test_list_sources_returns_latest_per_id(store):
    store.record_source(_source(sid="a", views=1, captured_at="2026-01-01T00:00:00+00:00"))
    store.record_source(_source(sid="a", views=5, captured_at="2026-02-01T00:00:00+00:00"))
    store.record_source(_source(sid="b", views=3, captured_at="2026-01-15T00:00:00+00:00"))

    sources = store.list_sources()
    by_id = {s.source_id: s.view_count for s in sources}
    assert by_id == {"a": 5, "b": 3}  # one row per id, latest snapshot


def test_comparison_and_view_ratio(store):
    store.record_source(_source(views=1000, captured_at="2026-01-01T00:00:00+00:00"))
    store.record_upload(UploadRecord(
        source_id="vid1", platform="bilibili", view_count=250,
        captured_at="2026-02-01T00:00:00+00:00",
    ))
    cmp = store.comparison("vid1")
    assert cmp.source.view_count == 1000
    assert cmp.upload.view_count == 250
    assert cmp.view_ratio() == pytest.approx(0.25)


def test_comparison_ratio_none_without_both(store):
    store.record_source(_source(views=1000))
    assert store.comparison("vid1").view_ratio() is None


def test_store_persists_across_reopen(tmp_path):
    db = tmp_path / "p.db"
    with DataStore(db) as s:
        s.record_source(_source(views=7, captured_at="2026-01-01T00:00:00+00:00"))
    with DataStore(db) as s:
        assert s.latest_source("vid1").view_count == 7


def test_captured_at_defaults_to_now(store):
    store.record_source(SourceRecord(source_id="x"))
    assert store.latest_source("x").captured_at  # set automatically


# --- ingest ------------------------------------------------------------------

def _write_info(path, **fields):
    path.write_text(json.dumps(fields), encoding="utf-8")
    return path


def test_source_record_from_info_json(tmp_path):
    info = _write_info(
        tmp_path / "Clip.info.json",
        id="abc", webpage_url="https://yt/abc", title="USB-C",
        channel="Zeus", upload_date="20260425", duration=335,
        view_count=12345, like_count=678, comment_count=90,
    )
    rec = source_record_from_info_json(info)
    assert rec.source_id == "abc"
    assert rec.url == "https://yt/abc"
    assert rec.view_count == 12345
    assert rec.duration_s == 335


def test_find_info_jsons_file_and_dir(tmp_path):
    (tmp_path / "d1").mkdir()
    (tmp_path / "d1" / "A.info.json").write_text("{}", encoding="utf-8")
    (tmp_path / "d2").mkdir()
    (tmp_path / "d2" / "B.info.json").write_text("{}", encoding="utf-8")

    found = find_info_jsons(tmp_path)
    assert len(found) == 2
    single = find_info_jsons(tmp_path / "d1" / "A.info.json")
    assert len(single) == 1
    assert find_info_jsons(tmp_path / "nope.info.json") == []


# --- CLI ---------------------------------------------------------------------

def test_cli_record_source_then_show(tmp_path, capsys):
    from data import cli

    info = _write_info(
        tmp_path / "Clip.info.json",
        id="vid9", webpage_url="u", title="标题", view_count=1000, like_count=50,
    )
    db = str(tmp_path / "c.db")

    assert cli.main(["--db", db, "record-source", str(info)]) == 0
    capsys.readouterr()

    assert cli.main([
        "--db", db, "record-upload", "--source-id", "vid9",
        "--platform", "bilibili", "--views", "300", "--likes", "20",
    ]) == 0
    capsys.readouterr()

    assert cli.main(["--db", db, "show", "vid9"]) == 0
    out = capsys.readouterr().out
    assert "source" in out and "upload" in out
    assert "30.0%" in out  # 300 / 1000


def test_cli_record_source_missing_path_returns_2(tmp_path, capsys):
    from data import cli

    rc = cli.main(["--db", str(tmp_path / "c.db"), "record-source", str(tmp_path / "no.info.json")])
    assert rc == 2


def test_cli_list_empty(tmp_path, capsys):
    from data import cli

    assert cli.main(["--db", str(tmp_path / "c.db"), "list"]) == 0
    assert "no sources" in capsys.readouterr().out
