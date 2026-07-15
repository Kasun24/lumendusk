"""Toggle night light (warm color temperature) on Linux Mint / Cinnamon.

Preferred path is Cinnamon's built-in night light (gsettings). Where those keys
are missing, fall back to ``gammastep`` or ``xsct`` if available.
"""

from __future__ import annotations

import shutil
import subprocess

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


def _fallback(on: bool, temperature: int) -> None:
    """Best-effort night light without Cinnamon's own keys."""
    if shutil.which("gammastep"):
        # gammastep -O sets a one-shot temperature; -x resets to daylight.
        if on:
            subprocess.Popen(["gammastep", "-O", str(temperature)])
        elif shutil.which("gammastep"):
            subprocess.Popen(["gammastep", "-x"])
        return
    if shutil.which("xsct"):
        subprocess.Popen(["xsct", str(temperature) if on else "6500"])
        return
    print("[lumendusk] no night-light backend available (cinnamon keys, gammastep, xsct).")


def set_nightlight(on: bool, temperature: int = 4000) -> None:
    ok = _gsettings_set(_SCHEMA, "night-light-enabled", "true" if on else "false")
    if ok and on:
        # Cinnamon stores temperature as a uint; gsettings accepts the bare int.
        _gsettings_set(_SCHEMA, "night-light-temperature", str(int(temperature)))
    if not ok:
        _fallback(on, temperature)
    print(f"[lumendusk] night light → {'on' if on else 'off'}"
          + (f" @ {temperature}K" if on else ""))
