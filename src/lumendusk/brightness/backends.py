"""Brightness backends. Every backend reads/writes a 0–100 % value.

Three kinds, in order of preference:

* :class:`SysfsBacklight` / brightnessctl — internal laptop panel (real backlight).
* :class:`DdcutilBacklight` — external monitors over DDC/CI (real backlight).
* :class:`XrandrBacklight` — software gamma dimming; a labelled last resort only.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class BacklightError(RuntimeError):
    """Raised when a backend cannot read or set brightness."""


class Backlight:
    """Base interface. ``id`` is how the CLI/config addresses this monitor."""

    id: str
    label: str
    backend: str
    real: bool = True  # False for software (gamma) dimming

    def get(self) -> int:  # pragma: no cover - interface
        raise NotImplementedError

    def set(self, percent: int) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    @staticmethod
    def _clamp(percent: int) -> int:
        return max(0, min(100, int(round(percent))))


class SysfsBacklight(Backlight):
    """Internal panel via ``brightnessctl`` if present, else raw sysfs."""

    backend = "sysfs"

    def __init__(self, name: str, path: Path):
        self.id = name
        self.label = f"{name} (internal panel)"
        self._path = path
        self._max = int((path / "max_brightness").read_text().strip())
        self._use_ctl = shutil.which("brightnessctl") is not None
        if self._use_ctl:
            self.backend = "brightnessctl"

    def get(self) -> int:
        raw = int((self._path / "brightness").read_text().strip())
        return self._clamp(raw / self._max * 100)

    def set(self, percent: int) -> None:
        percent = self._clamp(percent)
        if self._use_ctl:
            try:
                subprocess.run(
                    ["brightnessctl", "--device", self.id, "set", f"{percent}%"],
                    check=True, capture_output=True, text=True,
                )
                return
            except subprocess.CalledProcessError as exc:
                raise BacklightError(exc.stderr.strip() or "brightnessctl failed") from exc
        raw = int(round(percent / 100 * self._max))
        try:
            (self._path / "brightness").write_text(str(raw))
        except PermissionError as exc:
            raise BacklightError(
                f"cannot write {self._path/'brightness'} (need the 'video' group "
                "or a udev rule, or install brightnessctl)"
            ) from exc


class DdcutilBacklight(Backlight):
    """External monitor over DDC/CI. VCP feature 0x10 is luminance (0–100)."""

    backend = "ddcutil"

    def __init__(self, display: int, model: str = ""):
        self.id = f"ddc{display}"
        self.label = f"{model or 'external'} (ddcutil display {display})"
        self._display = str(display)

    def get(self) -> int:
        try:
            out = subprocess.run(
                ["ddcutil", "--display", self._display, "--brief", "getvcp", "10"],
                check=True, capture_output=True, text=True,
            ).stdout
        except subprocess.CalledProcessError as exc:
            raise BacklightError(exc.stderr.strip() or "ddcutil getvcp failed") from exc
        # Brief format: "VCP 10 C <current> <max>"
        parts = out.split()
        try:
            return self._clamp(int(parts[3]))
        except (IndexError, ValueError) as exc:
            raise BacklightError(f"unexpected ddcutil output: {out!r}") from exc

    def set(self, percent: int) -> None:
        percent = self._clamp(percent)
        try:
            subprocess.run(
                ["ddcutil", "--display", self._display, "setvcp", "10", str(percent)],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise BacklightError(exc.stderr.strip() or "ddcutil setvcp failed") from exc


class XrandrBacklight(Backlight):
    """Software gamma dimming — NOT real backlight control. Last resort."""

    backend = "xrandr"
    real = False

    def __init__(self, output: str):
        self.id = output
        self.label = f"{output} (software dimming — xrandr gamma)"

    def get(self) -> int:
        try:
            out = subprocess.run(
                ["xrandr", "--verbose"], check=True, capture_output=True, text=True
            ).stdout
        except subprocess.CalledProcessError as exc:
            raise BacklightError("xrandr --verbose failed") from exc
        # Find the block for this output and read its "Brightness: <float>".
        in_block = False
        for line in out.splitlines():
            if line and not line[0].isspace():
                in_block = line.startswith(self.id + " ")
            elif in_block and "Brightness:" in line:
                return self._clamp(float(line.split(":")[1].strip()) * 100)
        raise BacklightError(f"no brightness reported for output {self.id}")

    def set(self, percent: int) -> None:
        percent = self._clamp(percent)
        try:
            subprocess.run(
                ["xrandr", "--output", self.id, "--brightness", f"{percent/100:.2f}"],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise BacklightError(exc.stderr.strip() or "xrandr --brightness failed") from exc
