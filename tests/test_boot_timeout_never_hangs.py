"""A boot that times out must SKIP, not hang.

`fresh_hass_instance` and `hass_instance` both boot a real Home Assistant and,
when it does not answer inside the timeout, kill it and read its log so the skip
message can say why. They read it with `proc.stdout.read()` — which reads to
EOF, and EOF on that pipe means every holder of the write end has closed it, not
just Home Assistant. HA spawns children that inherit it.

So a boot timeout could block forever inside the fixture that was only trying to
explain itself. On 2026-09-06 `Tests + Coverage` on converge PR #40 ran past 35
minutes on both matrix legs with an empty log, against a Home Assistant released
the day before (2026.9.1, and the extra pins nothing) that no longer came up
inside the 180s boot timeout. The job had no `timeout-minutes`, so it was
heading for GitHub's six-hour default.
"""
from __future__ import annotations

import subprocess
import sys
import time

import pytest

from tests.conftest import _drain


def test_a_child_holding_the_pipe_open_does_not_block_the_drain():
    """The exact shape: the parent is dead, a child still holds the write end."""
    parent = subprocess.Popen(
        [sys.executable, "-c",
         "import subprocess,sys,time;"
         "subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
         "print('booting', flush=True); sys.exit(0)"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(0.5)
    started = time.monotonic()
    out = _drain(parent, timeout=3)
    elapsed = time.monotonic() - started
    assert elapsed < 10, f"the drain blocked for {elapsed:.1f}s"
    assert isinstance(out, str)


def test_the_log_comes_back_when_the_process_is_simply_dead():
    proc = subprocess.Popen([sys.executable, "-c", "print('hello from hass')"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert "hello from hass" in _drain(proc)


def test_no_stdout_pipe_is_an_empty_string_not_a_crash():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert _drain(proc) == ""


def test_the_fixtures_no_longer_read_to_eof():
    """The regression itself: `.read()` on that pipe is the bug."""
    src = open("tests/conftest.py", encoding="utf-8").read()
    # The docstring in `_drain` names the call it replaces, so match CODE:
    # an actual assignment from it, not the prose warning about it.
    offenders = [ln for ln in src.splitlines()
                 if ".stdout.read()" in ln and not ln.lstrip().startswith("#")
                 and "NEVER" not in ln]
    assert offenders == [], offenders
    assert src.count("_drain(proc)") == 2
