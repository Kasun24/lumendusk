"""Command-line interface.

    lumendusk                 run the daemon (loop)
    lumendusk --once          evaluate + apply current phase, then exit
    lumendusk brightness list      show monitors + backend + current level
    lumendusk brightness get       print current brightness
    lumendusk brightness set 60    set brightness to 60 %
    lumendusk brightness day       apply the day preset from config
    lumendusk brightness night     apply the night preset from config

Most brightness commands accept ``--monitor <id>`` (default: all).
"""

from __future__ import annotations

import argparse

from . import __version__
from . import brightness as brightness_mod
from . import config as config_mod
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
    return parser


def _set_paused(paused: bool) -> int:
    cfg = config_mod.load()
    cfg.paused = paused
    config_mod.save(cfg)
    print(f"[lumendusk] automation {'paused' if paused else 'resumed'}.")
    return 0


def _status() -> int:
    from .daemon import current_phase  # local import avoids a cycle at import time
    cfg = config_mod.load()
    phase = current_phase(cfg).value
    state = "paused" if cfg.paused else ("enabled" if cfg.enabled else "disabled")
    print(f"mode={cfg.mode} phase={phase} state={state}")
    return 0


def _brightness_command(args: argparse.Namespace) -> int:
    action = args.action
    if action == "list":
        monitors = brightness_mod.list_monitors()
        if not monitors:
            print("[lumendusk] no controllable monitors detected.")
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
            print("[lumendusk] 'brightness set' needs a value, e.g. 'set 60'.")
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
        return _brightness_command(args)
    if args.command == "pause":
        return _set_paused(True)
    if args.command == "resume":
        return _set_paused(False)
    if args.command == "toggle":
        return _set_paused(not config_mod.load().paused)
    if args.command == "status":
        return _status()
    return run_daemon(interval=args.interval, once=args.once)
