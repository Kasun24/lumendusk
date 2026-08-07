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
* **Unkillable by config** — a bad config or a failing backend logs and is
  retried next tick. The loop is the one thing that must not stop; it is often
  running detached with no console attached (see :mod:`lumendusk.log`).
"""

from __future__ import annotations

import time
from datetime import datetime
from enum import Enum

from . import brightness as brightness_mod
from . import config as config_mod
from . import log
from .apply import set_nightlight, set_theme
from .schedule import is_night


class Phase(str, Enum):
    DAY = "day"
    NIGHT = "night"


def current_phase(cfg: config_mod.Config, now: datetime | None = None) -> Phase:
    return Phase.NIGHT if is_night(cfg, now) else Phase.DAY


def apply_phase(phase: Phase, cfg: config_mod.Config) -> None:
    """Apply theme, night light, and brightness for the given phase.

    Each step is independent: a backend that fails (no ddcutil permissions, a
    missing gsettings schema) is logged and the rest still run.
    """
    if not cfg.is_auto():
        log.info("manual mode; leaving the desktop as the user set it.")
        return
    dark = phase is Phase.NIGHT

    try:
        set_theme(dark, cfg)
    except Exception:
        log.exception("failed to apply the %s theme.", phase.value)

    if cfg.nightlight_enabled:
        try:
            set_nightlight(dark, cfg.nightlight_temperature)
        except Exception:
            log.exception("failed to set night light.")

    if cfg.brightness_enabled:
        level = cfg.brightness_night if dark else cfg.brightness_day
        try:
            brightness_mod.set_brightness(level, "all")
            log.info("brightness → %s%%", level)
        except Exception:
            log.exception("failed to set brightness.")


def run_once() -> int:
    """Evaluate the current phase and apply it, then return. Used by ``--once``."""
    cfg = config_mod.load()
    phase = current_phase(cfg)
    log.info("phase now: %s", phase.value)
    apply_phase(phase, cfg)
    return 0


def run_daemon(interval: int = 60, once: bool = False) -> int:
    """Run the main loop. Applies on startup, then only on phase changes."""
    if once:
        return run_once()

    interval = max(1, interval)
    cfg = config_mod.load()
    last: Phase | None = None
    was_manual = not cfg.is_auto()
    last_wall = time.time()

    log.info("logging to %s", log.log_path())

    # Startup: apply once so the desktop matches the current phase — unless the
    # user has put us in manual.
    if was_manual:
        # Manual: touch nothing at all. Not even night light — in manual that's
        # the user's own toggle, and forcing it off here would silently undo it
        # every login. The one-time drop happens when *switching* into manual
        # (below), which is the movie-night case; after that it's theirs.
        log.info("started in manual; leaving the desktop as it is.")
    else:
        phase = current_phase(cfg)
        apply_phase(phase, cfg)
        last = phase
        log.info("started (%s mode); phase=%s, checking every %ss.",
                 cfg.mode, phase.value, interval)

    while True:
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            log.info("stopping.")
            return 0

        try:
            # Detect a suspend/resume clock jump (elapsed >> interval).
            now_wall = time.time()
            if now_wall - last_wall > interval * 3:
                log.info("clock jump detected (resume?); re-evaluating.")
            last_wall = now_wall

            cfg = config_mod.load()  # cheap; lets applet/config edits take effect

            # Manual: leave theme + brightness where the user put them, but turn
            # night light off (true colors). Toggled once, on entering manual.
            if not cfg.is_auto():
                if not was_manual:
                    if cfg.nightlight_enabled:
                        set_nightlight(False)
                    log.info("switched to manual; night light off, "
                             "theme/brightness left alone.")
                was_manual = True
                continue

            phase = current_phase(cfg)

            # Just switched back to automatic: snap to the correct current state.
            if was_manual:
                log.info("switched to automatic; applying the current phase.")
                apply_phase(phase, cfg)
                last = phase
                was_manual = False
                continue

            if phase != last:
                log.info("transition %s → %s", last.value if last else "?",
                         phase.value)
                apply_phase(phase, cfg)
                last = phase
        except KeyboardInterrupt:
            log.info("stopping.")
            return 0
        except Exception:
            # Never let one bad tick end the daemon — log it and try again.
            log.exception("unexpected error during tick; continuing.")
