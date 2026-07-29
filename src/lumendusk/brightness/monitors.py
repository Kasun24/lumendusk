"""Enumerate monitors and pick the right brightness backend for each.

Detection order:
  1. Internal panels from ``/sys/class/backlight/*``.
  2. External monitors from ``ddcutil detect``.
  3. If neither is found, fall back to ``xrandr`` connected outputs (software).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .backends import (
    Backlight,
    BacklightError,
    DdcutilBacklight,
    SysfsBacklight,
    XrandrBacklight,
)

_SYS_BACKLIGHT = Path("/sys/class/backlight")


def _internal_monitors() -> list[Backlight]:
    mons: list[Backlight] = []
    if _SYS_BACKLIGHT.is_dir():
        for entry in sorted(_SYS_BACKLIGHT.iterdir()):
            if (entry / "max_brightness").exists():
                try:
                    mons.append(SysfsBacklight(entry.name, entry))
                except (OSError, ValueError):
                    continue
    return mons


def _external_monitors() -> list[Backlight]:
    if not shutil.which("ddcutil"):
        return []
    try:
        out = subprocess.run(
            ["ddcutil", "detect", "--brief"],
            check=True, capture_output=True, text=True, timeout=15,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []
    mons: list[Backlight] = []
    display: int | None = None
    model = ""
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("Display "):
            try:
                number = int(stripped.split()[1])
            except (IndexError, ValueError):
                continue  # e.g. "Display not found" — not a display block
            if display is not None:
                mons.append(DdcutilBacklight(display, model))
            display = number
            model = ""
        elif stripped.startswith("Monitor:") and display is not None:
            # "Monitor: <mfg>:<model>:<serial>"
            parts = stripped.split(":")
            model = parts[2].strip() if len(parts) > 2 else ""
    if display is not None:
        mons.append(DdcutilBacklight(display, model))
    return mons


def _xrandr_monitors() -> list[Backlight]:
    if not shutil.which("xrandr"):
        return []
    try:
        out = subprocess.run(
            ["xrandr", "--query"], check=True, capture_output=True, text=True
        ).stdout
    except subprocess.CalledProcessError:
        return []
    mons: list[Backlight] = []
    for line in out.splitlines():
        if " connected" in line:
            mons.append(XrandrBacklight(line.split()[0]))
    return mons


def list_monitors() -> list[Backlight]:
    """Return all controllable monitors, real backlights preferred."""
    mons = _internal_monitors() + _external_monitors()
    if not mons:
        mons = _xrandr_monitors()
    return mons


def select(monitors: list[Backlight], selector: str) -> list[Backlight]:
    """Filter monitors by id, or return all for the "all" selector.

    Raises :class:`BacklightError` for an unknown id — never ``SystemExit``,
    which would take the daemon down from library code.
    """
    if selector == "all":
        return monitors
    chosen = [m for m in monitors if m.id == selector]
    if not chosen:
        known = ", ".join(m.id for m in monitors) or "(none detected)"
        raise BacklightError(f"no monitor '{selector}'. Known: {known}")
    return chosen
