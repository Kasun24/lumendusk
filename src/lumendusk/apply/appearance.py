"""Standalone dark/light appearance switch for Cinnamon.

This is a **self-contained, correctly-working** dark/light switcher, developed
independently of the existing ``theme.py`` path so we can get the mechanism right
before wiring it into config/options. Run it directly:

    python3 -m lumendusk.apply.appearance dark
    python3 -m lumendusk.apply.appearance light
    python3 -m lumendusk.apply.appearance status

Why this exists: the older switcher set only two keys (``gtk-theme`` and
``color-scheme``), which left the Cinnamon shell, panel, menus and window
borders on their previous (often dark) theme while GTK apps flipped — a visible
"half switch". A correct dark/light change on Cinnamon has to move every key
that contributes to the desktop's appearance:

  * ``org.cinnamon.desktop.interface  gtk-theme``   — GTK application theme
  * ``org.cinnamon.theme              name``        — Cinnamon shell / panel / menus
  * ``org.cinnamon.desktop.wm.preferences theme``   — window borders / title bars
  * ``org.gnome.desktop.interface     color-scheme``— libadwaita / Flatpak hint

The switch keeps the current **accent** (Orange, Aqua, …) and only flips the
light/dark axis, so a user's colour choice survives the toggle.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

# The Mint-Y family: light names are "Mint-Y[-Accent]", dark names insert
# "-Dark" ("Mint-Y-Dark[-Accent]"). This is the only family we special-case for
# now; other themes fall back to a name-mangling guess.
_LIGHT_FAMILY = "Mint-Y"
_DARK_FAMILY = "Mint-Y-Dark"

# Every key that has to move together for a clean appearance change.
_GTK = ("org.cinnamon.desktop.interface", "gtk-theme")
_SHELL = ("org.cinnamon.theme", "name")
_WM = ("org.cinnamon.desktop.wm.preferences", "theme")
_SCHEME = ("org.gnome.desktop.interface", "color-scheme")


def _gsettings_get(schema: str, key: str) -> str | None:
    if not shutil.which("gsettings"):
        return None
    try:
        out = subprocess.run(
            ["gsettings", "get", schema, key],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        # gsettings prints strings quoted: 'Mint-Y-Orange' -> Mint-Y-Orange
        return out.strip("'\"")
    except subprocess.CalledProcessError:
        return None


def _gsettings_set(schema: str, key: str, value: str) -> bool:
    if not shutil.which("gsettings"):
        print("[appearance] gsettings not found; cannot change theme.")
        return False
    try:
        subprocess.run(
            ["gsettings", "set", schema, key, value],
            check=True, capture_output=True, text=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        print(f"[appearance] set {schema} {key} '{value}' failed: {exc.stderr.strip()}")
        return False


def _installed_themes() -> set[str]:
    """Theme directory names available to the user (~/.themes + system)."""
    dirs = [
        os.path.expanduser("~/.themes"),
        os.path.join(os.path.expanduser("~/.local/share/themes")),
        "/usr/share/themes",
    ]
    names: set[str] = set()
    for d in dirs:
        try:
            names.update(os.listdir(d))
        except OSError:
            pass
    return names


def _detect_accent() -> str:
    """Work out the current accent (e.g. "Orange") from the live GTK theme.

    Returns "" for the plain grey Mint-Y / Mint-Y-Dark.
    """
    current = _gsettings_get(*_GTK) or ""
    name = current
    if name.startswith(_DARK_FAMILY):
        name = name[len(_DARK_FAMILY):]
    elif name.startswith(_LIGHT_FAMILY):
        name = name[len(_LIGHT_FAMILY):]
    else:
        return ""  # unknown family; no accent we can preserve
    return name.lstrip("-")  # "-Orange" -> "Orange", "" -> ""


@dataclass
class ThemePair:
    light: str
    dark: str

    def name(self, dark: bool) -> str:
        return self.dark if dark else self.light


def theme_pair(accent: str = "") -> ThemePair:
    """Light/dark Mint-Y theme names for a given accent."""
    suffix = f"-{accent}" if accent else ""
    return ThemePair(light=f"{_LIGHT_FAMILY}{suffix}", dark=f"{_DARK_FAMILY}{suffix}")


def set_appearance(dark: bool, accent: str | None = None) -> bool:
    """Flip the whole desktop to dark or light, preserving the accent.

    Returns True if every key was set. Falls back the accent to plain Mint-Y if
    the accented dark/light theme is not actually installed.
    """
    if accent is None:
        accent = _detect_accent()

    pair = theme_pair(accent)
    installed = _installed_themes()
    # If the accented pair isn't installed, drop to the plain grey Mint-Y pair.
    if pair.light not in installed or pair.dark not in installed:
        if accent:
            print(f"[appearance] '{pair.name(dark)}' not installed; "
                  f"falling back to plain {_LIGHT_FAMILY}.")
        pair = theme_pair("")

    theme = pair.name(dark)
    scheme = "prefer-dark" if dark else "prefer-light"

    ok = True
    ok &= _gsettings_set(*_GTK, theme)      # GTK apps
    ok &= _gsettings_set(*_SHELL, theme)    # Cinnamon shell / panel / menus
    ok &= _gsettings_set(*_WM, theme)       # window borders
    ok &= _gsettings_set(*_SCHEME, scheme)  # libadwaita / Flatpak

    print(f"[appearance] → {'dark' if dark else 'light'}: {theme} ({scheme})")
    return ok


def status() -> None:
    """Print the four appearance keys so mismatches are obvious."""
    print(f"  gtk-theme     : {_gsettings_get(*_GTK)}")
    print(f"  cinnamon shell: {_gsettings_get(*_SHELL)}")
    print(f"  wm border     : {_gsettings_get(*_WM)}")
    print(f"  color-scheme  : {_gsettings_get(*_SCHEME)}")
    print(f"  detected accent: {_detect_accent()!r}")


def _main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: python3 -m lumendusk.apply.appearance {dark|light|status}")
        return 0 if argv else 2
    cmd = argv[0]
    if cmd == "status":
        status()
        return 0
    if cmd in ("dark", "light"):
        return 0 if set_appearance(cmd == "dark") else 1
    print(f"[appearance] unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
