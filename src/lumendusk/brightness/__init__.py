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

    Every change is logged *here*, not at the call sites, for two reasons.

    One: this is the only place that knows what actually happened. A caller
    that logs the level it asked for reports success even when every backend
    refused — and that is exactly the lie that hides a broken ddcutil setup for
    weeks.

    Two: the applet's slider writes through the CLI, so brightness used to be
    the one subsystem that could change with no trace at all, while theme and
    night light logged every move. That gap turned a two-line discrepancy into
    a real debugging session.
    """
    monitors = select(list_monitors(), selector)
    if not monitors:
        log.warning("no monitors matched %r; brightness unchanged.", selector)
        return []

    applied: list[tuple[str, int]] = []
    failed: list[str] = []
    for mon in monitors:
        try:
            mon.set(percent)
            applied.append((mon.id, max(0, min(100, int(percent)))))
        except BacklightError as exc:
            log.warning("%s: %s", mon.id, exc)
            failed.append(mon.id)

    level = max(0, min(100, int(percent)))
    names = ", ".join(mid for mid, _ in applied)
    if not applied:
        log.warning("brightness → %s%% failed on every monitor (%s).",
                    level, ", ".join(failed))
    elif failed:
        log.info("brightness → %s%% on %s (%s failed).",
                 level, names, ", ".join(failed))
    else:
        log.info("brightness → %s%% on %s.", level, names)
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
    "get_brightness",
    "list_monitors",
    "select",
    "set_brightness",
]
