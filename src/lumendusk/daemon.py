"""Core loop: decide day vs. night, then apply theme + night light on change.

This is a Phase 1 skeleton. The platform-specific "apply" steps are stubs for
now — see the TODOs. The scheduling logic is intentionally simple and cheap.
"""

from __future__ import annotations

import time
from datetime import datetime
from enum import Enum


class Phase(str, Enum):
    """Whether it is currently day or night."""

    DAY = "day"
    NIGHT = "night"


def current_phase(now: datetime | None = None) -> Phase:
    """Return the current day/night phase.

    TODO: replace the naive fixed-hours check with:
      - sunrise/sunset from the user's location (optional `astral` dependency), or
      - user-configured fixed times loaded from config.
    """
    now = now or datetime.now()
    # Placeholder rule: night between 19:00 and 07:00.
    return Phase.NIGHT if now.hour >= 19 or now.hour < 7 else Phase.DAY


def apply_phase(phase: Phase) -> None:
    """Apply the theme and night light for the given phase.

    TODO (Phase 1, Linux Mint / Cinnamon):
      - Theme: `gsettings set org.cinnamon.desktop.interface gtk-theme "<theme>"`
               and `org.gnome.desktop.interface color-scheme` prefer-dark/light.
      - Night light: Cinnamon night-light gsettings keys, or `gammastep`/`xsct`.
    """
    print(f"[lumendusk] applying phase: {phase.value}")


def run_daemon(interval: int = 60, once: bool = False) -> int:
    """Run the main loop.

    Only acts when the phase changes, so it stays cheap between checks.
    """
    last: Phase | None = None
    while True:
        phase = current_phase()
        if phase != last:
            apply_phase(phase)
            last = phase
        if once:
            return 0
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[lumendusk] stopping.")
            return 0
