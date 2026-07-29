"""Command-line interface.

    lumendusk                 run the daemon (loop)
    lumendusk --once          evaluate + apply current phase, then exit
    lumendusk brightness list      show monitors + backend + current level
    lumendusk brightness get       print current brightness
    lumendusk brightness set 60    set brightness to 60 %
    lumendusk brightness day       apply the day preset from config
    lumendusk brightness night     apply the night preset from config
    lumendusk mode day             switch to full day mode now (manual override)
    lumendusk mode night           switch to full night mode now (manual override)
    lumendusk pause / resume       freeze automation (night light off) / resume
    lumendusk location 51.5 -0.13  set your location and switch to sun mode

Most brightness commands accept ``--monitor <id>`` (default: all).
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from . import brightness as brightness_mod
from . import config as config_mod
from . import log
from .daemon import run_daemon


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lumendusk",
        description="Automatic dark/light theme, night light, and brightness.",
    )
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    parser.add_argument("--once", action="store_true",
                        help="Evaluate and apply once, then exit (no loop).")
    parser.add_argument("--interval", type=int, default=60,
                        help="Seconds between checks in daemon mode (default: 60).")

    sub = parser.add_subparsers(dest="command")
    b = sub.add_parser("brightness", help="Read/set monitor brightness.")
    b.add_argument("action", choices=["get", "set", "list", "day", "night"])
    b.add_argument("value", nargs="?", type=int,
                   help="Percent 0–100 (only for 'set').")
    b.add_argument("--monitor", default="all",
                   help="Monitor id (see 'brightness list'), or 'all'.")

    sub.add_parser("pause", help="Freeze automation (e.g. while watching a movie).")
    sub.add_parser("resume", help="Resume automation and snap to the current state.")
    sub.add_parser("toggle", help="Toggle the paused state.")
    sub.add_parser("status", help="Print current mode, phase, and paused state.")

    m = sub.add_parser("mode", help="Manually switch to full day/night mode now.")
    m.add_argument("which", choices=["day", "night"])

    a = sub.add_parser("appearance",
                       help="Dark/light desktop switch (system UI + apps).")
    a.add_argument("which", choices=["dark", "light", "toggle", "status"])

    loc = sub.add_parser(
        "location",
        help="Set your latitude/longitude and switch to sun mode.")
    loc.add_argument("latitude", type=float, help="Decimal latitude, e.g. 51.5074")
    loc.add_argument("longitude", type=float, help="Decimal longitude, e.g. -0.1278")
    return parser


def _set_paused(paused: bool) -> int:
    cfg = config_mod.load()
    cfg.paused = paused
    config_mod.save(cfg)
    # Act immediately so the applet feels responsive (the daemon reconciles too).
    if paused:
        # Movie/manual pause: night light off for true colors; theme + brightness
        # stay frozen wherever they are.
        if cfg.nightlight_enabled:
            from .apply import set_nightlight
            set_nightlight(False)
        log.info("paused; night light off, theme/brightness frozen.")
    else:
        # Resume: snap straight to the correct current phase.
        from .daemon import apply_phase, current_phase
        apply_phase(current_phase(cfg), cfg)
        log.info("resumed; applied current phase.")
    return 0


def _set_location(latitude: float, longitude: float) -> int:
    """Store a location and switch to sun mode (the point of having one)."""
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        print("latitude must be -90..90 and longitude -180..180.", file=sys.stderr)
        return 2
    cfg = config_mod.load()
    cfg.latitude, cfg.longitude = latitude, longitude
    cfg.mode = "sun"
    config_mod.save(cfg)
    print(f"location set to {latitude}, {longitude}; mode is now 'sun'.")
    if not cfg.location_is_set():
        print("note: 0, 0 is treated as 'not set' — sun mode will use the "
              "fixed times until a real location is given.", file=sys.stderr)
    return 0


def _appearance_command(which: str) -> int:
    """Standalone dark/light switch (separate from the day/night theme path)."""
    from .apply import appearance
    if which == "status":
        appearance.status()
        return 0
    if which == "toggle":
        which = "light" if appearance.current_mode() == "dark" else "dark"
    return 0 if appearance.set_mode(which) else 1


def _apply_mode(which: str) -> int:
    """Manually apply full day or night mode (theme + night light + brightness).

    A manual override: the transition-only daemon leaves it alone until the next
    scheduled day/night transition.
    """
    from .daemon import Phase, apply_phase
    cfg = config_mod.load()
    phase = Phase.NIGHT if which == "night" else Phase.DAY
    apply_phase(phase, cfg)
    log.info("switched to %s mode (manual).", which)
    return 0


def _status() -> int:
    from .daemon import current_phase  # local import avoids a cycle at import time
    cfg = config_mod.load()
    phase = current_phase(cfg).value
    state = "paused" if cfg.paused else ("enabled" if cfg.enabled else "disabled")
    print(f"mode={cfg.mode} phase={phase} state={state}")
    if cfg.mode == "sun" and not cfg.location_is_set():
        print(f"  sun mode has no location set, so the fixed times "
              f"({cfg.light_start}–{cfg.dark_start}) are in use. Set one with: "
              f"lumendusk location <lat> <lon>")
    print(f"  config: {config_mod.config_path()}")
    print(f"  log:    {log.log_path()}")
    return 0


def _brightness_command(args: argparse.Namespace) -> int:
    action = args.action
    if action == "list":
        monitors = brightness_mod.list_monitors()
        if not monitors:
            print("no controllable monitors detected. For external monitors, "
                  "install ddcutil, load the i2c-dev module, and add yourself "
                  "to the 'i2c' group.", file=sys.stderr)
            return 1
        for mon in monitors:
            try:
                level = f"{mon.get()}%"
            except brightness_mod.BacklightError as exc:
                level = f"(read failed: {exc})"
            tag = "" if mon.real else "  [software dimming]"
            print(f"  {mon.id:<12} {mon.backend:<12} {level:<8} {mon.label}{tag}")
        return 0

    if action == "get":
        for mid, level in brightness_mod.get_brightness(args.monitor):
            print(f"  {mid}: {level if level is not None else '?'}%")
        return 0

    if action == "set":
        if args.value is None:
            print("'brightness set' needs a value, e.g. 'set 60'.", file=sys.stderr)
            return 2
        for mid, level in brightness_mod.set_brightness(args.value, args.monitor):
            print(f"  {mid} → {level}%")
        return 0

    # day / night presets from config
    cfg = config_mod.load()
    level = cfg.brightness_day if action == "day" else cfg.brightness_night
    for mid, applied in brightness_mod.set_brightness(level, args.monitor):
        print(f"  {mid} → {applied}% ({action} preset)")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "brightness":
        try:
            return _brightness_command(args)
        except brightness_mod.BacklightError as exc:
            print(exc, file=sys.stderr)
            return 1
    if args.command == "location":
        return _set_location(args.latitude, args.longitude)
    if args.command == "pause":
        return _set_paused(True)
    if args.command == "resume":
        return _set_paused(False)
    if args.command == "toggle":
        return _set_paused(not config_mod.load().paused)
    if args.command == "status":
        return _status()
    if args.command == "mode":
        return _apply_mode(args.which)
    if args.command == "appearance":
        return _appearance_command(args.which)
    return run_daemon(interval=args.interval, once=args.once)
