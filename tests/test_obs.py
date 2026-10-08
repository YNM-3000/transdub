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
    assert out.endswith("\n") and "\rcompose: 100%" in out  # newline only at the end
    assert out.count("\n") == 1  # single line: only the final newline


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
    log.info.assert_called_once_with("%s: %d%%%s", "compose", 50, "")


def test_make_progress_tty_shows_elapsed_and_eta(monkeypatch):
    import io
    import sys

    class FakeTTY(io.StringIO):
        def isatty(self):
            return True

    fake = FakeTTY()
    monkeypatch.setattr(sys, "stderr", fake)
    ticks = iter([0.0, 10.0, 40.0])  # t0 baseline, +10s @25%, +40s @100%
    progress = obs.make_progress("translate", clock=lambda: next(ticks))

    progress(0)    # first call sets the start time (elapsed 0)
    progress(25)   # 10s elapsed at 25% → ETA 30s
    assert "\rtranslate: 25% [0:10<0:30]" in fake.getvalue()

    progress(100)  # completion shows elapsed only
    assert "\rtranslate: 100% [0:40]" in fake.getvalue()


def test_make_progress_non_tty_throttles_and_logs_elapsed_at_end(monkeypatch):
    import io
    import sys
    from unittest.mock import MagicMock

    class FakeFile(io.StringIO):
        def isatty(self):
            return False

    monkeypatch.setattr(sys, "stderr", FakeFile())
    log = MagicMock()
    progress = obs.make_progress("dub", log, step=10)

    for pct in range(0, 101):  # 101 updates, as a chatty stage would emit
        progress(pct)

    # Throttled to every 10% (0,10,…,90) plus the final 100 → 11 lines, not 101.
    assert log.info.call_count == 11
    # The completion line carries elapsed time in its format.
    assert log.info.call_args_list[-1].args[0] == "%s: %d%%%s (%s)"
    assert log.info.call_args_list[-1].args[1] == "dub"


def test_make_progress_tty_appends_detail_and_clears(monkeypatch):
    import io
    import sys

    class FakeTTY(io.StringIO):
        def isatty(self):
            return True

    fake = FakeTTY()
    monkeypatch.setattr(sys, "stderr", fake)
    progress = obs.make_progress("download")
    progress(40, "of 12.3MiB")
    out = fake.getvalue()
    assert "\rdownload: 40% of 12.3MiB" in out
    assert "\033[K" in out  # clears stale characters from a longer prior line
