"""Each phase carries its own appearance, rather than day meaning light.

Day → light and night → dark are defaults, not laws: plenty of people want a
dark desktop at noon and still want the screen warmed and dimmed after sunset.
Two things have to hold for that to be usable:

* the mapping is what decides the theme, everywhere the theme is applied; and
* changing it is a *request*, so it lands now — the transition-only rule that
  protects manual tweaks must not swallow a setting the user just changed.
"""

from __future__ import annotations

import pytest

from lumendusk import config as config_mod
from lumendusk.apply.theme import appearance_for, set_theme
from lumendusk.cli import main
from lumendusk.config import Config


@pytest.fixture
def applied(monkeypatch):
    """Record the appearance handed to the whole-desktop switcher."""
    modes: list[str] = []
    monkeypatch.setattr("lumendusk.apply.theme.appearance.set_mode",
                        lambda mode, accent=None, force=False: modes.append(mode)
                        or True)
    return modes


class TestMapping:
    def test_defaults_are_light_day_dark_night(self):
        cfg = Config()
        assert appearance_for(False, cfg) == "light"
        assert appearance_for(True, cfg) == "dark"

    def test_dark_all_day(self, applied):
        cfg = Config(theme_day="dark")
        set_theme(False, cfg)          # daytime
        set_theme(True, cfg)           # night
        assert applied == ["dark", "dark"]

    def test_light_all_day_still_leaves_night_dark(self, applied):
        # The inverse of the above, and the reason night is configurable too:
        # someone who wants the theme never to move sets both the same.
        cfg = Config(theme_day="light", theme_night="light")
        set_theme(True, cfg)
        assert applied == ["light"]


class TestConfigFile:
    def test_round_trip(self):
        config_mod.save(Config(theme_day="dark", theme_night="light"))
        loaded = config_mod.load()
        assert loaded.theme_day == "dark"
        assert loaded.theme_night == "light"

    def test_nonsense_falls_back_per_phase(self):
        # A hand-edited value that isn't light or dark would have to mean
        # *something* at apply time, and guessing is worse than the default.
        path = config_mod.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('[theme]\nday = "midnight"\nnight = "light"\n')
        loaded = config_mod.load()
        assert loaded.theme_day == "light"      # default, not "midnight"
        assert loaded.theme_night == "light"    # the valid one is kept

    def test_brightness_day_is_not_mistaken_for_theme_day(self):
        # Both tables have a "day" key. They must not read each other's.
        config_mod.save(Config(theme_day="dark", brightness_day=45))
        loaded = config_mod.load()
        assert loaded.theme_day == "dark"
        assert loaded.brightness_day == 45


class TestCli:
    def test_set_rejects_anything_but_light_or_dark(self, capsys):
        assert main(["config", "set", "theme_day", "dark"]) == 0
        assert main(["config", "set", "theme_day", "purple"]) == 2
        assert "light" in capsys.readouterr().err
        assert config_mod.load().theme_day == "dark"

    def test_appearance_auto_applies_the_configured_appearance(self, applied):
        # Fixed times with an all-day dark preference: whichever phase we are
        # in, "auto" must ask for dark.
        config_mod.save(Config(theme_day="dark", theme_night="dark"))
        assert main(["appearance", "auto"]) == 0
        assert applied == ["dark"]

    def test_status_explains_a_non_obvious_mapping(self, capsys):
        config_mod.save(Config(theme_day="dark", theme_night="dark"))
        main(["status"])
        assert "stays dark in both phases" in capsys.readouterr().out

    def test_status_stays_quiet_about_the_default(self, capsys):
        config_mod.save(Config())
        main(["status"])
        assert "appearance" not in capsys.readouterr().out


class TestDaemonPicksUpTheChange:
    """A changed setting must not wait for the next transition.

    Transition-only apply exists to protect changes the *user* makes by hand
    mid-period. A setting they just edited is the opposite of that — sitting on
    it until sunset would look like the setting simply doesn't work.
    """

    def test_a_new_daytime_appearance_lands_on_the_next_tick(self, run_ticks):
        config_mod.save(Config(control="auto", light_start="00:00",
                               dark_start="23:59"))   # always day

        def on_tick(n):
            if n == 1:
                cfg = config_mod.load()
                cfg.theme_day = "dark"
                config_mod.save(cfg)
                return True
            return False

        calls = run_ticks(on_tick)
        # Startup applied light; the tick after the edit applied dark, without
        # any transition having happened.
        assert calls["theme"] == ["light", "dark"]

    def test_only_the_theme_moves(self, run_ticks):
        """Night light and brightness don't depend on this setting.

        Re-applying them here would stomp on a brightness the user nudged with
        the panel slider earlier in the same period.
        """
        config_mod.save(Config(control="auto", light_start="00:00",
                               dark_start="23:59", nightlight_enabled=True,
                               brightness_enabled=True))

        def on_tick(n):
            if n == 1:
                cfg = config_mod.load()
                cfg.theme_day = "dark"
                config_mod.save(cfg)
                return True
            return False

        calls = run_ticks(on_tick)
        assert calls["theme"] == ["light", "dark"]
        assert [on for on, _ in calls["nightlight"]] == [False]   # startup only
        assert calls["brightness"] == [80]                        # startup only

    def test_an_unchanged_setting_applies_nothing(self, run_ticks):
        config_mod.save(Config(control="auto", light_start="00:00",
                               dark_start="23:59"))
        calls = run_ticks(lambda n: n < 3)
        assert calls["theme"] == ["light"], "startup only — no repeated writes"
