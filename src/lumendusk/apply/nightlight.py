"""Toggle night light (warm color temperature) on Linux Mint / Cinnamon.

Preferred path is Cinnamon's built-in night light (gsettings). Where those keys
are missing, fall back to ``gammastep`` or ``xsct`` if available.
"""

from __future__ import annotations

import shutil
import subprocess

from .. import log

_SCHEMA = "org.cinnamon.settings-daemon.plugins.color"


def _gsettings_set(schema: str, key: str, value: str) -> bool:
    if not shutil.which("gsettings"):
        return False
    try:
        subprocess.run(
            ["gsettings", "set", schema, key, value],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def _gsettings_get(schema: str, key: str) -> str | None:
    if not shutil.which("gsettings"):
        return None
    try:
        out = subprocess.run(
            ["gsettings", "get", schema, key],
            check=True, capture_output=True, text=True,
        )
        return out.stdout.strip().strip("'")
    except (subprocess.CalledProcessError, OSError):
        return None


def nightlight_on() -> bool:
    """Is the screen warmed right now?

    Reads Cinnamon's own key rather than remembering what we last set, so the
    manual toggle stays honest when the user changes it in System Settings.
    Unknown (no gsettings, fallback backend in use) reads as off — the toggle
    then shows off, and switching it on is still the right next action.
    """
    return _gsettings_get(_SCHEMA, "night-light-enabled") == "true"


def _fallback(on: bool, temperature: int) -> None:
    """Best-effort night light without Cinnamon's own keys."""
    try:
        if shutil.which("gammastep"):
            # gammastep -O sets a one-shot temperature; -x resets to daylight.
            args = ["gammastep", "-O", str(temperature)] if on else ["gammastep", "-x"]
            subprocess.Popen(args)
            return
        if shutil.which("xsct"):
            subprocess.Popen(["xsct", str(temperature) if on else "6500"])
            return
    except OSError as exc:
        log.warning("night-light fallback failed to start: %s", exc)
        return
    log.warning("no night-light backend available "
                "(cinnamon keys, gammastep, xsct).")


def set_nightlight(on: bool, temperature: int = 4000) -> None:
    if on:
        # Cinnamon stores temperature as a uint; gsettings accepts the bare int.
        _gsettings_set(_SCHEMA, "night-light-temperature", str(int(temperature)))
        # Force 'always' so the warm tint follows *our* enable toggle. In the
        # default 'auto' mode Cinnamon runs its own location-based sunrise/sunset
        # schedule, which disagrees with lumendusk's day/night times and leaves
        # the screen warm during daylight. We own the schedule; Cinnamon just
        # applies the tint when we say so.
        _gsettings_set(_SCHEMA, "night-light-schedule-mode", "always")
        ok = _gsettings_set(_SCHEMA, "night-light-enabled", "true")
    else:
        # The enabled flag is the master switch; false = off regardless of mode.
        ok = _gsettings_set(_SCHEMA, "night-light-enabled", "false")
    if not ok:
        _fallback(on, temperature)
    log.info("night light → %s%s", "on" if on else "off",
             f" @ {temperature}K" if on else "")
