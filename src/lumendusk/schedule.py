"""Decide whether it is currently day or night.

Two modes, both pure-Python and offline:

* ``sun``   — sunrise/sunset for the user's latitude/longitude, via ``astral``.
* ``fixed`` — user-set clock times (``dark_start`` / ``light_start``).

If ``astral`` is not installed while in sun mode, we log once and fall back to
fixed times so the daemon still does something sensible.
"""

from __future__ import annotations

from datetime import datetime

from .config import Config

_warned_no_astral = False


def _hhmm_to_minutes(value: str) -> int:
    hh, mm = value.split(":")
    return int(hh) * 60 + int(mm)


def _fixed_is_night(config: Config, now: datetime) -> bool:
    now_min = now.hour * 60 + now.minute
    dark = _hhmm_to_minutes(config.dark_start)
    light = _hhmm_to_minutes(config.light_start)
    if dark <= light:
        # Unusual ordering (dark before light on the same day): night is the
        # window between them.
        return dark <= now_min < light
    # Normal case: night wraps past midnight (e.g. 19:00 → 07:00).
    return now_min >= dark or now_min < light


def _sun_is_night(config: Config, now: datetime) -> bool:
    global _warned_no_astral
    try:
        from astral import LocationInfo
        from astral.sun import sun
    except ImportError:
        if not _warned_no_astral:
            print(
                "[lumendusk] astral not installed; sun mode unavailable, "
                "falling back to fixed times. Install with: pip install 'lumendusk[sun]'"
            )
            _warned_no_astral = True
        return _fixed_is_night(config, now)

    # Work in the machine's local timezone so comparisons line up.
    local = now.astimezone()
    loc = LocationInfo(latitude=config.latitude, longitude=config.longitude)
    times = sun(loc.observer, date=local.date(), tzinfo=local.tzinfo)
    return local < times["sunrise"] or local >= times["sunset"]


def is_night(config: Config, now: datetime | None = None) -> bool:
    """Return True if it is currently night under the configured mode."""
    now = now or datetime.now().astimezone()
    if config.mode == "sun":
        return _sun_is_night(config, now)
    return _fixed_is_night(config, now)
