"""Tests for the obs logging helper."""

from __future__ import annotations

import argparse
import logging

import obs


def test_configure_sets_recreator_logger_to_stderr():
    obs.configure(verbose=False)
    root = logging.getLogger("recreator")
    assert root.level == logging.INFO
    assert root.handlers and not root.propagate

    obs.configure(verbose=True)
    assert logging.getLogger("recreator").level == logging.DEBUG


def test_logger_is_namespaced():
    assert obs.logger("compose").name == "recreator.compose"


def test_add_verbose_arg():
    parser = argparse.ArgumentParser()
    obs.add_verbose_arg(parser)
    assert parser.parse_args(["-v"]).verbose is True
    assert parser.parse_args([]).verbose is False


def test_make_progress_tty_rewrites_one_line(monkeypatch):
    import io
    import sys

    class FakeTTY(io.StringIO):
        def isatty(self):
            return True

    fake = FakeTTY()
    monkeypatch.setattr(sys, "stderr", fake)
    progress = obs.make_progress("compose")
    progress(40)
    progress(100)
    out = fake.getvalue()
    assert "\rcompose: 40%" in out
    assert out.endswith("\rcompose: 100%\n")  # newline only at the end


def test_make_progress_non_tty_falls_back_to_log(monkeypatch):
    import io
    import sys
    from unittest.mock import MagicMock

    class FakeFile(io.StringIO):
        def isatty(self):
            return False

    monkeypatch.setattr(sys, "stderr", FakeFile())
    log = MagicMock()
    obs.make_progress("compose", log)(50)
    log.info.assert_called_once_with("%s: %d%%", "compose", 50)
