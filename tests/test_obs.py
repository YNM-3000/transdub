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
