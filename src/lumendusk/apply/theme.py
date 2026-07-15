"""Apply the GTK theme for day or night (Linux Mint / Cinnamon).

Sets two keys:

* ``org.cinnamon.desktop.interface gtk-theme`` — the actual GTK theme name.
* ``org.gnome.desktop.interface color-scheme`` — ``prefer-dark`` / ``prefer-light``,
  which libadwaita / Flatpak apps honour even when they ignore the GTK theme key.
"""

from __future__ import annotations

import shutil
import subprocess

from ..config import Config


def _gsettings_set(schema: str, key: str, value: str) -> bool:
    """Set one gsettings key. Returns False (without raising) on failure."""
    if not shutil.which("gsettings"):
        print("[lumendusk] gsettings not found; cannot set theme.")
        return False
    try:
        subprocess.run(
            ["gsettings", "set", schema, key, value],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        # Missing schema/key on some setups — report but don't crash the daemon.
        print(f"[lumendusk] gsettings set {schema} {key} failed: {exc.stderr.strip()}")
        return False


def set_theme(dark: bool, config: Config) -> None:
    theme = config.theme_dark if dark else config.theme_light
    scheme = "prefer-dark" if dark else "prefer-light"
    _gsettings_set("org.cinnamon.desktop.interface", "gtk-theme", theme)
    _gsettings_set("org.gnome.desktop.interface", "color-scheme", scheme)
    print(f"[lumendusk] theme → {theme} ({scheme})")
