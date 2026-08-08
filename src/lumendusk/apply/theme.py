"""Apply the desktop dark/light appearance for day or night.

Thin adapter over :mod:`lumendusk.apply.appearance`, the whole-desktop switcher.
Day → light, night → dark. The switcher moves every appearance key together
(shell, window borders, GTK, libadwaita/GTK4, Flatpak portal, icons, accent),
so app windows and the Cinnamon UI stay in sync — the old two-key approach left
the panel and borders behind.
"""

from __future__ import annotations

from ..config import Config
from . import appearance


def set_theme(dark: bool, config: Config, force: bool = False) -> None:
    mode = "dark" if dark else "light"
    # Blank accent = keep the user's current accent (auto-detected).
    accent = (config.theme_accent or "").strip() or None
    appearance.set_mode(mode, accent=accent, force=force)
