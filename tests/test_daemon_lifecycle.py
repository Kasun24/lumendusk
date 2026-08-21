"""Starting and stopping the daemon.

Not the schedule — the two things that happen either side of it. Both are
invisible when they work and quiet when they don't: a second daemon just makes
everything happen twice, and an unhandled SIGTERM just makes the log stop.
"""

from __future__ import annotations

import fcntl
import os
import signal

import pytest

from lumendusk import daemon as daemon_mod
from lumendusk.brightness.backends import cache_dir


@pytest.fixture(autouse=True)
def _restore_sigterm():
    """Give pytest its own SIGTERM handler back.

    run_daemon installs one process-wide, and a test that left it in place
    would change how the *test runner* dies.
    """
    previous = signal.getsignal(signal.SIGTERM)
    yield
    signal.signal(signal.SIGTERM, previous)


def test_a_second_daemon_bows_out(applies, caplog):
    # flock belongs to the open file description, not the process, so a
    # separate open() here contends exactly the way another process would.
    path = cache_dir() / "daemon.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)

        assert daemon_mod.run_daemon(interval=1) == 0

    # The point isn't the exit code, it's that it touched nothing on the way
    # out: the daemon that already holds the lock owns the desktop.
    assert applies == {"theme": [], "nightlight": [], "brightness": []}


def test_the_lock_is_released_when_the_daemon_stops(monkeypatch, applies):
    """A daemon that exits must not lock the next one out."""
    def stop_immediately(_seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(daemon_mod.time, "sleep", stop_immediately)
    assert daemon_mod.run_daemon(interval=1) == 0

    with open(cache_dir() / "daemon.lock", "w") as after:
        fcntl.flock(after, fcntl.LOCK_EX | fcntl.LOCK_NB)   # raises if still held


def test_an_unwritable_cache_does_not_stop_the_daemon(monkeypatch, applies, tmp_path):
    """The lock is a courtesy. Losing it must never cost a working daemon."""
    def no_cache_dir():
        raise OSError("read-only")

    monkeypatch.setattr(daemon_mod, "cache_dir", no_cache_dir)

    ticks = {"n": 0}

    def one_tick(_seconds):
        ticks["n"] += 1
        raise KeyboardInterrupt

    monkeypatch.setattr(daemon_mod.time, "sleep", one_tick)
    assert daemon_mod.run_daemon(interval=1) == 0
    assert ticks["n"] == 1
    assert applies["theme"], "the daemon should still have applied the phase"


def test_sigterm_ends_the_loop_the_way_ctrl_c_does(monkeypatch, applies):
    """SIGTERM is how a logout, a pkill and uninstall.sh all stop the daemon."""
    def sleep_then_terminate(_seconds):
        os.kill(os.getpid(), signal.SIGTERM)

    monkeypatch.setattr(daemon_mod.time, "sleep", sleep_then_terminate)
    assert daemon_mod.run_daemon(interval=1) == 0


def test_once_does_not_take_the_lock(monkeypatch, applies):
    """``--once`` is run *while* the daemon is up — that is what it is for."""
    path = cache_dir() / "daemon.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)

        assert daemon_mod.run_daemon(once=True) == 0

    assert applies["theme"], "--once should have applied the current phase"
