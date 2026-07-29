"""Brightness control (feature track B1–B3).

Public helpers used by the CLI, the daemon, and (later) the applet. Everything
speaks in 0–100 %, regardless of the underlying backend.
"""

from __future__ import annotations

from .. import log
from .backends import Backlight, BacklightError
from .monitors import list_monitors, select


def set_brightness(percent: int, selector: str = "all") -> list[tuple[str, int]]:
    """Set brightness on the selected monitor(s). Returns (id, percent) applied.

    One monitor failing (no DDC/CI permission, unplugged mid-write) is logged
    and the others still get set.
    """
    monitors = select(list_monitors(), selector)
    applied: list[tuple[str, int]] = []
    for mon in monitors:
        try:
            mon.set(percent)
            applied.append((mon.id, max(0, min(100, int(percent)))))
        except BacklightError as exc:
            log.warning("%s: %s", mon.id, exc)
    return applied


def get_brightness(selector: str = "all") -> list[tuple[str, int | None]]:
    """Read brightness on the selected monitor(s). None where a read failed."""
    monitors = select(list_monitors(), selector)
    result: list[tuple[str, int | None]] = []
    for mon in monitors:
        try:
            result.append((mon.id, mon.get()))
        except BacklightError as exc:
            log.warning("%s: %s", mon.id, exc)
            result.append((mon.id, None))
    return result


__all__ = [
    "Backlight",
    "BacklightError",
    "list_monitors",
    "select",
    "set_brightness",
    "get_brightness",
]
