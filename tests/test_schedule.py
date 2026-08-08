"""Day/night decision logic — the part that must never be wrong or crash."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from lumendusk.config import Config
from lumendusk.schedule import is_night


def at(hour: int, minute: int = 0, offset_hours: float = 0) -> datetime:
    tz = timezone(timedelta(hours=offset_hours))
    return datetime(2026, 7, 27, hour, minute, tzinfo=tz)


class TestFixedMode:
    @pytest.mark.parametrize("hour,expected_night", [
        (0, True), (6, True), (7, False), (12, False),
        (18, False), (19, True), (23, True),
    ])
    def test_night_wraps_past_midnight(self, hour, expected_night):
        cfg = Config(mode="fixed", dark_start="19:00", light_start="07:00")
        assert is_night(cfg, at(hour)) is expected_night

    def test_boundaries_are_inclusive_at_dark_exclusive_at_light(self):
        cfg = Config(mode="fixed", dark_start="19:00", light_start="07:00")
        assert is_night(cfg, at(18, 59)) is False
        assert is_night(cfg, at(19, 0)) is True
        assert is_night(cfg, at(6, 59)) is True
        assert is_night(cfg, at(7, 0)) is False

    def test_reversed_order_treats_the_gap_as_night(self):
        # Unusual but legal: dark at 02:00, light at 05:00.
        cfg = Config(mode="fixed", dark_start="02:00", light_start="05:00")
        assert is_night(cfg, at(3)) is True
        assert is_night(cfg, at(12)) is False

    @pytest.mark.parametrize("dark,light", [
        ("7pm", "07:00"),          # not HH:MM
        ("19:00", ""),             # empty
        ("25:00", "07:00"),        # hour out of range
        ("19:61", "07:00"),        # minute out of range
        ("nineteen", "seven"),     # nonsense
    ])
    def test_malformed_times_fall_back_instead_of_raising(self, dark, light):
        cfg = Config(mode="fixed", dark_start=dark, light_start=light)
        # Defaults are 19:00/07:00, so midnight is night either way — the point
        # is that this returns a bool rather than raising.
        assert isinstance(is_night(cfg, at(0)), bool)

    def test_identical_times_do_not_flap(self):
        cfg = Config(mode="fixed", dark_start="12:00", light_start="12:00")
        assert is_night(cfg, at(11)) is False
        assert is_night(cfg, at(13)) is False

    def test_unknown_mode_falls_back_to_fixed(self):
        cfg = Config(mode="banana", dark_start="19:00", light_start="07:00")
        assert is_night(cfg, at(22)) is True
        assert is_night(cfg, at(12)) is False


class TestSunMode:
    def test_unset_location_uses_fixed_times(self):
        """The 0,0 default must not produce Gulf-of-Guinea sun times.

        This is the first-run case: mode was switched to sun but no location
        was ever entered. Sun times for 0,0 in a +5:30 timezone would call
        10:00 local 'night'; the fixed-time fallback must not.
        """
        cfg = Config(mode="sun", latitude=0.0, longitude=0.0,
                     dark_start="19:00", light_start="07:00")
        assert is_night(cfg, at(10, offset_hours=5.5)) is False
        assert is_night(cfg, at(20, offset_hours=5.5)) is True

    def test_real_location_uses_sun_times(self):
        pytest.importorskip("astral")
        # London in late July: sunrise ~05:15, sunset ~21:00 local (BST, +01:00).
        cfg = Config(mode="sun", latitude=51.5074, longitude=-0.1278)
        assert is_night(cfg, at(12, offset_hours=1)) is False
        assert is_night(cfg, at(23, offset_hours=1)) is True

    def test_solar_day_may_straddle_the_utc_date(self):
        """Anchorage's sunset falls on the *next* UTC day.

        Asking astral for "today's sunrise and sunset" returns both pinned to
        the date requested, so the sunset comes back earlier than the sunrise
        and every evening reads as night. Everywhere west of ~UTC-8 and across
        the Pacific is affected, so this is not an edge case.
        """
        pytest.importorskip("astral")
        cfg = Config(mode="sun", latitude=61.2181, longitude=-149.9003)
        # 20:00 local (UTC-8) on a July evening — the sun is still well up.
        assert is_night(cfg, at(20, offset_hours=-8)) is False
        assert is_night(cfg, at(2, offset_hours=-8)) is True

    def test_polar_summer_is_day_and_polar_winter_is_night(self):
        pytest.importorskip("astral")
        # Svalbard: midnight sun in July, and no sunrise at all in January.
        cfg = Config(mode="sun", latitude=78.22, longitude=15.65)
        midnight_july = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
        noon_january = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
        assert is_night(cfg, midnight_july) is False
        assert is_night(cfg, noon_january) is True

    def test_missing_astral_falls_back(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def no_astral(name, *args, **kwargs):
            if name.startswith("astral"):
                raise ImportError("no astral")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_astral)
        cfg = Config(mode="sun", latitude=51.5, longitude=-0.13,
                     dark_start="19:00", light_start="07:00")
        assert is_night(cfg, at(22)) is True
