"""CLI tests with the backend resolver monkeypatched to a fake."""

from __future__ import annotations

import pysubs2

from translate import cli


def test_main_translates_with_default_output(sample_srt, tmp_path, monkeypatch, fake_backend):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "get_backend", lambda name: fake_backend)

    rc = cli.main([str(sample_srt)])

    assert rc == 0
    out = tmp_path / "out" / f"{sample_srt.stem}.bilingual.ass"
    assert out.is_file()
    assert len(pysubs2.load(str(out))) == 2


def test_main_missing_input_returns_2(tmp_path, monkeypatch, fake_backend):
    monkeypatch.setattr(cli, "get_backend", lambda name: fake_backend)
    rc = cli.main([str(tmp_path / "nope.srt")])
    assert rc == 2


def test_main_reports_backend_error(sample_srt, monkeypatch):
    def boom(name):
        raise ValueError("bad backend")

    monkeypatch.setattr(cli, "get_backend", boom)
    rc = cli.main([str(sample_srt), "-o", "x.ass", "--backend", "nope"])
    assert rc == 1
