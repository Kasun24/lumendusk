"""Brightness backends: percent clamping, output parsing, and error handling.

No real monitors are touched — subprocess output is faked.
"""

from __future__ import annotations

import logging
import subprocess

import pytest

from lumendusk import brightness as brightness_mod
from lumendusk.brightness import backends
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
