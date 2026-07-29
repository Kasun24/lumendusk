"""Brightness backends: percent clamping, output parsing, and error handling.

No real monitors are touched — subprocess output is faked.
"""

from __future__ import annotations

import subprocess

import pytest

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
