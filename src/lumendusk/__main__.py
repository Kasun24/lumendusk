"""Command-line entry point for Lumendusk."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .daemon import run_daemon


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lumendusk",
        description="Automatic dark/light theme and night light for your desktop.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Evaluate day/night once, apply the state, then exit (no loop).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between checks when running as a daemon (default: 60).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_daemon(interval=args.interval, once=args.once)


if __name__ == "__main__":
    sys.exit(main())
