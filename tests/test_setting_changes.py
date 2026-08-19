"""A setting you just changed has to show up now, not at the next transition.

Transition-only apply protects changes the *user* makes by hand: nudge the
brightness at 9pm and the daemon leaves it alone until sunrise. A value edited in
the settings panel is the opposite — dragging "night brightness" after dark and
watching nothing happen reads as a broken control, not as restraint.

Telling the two apart is what :class:`~lumendusk.daemon.PhaseState` is for, and
the same diff runs on the daemon's tick and behind ``config set --apply`` so the
panel and the schedule can't disagree about it.
"""

from __future__ import annotations

from lumendusk import config as config_mod
from lumendusk.cli import main
from lumendusk.config import Config
from lumendusk.daemon import Phase, PhaseState, phase_state

ALWAYS_NIGHT = {"control": "auto", "light_start": "23:58", "dark_start": "23:59"}
ALWAYS_DAY = {"control": "auto", "light_start": "00:00", "dark_start": "23:59"}


def edit_on_first_tick(**changes):
    """An on_tick that edits the config once, then runs one more tick."""
    def on_tick(n):
        if n == 1:
            cfg = config_mod.load()
            for key, value in changes.items():
                setattr(cfg, key, value)
            config_mod.save(cfg)
            return True
        return False
    return on_tick


class TestState:
    def test_night_carries_the_temperature_and_day_does_not(self):
        cfg = Config(nightlight_enabled=True, nightlight_temperature=2500)
        assert phase_state(Phase.NIGHT, cfg).nightlight == (True, 2500)
        # Off is off at every temperature, so daytime holds no temperature at
        # all — otherwise editing it at noon would look like a change.
        assert phase_state(Phase.DAY, cfg).nightlight == (False, 0)
        assert (phase_state(Phase.DAY, cfg)
                == phase_state(Phase.DAY, Config(nightlight_temperature=6000)))

    def test_only_this_phase_s_brightness_counts(self):
        cfg = Config(brightness_enabled=True, brightness_day=80,
                     brightness_night=30)
        assert phase_state(Phase.DAY, cfg).brightness == 80
        assert phase_state(Phase.NIGHT, cfg).brightness == 30

    def test_brightness_automation_off_is_not_zero_percent(self):
        # A real distinction: 0% is a setting, "off" means don't touch it.
        assert phase_state(Phase.DAY, Config(brightness_enabled=False)).brightness is None
        assert phase_state(
            Phase.DAY, Config(brightness_enabled=True, brightness_day=0)
        ).brightness == 0


class TestDaemon:
    def test_a_warmer_night_light_lands_on_the_next_tick(self, run_ticks):
        config_mod.save(Config(**ALWAYS_NIGHT, nightlight_enabled=True,
                               nightlight_temperature=4000))
        calls = run_ticks(edit_on_first_tick(nightlight_temperature=2500))
        assert calls["nightlight"] == [(True, 4000), (True, 2500)]

    def test_switching_night_light_off_at_night_turns_it_off(self, run_ticks):
        config_mod.save(Config(**ALWAYS_NIGHT, nightlight_enabled=True,
                               nightlight_temperature=4000))
        calls = run_ticks(edit_on_first_tick(nightlight_enabled=False))
        assert calls["nightlight"] == [(True, 4000), (False, 4000)]

    def test_a_new_night_brightness_lands_on_the_next_tick(self, run_ticks):
        config_mod.save(Config(**ALWAYS_NIGHT, brightness_enabled=True,
                               brightness_night=30))
        calls = run_ticks(edit_on_first_tick(brightness_night=90))
        assert calls["brightness"] == [30, 90]

    def test_the_other_phase_s_preset_changes_nothing(self, run_ticks):
        """Editing the day preset after dark must not move tonight's screen.

        This is the case that makes the diff worth having rather than just
        re-applying everything on any config change: the user may well have
        nudged the brightness by hand an hour ago.
        """
        config_mod.save(Config(**ALWAYS_NIGHT, brightness_enabled=True,
                               brightness_day=80, brightness_night=30))
        calls = run_ticks(edit_on_first_tick(brightness_day=15))
        assert calls["brightness"] == [30], "startup only"

    def test_the_temperature_is_inert_during_the_day(self, run_ticks):
        config_mod.save(Config(**ALWAYS_DAY, nightlight_enabled=True,
                               nightlight_temperature=4000))
        calls = run_ticks(edit_on_first_tick(nightlight_temperature=2500))
        assert [on for on, _ in calls["nightlight"]] == [False], "startup only"

    def test_one_change_does_not_re_apply_the_others(self, run_ticks):
        config_mod.save(Config(**ALWAYS_NIGHT, nightlight_enabled=True,
                               brightness_enabled=True, brightness_night=30))
        calls = run_ticks(edit_on_first_tick(brightness_night=90))
        assert calls["brightness"] == [30, 90]
        assert len(calls["theme"]) == 1, "startup only"
        assert len(calls["nightlight"]) == 1, "startup only"

    def test_manual_still_ignores_everything(self, run_ticks):
        config_mod.save(Config(control="manual", light_start="23:58",
                               dark_start="23:59", brightness_enabled=True))
        calls = run_ticks(edit_on_first_tick(brightness_night=90))
        assert calls == {"theme": [], "nightlight": [], "brightness": []}


class TestConfigSetApply:
    """``--apply`` is how the settings panel gets the same result at once."""

    def test_apply_shows_the_change_now(self, applies):
        config_mod.save(Config(**ALWAYS_NIGHT, brightness_enabled=True,
                               brightness_night=30))
        assert main(["config", "set", "brightness_night", "90", "--apply"]) == 0
        assert applies["brightness"] == [90]

    def test_without_apply_it_is_only_stored(self, applies):
        config_mod.save(Config(**ALWAYS_NIGHT, brightness_enabled=True,
                               brightness_night=30))
        assert main(["config", "set", "brightness_night", "90"]) == 0
        assert config_mod.load().brightness_night == 90
        assert applies["brightness"] == []

    def test_apply_leaves_the_other_phase_alone(self, applies):
        config_mod.save(Config(**ALWAYS_NIGHT, brightness_enabled=True,
                               brightness_day=80, brightness_night=30))
        assert main(["config", "set", "brightness_day", "15", "--apply"]) == 0
        assert applies["brightness"] == []

    def test_apply_touches_nothing_in_manual(self, applies):
        config_mod.save(Config(control="manual", brightness_enabled=True,
                               brightness_night=30))
        assert main(["config", "set", "brightness_night", "90", "--apply"]) == 0
        assert applies == {"theme": [], "nightlight": [], "brightness": []}

    def test_a_rejected_value_is_neither_stored_nor_applied(self, applies):
        config_mod.save(Config(**ALWAYS_NIGHT, brightness_enabled=True,
                               brightness_night=30))
        assert main(["config", "set", "brightness_night", "500", "--apply"]) == 2
        assert config_mod.load().brightness_night == 30
        assert applies["brightness"] == []

    def test_appearance_still_applies_through_the_same_path(self, applies):
        config_mod.save(Config(**ALWAYS_DAY, theme_day="light"))
        assert main(["config", "set", "theme_day", "dark", "--apply"]) == 0
        assert applies["theme"] == ["dark"]


class TestUnchangedIsUnchanged:
    def test_storing_the_same_value_applies_nothing(self, applies):
        config_mod.save(Config(**ALWAYS_NIGHT, brightness_enabled=True,
                               brightness_night=30))
        assert main(["config", "set", "brightness_night", "30", "--apply"]) == 0
        assert applies["brightness"] == []

    def test_states_compare_equal_by_value(self):
        cfg = Config()
        assert phase_state(Phase.DAY, cfg) == phase_state(Phase.DAY, Config())
        assert isinstance(phase_state(Phase.DAY, cfg), PhaseState)
