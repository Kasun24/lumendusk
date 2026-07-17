"""Core loop: decide day vs. night, then apply theme + night light + brightness.

Key behaviours from the plan:

* **Transition-only apply** — we apply on startup, then only when the phase
  actually changes. This is what makes manual overrides stick: if you tweak the
  theme or brightness by hand mid-period, the daemon leaves it alone until the
  next real day↔night transition.
* **Suspend/resume safety** — every tick re-evaluates the phase, so if the clock
  jumped across a transition while asleep, the change is caught on the next tick
  rather than waiting a full period. Large wall-clock jumps are logged.
* **Cheap** — sleeps ``interval`` seconds between ticks; near-zero CPU otherwise.
"""

from __future__ import annotations

import time
from datetime import datetime
from enum import Enum

from . import brightness as brightness_mod
from . import config as config_mod
from .apply import set_nightlight, set_theme
from .schedule import is_night


class Phase(str, Enum):
    DAY = "day"
    NIGHT = "night"


def current_phase(cfg: config_mod.Config, now: datetime | None = None) -> Phase:
    return Phase.NIGHT if is_night(cfg, now) else Phase.DAY


def apply_phase(phase: Phase, cfg: config_mod.Config) -> None:
    """Apply theme, night light, and brightness for the given phase."""
    if not cfg.enabled:
        print("[lumendusk] disabled in config; skipping apply.")
        return
    dark = phase is Phase.NIGHT
    set_theme(dark, cfg)
    if cfg.nightlight_enabled:
        set_nightlight(dark, cfg.nightlight_temperature)
    if cfg.brightness_enabled:
        level = cfg.brightness_night if dark else cfg.brightness_day
        brightness_mod.set_brightness(level, "all")
        print(f"[lumendusk] brightness → {level}%")


def run_once() -> int:
    """Evaluate the current phase and apply it, then return. Used by ``--once``."""
    cfg = config_mod.load()
    phase = current_phase(cfg)
    print(f"[lumendusk] phase now: {phase.value}")
    apply_phase(phase, cfg)
    return 0


def run_daemon(interval: int = 60, once: bool = False) -> int:
    """Run the main loop. Applies on startup, then only on phase changes."""
    if once:
        return run_once()

    cfg = config_mod.load()
    last: Phase | None = None
    was_paused = cfg.paused
    last_wall = time.time()

    # Startup: apply once so the desktop matches the current phase — unless the
    # user left automation paused.
    if cfg.paused:
        # Paused = manual/movie mode: drop night light for true colors, but
        # leave theme + brightness frozen wherever the user has them.
        if cfg.nightlight_enabled:
            set_nightlight(False)
        print("[lumendusk] started paused; night light off, theme/brightness frozen.")
    else:
        phase = current_phase(cfg)
        apply_phase(phase, cfg)
        last = phase
        print(f"[lumendusk] started ({cfg.mode} mode); phase={phase.value}, "
              f"checking every {interval}s.")

    while True:
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[lumendusk] stopping.")
            return 0

        # Detect a suspend/resume clock jump (elapsed >> interval).
        now_wall = time.time()
        if now_wall - last_wall > interval * 3:
            print("[lumendusk] clock jump detected (resume?); re-evaluating.")
        last_wall = now_wall

        cfg = config_mod.load()  # cheap; lets applet/config edits take effect

        # Paused: freeze theme + brightness where they are, but turn night light
        # off (true colors for movies). Do the toggle once, on entering pause.
        if cfg.paused:
            if not was_paused:
                if cfg.nightlight_enabled:
                    set_nightlight(False)
                print("[lumendusk] paused; night light off, theme/brightness frozen.")
            was_paused = True
            continue

        phase = current_phase(cfg)

        # Just resumed from pause: snap to the correct current state.
        if was_paused:
            print("[lumendusk] resumed; applying current phase.")
            apply_phase(phase, cfg)
            last = phase
            was_paused = False
            continue

        if phase != last:
            print(f"[lumendusk] transition {last.value if last else '?'} → "
                  f"{phase.value}")
            apply_phase(phase, cfg)
            last = phase
