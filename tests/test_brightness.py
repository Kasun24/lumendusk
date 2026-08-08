"""Brightness backends: percent clamping, output parsing, and error handling.

No real monitors are touched — subprocess output is faked.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time

import pytest

from lumendusk import brightness as brightness_mod
from lumendusk.brightness import backends, monitors
from lumendusk.brightness.backends import (
    BacklightError,
    DdcutilBacklight,
    SysfsBacklight,
    XrandrBacklight,
)
from lumendusk.brightness.monitors import select


class FakeCompleted:
    def __init__(self, stdout="", stderr=""):
        self.stdout = stdout
        self.stderr = stderr


class TestClamping:
    @pytest.mark.parametrize("given,expected", [
        (-40, 0), (0, 0), (55, 55), (100, 100), (250, 100),
    ])
    def test_percent_is_clamped_to_0_100(self, given, expected):
        assert backends.Backlight._clamp(given) == expected


class TestSysfs:
    def _panel(self, tmp_path, current=120, maximum=255):
        (tmp_path / "max_brightness").write_text(str(maximum))
        (tmp_path / "brightness").write_text(str(current))
        return SysfsBacklight("intel_backlight", tmp_path)

    def test_get_normalises_raw_value_to_percent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backends.shutil, "which", lambda _: None)
        panel = self._panel(tmp_path, current=128, maximum=255)
        assert panel.get() == 50

    def test_set_writes_the_scaled_raw_value(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backends.shutil, "which", lambda _: None)
        panel = self._panel(tmp_path, maximum=255)
        panel.set(40)
        assert int((tmp_path / "brightness").read_text()) == 102

    def test_permission_error_becomes_a_helpful_backlight_error(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(backends.shutil, "which", lambda _: None)
        panel = self._panel(tmp_path)

        def denied(*args, **kwargs):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(type(tmp_path / "brightness"), "write_text", denied)
        with pytest.raises(BacklightError, match="video"):
            panel.set(50)


class TestDdcutil:
    def test_get_parses_brief_output(self, monkeypatch):
        monkeypatch.setattr(
            backends.subprocess, "run",
            lambda *a, **k: FakeCompleted(stdout="VCP 10 C 33 100\n"))
        assert DdcutilBacklight(1, "DELL").get() == 33

    def test_get_rejects_unexpected_output(self, monkeypatch):
        monkeypatch.setattr(
            backends.subprocess, "run",
            lambda *a, **k: FakeCompleted(stdout="DDC communication failed\n"))
        with pytest.raises(BacklightError, match="unexpected ddcutil output"):
            DdcutilBacklight(1).get()

    def test_failure_surfaces_stderr(self, monkeypatch):
        def boom(*a, **k):
            raise subprocess.CalledProcessError(
                1, "ddcutil", stderr="no /dev/i2c devices found")

        monkeypatch.setattr(backends.subprocess, "run", boom)
        with pytest.raises(BacklightError, match="i2c"):
            DdcutilBacklight(1).set(50)


class TestXrandr:
    OUTPUT = (
        "HDMI-1 connected primary 1920x1080+0+0\n"
        "\tIdentifier: 0x44\n"
        "\tBrightness: 0.75\n"
        "DP-1 connected 1920x1080+1920+0\n"
        "\tBrightness: 1.0\n"
    )

    def test_get_reads_the_right_output_block(self, monkeypatch):
        monkeypatch.setattr(backends.subprocess, "run",
                            lambda *a, **k: FakeCompleted(stdout=self.OUTPUT))
        assert XrandrBacklight("HDMI-1").get() == 75
        assert XrandrBacklight("DP-1").get() == 100

    def test_unknown_output_raises(self, monkeypatch):
        monkeypatch.setattr(backends.subprocess, "run",
                            lambda *a, **k: FakeCompleted(stdout=self.OUTPUT))
        with pytest.raises(BacklightError):
            XrandrBacklight("VGA-9").get()

    def test_is_flagged_as_not_a_real_backlight(self):
        assert XrandrBacklight("HDMI-1").real is False
        assert DdcutilBacklight(1).real is True


class TestSelect:
    def test_all_returns_everything(self):
        mons = [XrandrBacklight("HDMI-1"), XrandrBacklight("DP-1")]
        assert select(mons, "all") == mons

    def test_known_id_returns_one(self):
        mons = [XrandrBacklight("HDMI-1"), XrandrBacklight("DP-1")]
        assert [m.id for m in select(mons, "DP-1")] == ["DP-1"]

    def test_unknown_id_raises_backlight_error_not_systemexit(self):
        """SystemExit from library code would take the daemon down with it."""
        mons = [XrandrBacklight("HDMI-1")]
        with pytest.raises(BacklightError, match="HDMI-1"):
            select(mons, "nope")


class FakeMonitor:
    """A monitor that either accepts a write or refuses it."""

    def __init__(self, mid, fails=False):
        self.id = mid
        self.fails = fails
        self.written = None

    def set(self, percent):
        if self.fails:
            raise BacklightError("ddcutil setvcp failed")
        self.written = percent


class TestSetBrightnessLogging:
    """What set_brightness reports must match what actually happened.

    Brightness used to be the one subsystem that could change silently: the
    applet's slider writes through the CLI, and only the daemon logged, so a
    change made from the panel left no trace. Worse, the daemon logged the
    level it *asked* for whether or not any backend accepted it — a success
    line over a total failure is how a broken ddcutil setup stays hidden.
    """

    @pytest.fixture
    def monitors(self, monkeypatch):
        def install(*mons):
            monkeypatch.setattr(brightness_mod, "list_monitors",
                                lambda: list(mons))
            return mons
        return install

    @pytest.fixture
    def logged(self):
        """Collect Lumendusk's own log messages.

        Not pytest's ``caplog``: log.py sets ``propagate = False``, so records
        never reach the root logger caplog listens on. Attaching to the
        project logger is the only way to see them.
        """
        messages: list[str] = []

        class Collect(logging.Handler):
            def emit(self, record):
                messages.append(record.getMessage())

        logger = logging.getLogger("lumendusk")
        handler = Collect()
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            yield messages
        finally:
            logger.removeHandler(handler)

    def test_success_names_the_monitors_it_set(self, monitors, logged):
        a, b = monitors(FakeMonitor("ddc1"), FakeMonitor("ddc2"))
        applied = brightness_mod.set_brightness(20)
        assert applied == [("ddc1", 20), ("ddc2", 20)]
        assert (a.written, b.written) == (20, 20)
        assert "brightness \u2192 20% on ddc1, ddc2." in "\n".join(logged)

    def test_a_partial_failure_says_which_one(self, monitors, logged):
        monitors(FakeMonitor("ddc1"), FakeMonitor("ddc2", fails=True))
        applied = brightness_mod.set_brightness(45)
        assert [mid for mid, _ in applied] == ["ddc1"]
        assert "brightness \u2192 45% on ddc1 (ddc2 failed)." in "\n".join(logged)

    def test_a_total_failure_is_not_reported_as_success(self, monitors, logged):
        """The regression that matters: no cheerful line over a dead write."""
        monitors(FakeMonitor("ddc1", fails=True), FakeMonitor("ddc2", fails=True))
        assert brightness_mod.set_brightness(45) == []
        text = "\n".join(logged)
        assert "failed on every monitor (ddc1, ddc2)" in text
        assert "brightness \u2192 45% on" not in text

    def test_no_monitors_is_said_out_loud(self, monitors, logged):
        monitors()
        assert brightness_mod.set_brightness(45) == []
        assert "no monitors matched 'all'" in "\n".join(logged)

    def test_the_level_is_clamped_in_the_log_too(self, monitors, logged):
        monitors(FakeMonitor("ddc1"))
        brightness_mod.set_brightness(250)
        assert "brightness \u2192 100% on ddc1." in "\n".join(logged)


class TestHangingCommands:
    """A backend that hangs must not take the daemon with it.

    This is the failure the timeouts exist for, and it is the quietest one in
    the project: ddcutil waiting on a monitor that is asleep or on another
    input never raises, so a daemon stuck there keeps its process alive, logs
    nothing further, and looks exactly like a healthy idle daemon. The next
    transition simply never happens.
    """

    @staticmethod
    def _hang(*a, **k):
        raise subprocess.TimeoutExpired(cmd="ddcutil", timeout=10)

    def test_a_hung_read_becomes_a_backlight_error(self, monkeypatch):
        monkeypatch.setattr(backends.subprocess, "run", self._hang)
        with pytest.raises(BacklightError, match="timed out"):
            DdcutilBacklight(1).get()

    def test_a_hung_write_becomes_a_backlight_error(self, monkeypatch):
        monkeypatch.setattr(backends.subprocess, "run", self._hang)
        with pytest.raises(BacklightError, match="timed out"):
            DdcutilBacklight(1).set(50)

    def test_one_hung_monitor_does_not_block_the_others(self, monkeypatch):
        """The point of per-monitor errors: ddc2 wedging must not cost ddc1."""
        good = FakeMonitor("ddc1")

        class Hangs:
            id = "ddc2"

            def set(self, percent):
                raise BacklightError("ddcutil setvcp timed out after 10s")

        monkeypatch.setattr(brightness_mod, "list_monitors",
                            lambda: [good, Hangs()])
        applied = brightness_mod.set_brightness(20)
        assert applied == [("ddc1", 20)]
        assert good.written == 20

    def test_a_missing_executable_is_an_error_not_a_crash(self, monkeypatch):
        """OSError used to escape uncaught and reach the daemon's tick handler."""
        def gone(*a, **k):
            raise FileNotFoundError(2, "No such file or directory", "ddcutil")

        monkeypatch.setattr(backends.subprocess, "run", gone)
        with pytest.raises(BacklightError, match="ddcutil"):
            DdcutilBacklight(1).get()


class TestDiscoveryCache:
    """Caching monitor discovery, and — the harder half — invalidating it.

    `ddcutil detect` costs ~0.5 s and runs on every brightness operation. The
    applet shells out to the CLI, so each slider move is a fresh process paying
    it again; only an on-disk cache is shared across those.

    Every test here is really about the failure mode of caching: showing a user
    a monitor that is no longer plugged in, or hiding one that now is.
    """

    @pytest.fixture
    def cache(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        monkeypatch.setattr(monitors, "_connector_fingerprint", lambda: "dp1:connected")
        probes = {"n": 0}

        def probe():
            probes["n"] += 1
            return [DdcutilBacklight(1, "DELL")]

        monkeypatch.setattr(monitors, "_external_monitors", probe)
        monkeypatch.setattr(monitors, "_internal_monitors", list)
        return probes

    def test_the_second_call_does_not_probe(self, cache):
        first = monitors.list_monitors()
        second = monitors.list_monitors()
        assert [m.id for m in first] == [m.id for m in second] == ["ddc1"]
        assert cache["n"] == 1, "detect should have run exactly once"

    def test_plugging_a_monitor_in_invalidates_immediately(self, cache, monkeypatch):
        """The reason this is keyed on DRM connectors and not just a timer."""
        monitors.list_monitors()
        assert cache["n"] == 1

        monkeypatch.setattr(monitors, "_connector_fingerprint",
                            lambda: "dp1:connected|hdmi1:connected")
        monitors.list_monitors()
        assert cache["n"] == 2, "a hotplug must not wait for the cache to age out"

    def test_an_old_cache_is_not_trusted(self, cache, monkeypatch):
        """Backstop for machines exposing no DRM connectors, where the
        fingerprint is a constant empty string and can never invalidate."""
        monitors.list_monitors()
        # Capture the real clock first: patching time.time and then calling it
        # inside the replacement would call the replacement.
        later = time.time() + monitors._CACHE_MAX_AGE + 1
        monkeypatch.setattr(monitors.time, "time", lambda: later)
        monitors.list_monitors()
        assert cache["n"] == 2

    def test_refresh_bypasses_a_valid_cache(self, cache):
        monitors.list_monitors()
        monitors.list_monitors(refresh=True)
        assert cache["n"] == 2

    def test_a_corrupt_cache_falls_back_to_probing(self, cache, tmp_path):
        monitors.list_monitors()
        monitors._cache_path().write_text("{ this is not json", encoding="utf-8")
        assert [m.id for m in monitors.list_monitors()] == ["ddc1"]
        assert cache["n"] == 2, "a broken cache must never be fatal"

    def test_an_unwritable_cache_dir_costs_speed_not_correctness(
            self, cache, monkeypatch):
        monkeypatch.setattr(monitors.Path, "mkdir",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("read-only")))
        assert [m.id for m in monitors.list_monitors()] == ["ddc1"]
        assert [m.id for m in monitors.list_monitors()] == ["ddc1"]

    def test_a_cached_monitor_is_rebuilt_as_the_same_backend(self, cache):
        monitors.list_monitors()
        restored = monitors.list_monitors()[0]
        assert isinstance(restored, DdcutilBacklight)
        assert restored.id == "ddc1"
        assert "DELL" in restored.label

    def test_nothing_detected_is_not_cached_as_truth(self, tmp_path, monkeypatch):
        """An empty result usually means ddcutil failed, not that the machine
        has no monitors — caching it would make one bad probe stick."""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        monkeypatch.setattr(monitors, "_connector_fingerprint", lambda: "x")
        monkeypatch.setattr(monitors, "_internal_monitors", list)
        monkeypatch.setattr(monitors, "_external_monitors", list)
        monkeypatch.setattr(monitors, "_xrandr_monitors", list)
        assert monitors.list_monitors() == []
        assert not monitors._cache_path().exists()


class TestDdcLock:
    """ddcutil must never run twice at once, across processes.

    DDC/CI is a bus, not independent devices. Measured on real hardware,
    concurrent getvcp calls failed about one run in five with "Display not
    found" — and were slower than running them in sequence. The callers are
    separate processes (the daemon at a transition, the applet shelling out to
    draw its slider), so only a file lock can see both.
    """

    @pytest.fixture
    def lockdir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        return tmp_path

    def test_it_serialises_concurrent_holders(self, lockdir):
        """Two threads, and the second must not enter while the first holds it."""
        overlaps = []
        inside = []

        def worker():
            with backends.ddc_lock():
                inside.append(1)
                overlaps.append(len(inside))
                time.sleep(0.05)
                inside.pop()

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert overlaps == [1, 1, 1, 1], f"overlapping ddcutil calls: {overlaps}"

    def test_the_lock_is_released_when_the_body_raises(self, lockdir):
        """A failed ddcutil must not leave the bus locked for everyone else."""
        with pytest.raises(BacklightError), backends.ddc_lock():
            raise BacklightError("ddcutil setvcp failed")

        acquired = []
        with backends.ddc_lock():
            acquired.append(True)
        assert acquired == [True]

    def test_an_unwritable_cache_dir_still_runs(self, monkeypatch, tmp_path):
        """Degrade to today's behaviour rather than refusing to set brightness."""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        monkeypatch.setattr(backends.Path, "mkdir",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("read-only")))
        ran = []
        with backends.ddc_lock():
            ran.append(True)
        assert ran == [True]

    def test_a_platform_without_fcntl_still_runs(self, monkeypatch, lockdir):
        """Windows (Phase 3) has no flock; brightness must not depend on it."""
        monkeypatch.setattr(backends, "fcntl", None)
        ran = []
        with backends.ddc_lock():
            ran.append(True)
        assert ran == [True]

    def test_a_wedged_holder_does_not_block_forever(self, monkeypatch, lockdir):
        """Bounded wait: past the deadline, warn and proceed unlocked.

        Better a possible collision than a daemon that stops applying
        brightness because some other process died holding the lock.
        """
        monkeypatch.setattr(backends, "_LOCK_WAIT", 0.1)
        backends.cache_dir().mkdir(parents=True, exist_ok=True)
        blocker = open(backends.cache_dir() / "ddc.lock", "w")
        fcntl_mod = backends.fcntl
        fcntl_mod.flock(blocker, fcntl_mod.LOCK_EX)
        try:
            ran = []
            started = time.monotonic()
            with backends.ddc_lock():
                ran.append(True)
            assert ran == [True]
            assert time.monotonic() - started < 5, "should give up quickly"
        finally:
            fcntl_mod.flock(blocker, fcntl_mod.LOCK_UN)
            blocker.close()
