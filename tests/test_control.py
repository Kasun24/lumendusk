"""Automatic vs. manual: who is allowed to touch the desktop.

The whole promise of manual mode is that Lumendusk keeps its hands off. That is
easy to break by accident — a new "apply" call added to the daemon, a CLI path
that forgets to check — and the symptom (your theme flips while you're watching
a film) is exactly the thing the mode exists to prevent. So assert it directly.
"""

from __future__ import annotations

import pytest

from lumendusk import config as config_mod
from lumendusk import daemon as daemon_mod
from lumendusk.cli import main
from lumendusk.config import Config


@pytest.fixture
def applied(monkeypatch):
    """Record every desktop-touching call the engine makes.

    ``forced`` collects the ``force`` flag each apply was given, which is what
    separates a reconciliation pass (skip settings already correct) from the
    explicit "apply now" (rewrite regardless).
    """
    calls = {"theme": [], "nightlight": [], "brightness": [], "forced": []}

    def theme(dark, cfg, force=False):
        calls["theme"].append(dark)
        calls["forced"].append(force)

    def nightlight(dark, temp=None, force=False):
        calls["nightlight"].append(dark)

    monkeypatch.setattr(daemon_mod, "set_theme", theme)
    monkeypatch.setattr(daemon_mod, "set_nightlight", nightlight)
    monkeypatch.setattr(daemon_mod.brightness_mod, "set_brightness",
                        lambda level, target: calls["brightness"].append(level))
    return calls


class TestApplyPhase:
    def test_automatic_applies_everything(self, applied):
        cfg = Config(control="auto", nightlight_enabled=True,
                     brightness_enabled=True, brightness_night=20)
        daemon_mod.apply_phase(daemon_mod.Phase.NIGHT, cfg)
        assert applied["theme"] == [True]
        assert applied["nightlight"] == [True]
        assert applied["brightness"] == [20]

    def test_manual_touches_nothing(self, applied):
        cfg = Config(control="manual", nightlight_enabled=True,
                     brightness_enabled=True)
        daemon_mod.apply_phase(daemon_mod.Phase.NIGHT, cfg)
        assert applied["theme"] == []
        assert applied["nightlight"] == []
        assert applied["brightness"] == []

    def test_run_once_respects_manual(self, applied):
        config_mod.save(Config(control="manual"))
        assert daemon_mod.run_once() == 0
        assert applied["theme"] == []

    def test_a_scheduled_apply_does_not_force(self, applied):
        """The daemon reconciles; it must not rewrite what is already right."""
        daemon_mod.apply_phase(daemon_mod.Phase.NIGHT, Config(control="auto"))
        assert applied["forced"] == [False]

    def test_apply_now_forces(self, applied):
        """`--once` is the repair button: it rewrites even correct-looking keys.

        Someone reaches for it *because* the desktop looks wrong, and the case
        it has to fix is a setting that reads correct while the desktop isn't.
        """
        config_mod.save(Config(control="auto"))
        assert daemon_mod.run_once() == 0
        assert applied["forced"] == [True]


class TestCliSwitching:
    def test_manual_turns_night_light_off_and_freezes(self, applied, monkeypatch):
        # set_nightlight is imported inside _set_control, so patch it at source.
        from lumendusk import apply as apply_mod
        monkeypatch.setattr(apply_mod, "set_nightlight",
                            lambda dark, temp=None: applied["nightlight"].append(dark))
        config_mod.save(Config(control="auto", nightlight_enabled=True))

        assert main(["manual"]) == 0
        assert config_mod.load().control == "manual"
        assert applied["nightlight"] == [False], "night light should be dropped"
        assert applied["theme"] == [], "the theme must be left where the user put it"

    def test_auto_snaps_to_the_current_phase(self, applied):
        config_mod.save(Config(control="manual"))
        assert main(["auto"]) == 0
        assert config_mod.load().control == "auto"
        assert len(applied["theme"]) == 1, "should apply immediately, not next tick"

    def test_toggle_flips_between_the_two(self, applied):
        config_mod.save(Config(control="auto"))
        main(["toggle"])
        assert config_mod.load().control == "manual"
        main(["toggle"])
        assert config_mod.load().control == "auto"

    @pytest.mark.parametrize("alias,expected", [
        ("pause", "manual"),
        ("resume", "auto"),
    ])
    def test_the_old_names_still_work(self, alias, expected, applied):
        """Documented in older READMEs and in people's scripts."""
        assert main([alias]) == 0
        assert config_mod.load().control == expected


class TestConfigSet:
    @pytest.mark.parametrize("value", ["auto", "manual"])
    def test_accepts_both_modes(self, value, capsys):
        assert main(["config", "set", "control", value]) == 0
        capsys.readouterr()
        assert config_mod.load().control == value

    def test_refuses_anything_else(self, capsys):
        assert main(["config", "set", "control", "paused"]) == 2
        assert config_mod.load().control == "auto"


class TestManualNightlight:
    """In manual there's no schedule, so warmth needs its own live switch."""

    @pytest.fixture
    def light(self, monkeypatch):
        from lumendusk.apply import nightlight as nl
        state = {"on": False, "temperature": None}

        def fake_set(on, temperature=4000):
            state["on"] = on
            state["temperature"] = temperature

        monkeypatch.setattr(nl, "set_nightlight", fake_set)
        monkeypatch.setattr(nl, "nightlight_on", lambda: state["on"])
        # cli imports these from the package, so rebind there too.
        import lumendusk.apply as apply_pkg
        monkeypatch.setattr(apply_pkg, "set_nightlight", fake_set)
        monkeypatch.setattr(apply_pkg, "nightlight_on", lambda: state["on"])
        return state

    def test_on_and_off(self, light, capsys):
        assert main(["nightlight", "on"]) == 0
        assert light["on"] is True
        assert main(["nightlight", "off"]) == 0
        assert light["on"] is False
        capsys.readouterr()

    def test_on_uses_the_configured_colour(self, light, capsys):
        config_mod.save(Config(nightlight_temperature=2700))
        main(["nightlight", "on"])
        assert light["temperature"] == 2700, "should use the settings-panel value"
        capsys.readouterr()

    def test_toggle_flips_the_live_state(self, light, capsys):
        main(["nightlight", "toggle"])
        assert light["on"] is True
        main(["nightlight", "toggle"])
        assert light["on"] is False
        capsys.readouterr()

    def test_status_is_a_bare_word_the_applet_can_parse(self, light, capsys):
        assert main(["nightlight", "status"]) == 0
        assert capsys.readouterr().out.strip() == "off"
        light["on"] = True
        main(["nightlight", "status"])
        assert capsys.readouterr().out.strip() == "on"

    def test_works_regardless_of_the_automation_setting(self, light, capsys):
        """nightlight_enabled governs the schedule, not this switch."""
        config_mod.save(Config(control="manual", nightlight_enabled=False))
        assert main(["nightlight", "on"]) == 0
        assert light["on"] is True
        capsys.readouterr()


class TestDaemonHandoff:
    """The seam between `lumendusk manual` and the daemon's next tick.

    Both sides were tested on their own and both were correct on their own,
    which is exactly how the bug below survived: it only existed in the gap
    between them.
    """

    @pytest.fixture
    def ticking(self, monkeypatch):
        """Run the daemon for a fixed number of ticks instead of forever.

        The loop only yields control inside ``time.sleep``, so that is where a
        test gets to act between ticks — and raising KeyboardInterrupt there is
        how the daemon is designed to stop.
        """
        def run(interval, on_tick):
            count = {"n": 0}

            def fake_sleep(_seconds):
                count["n"] += 1
                if not on_tick(count["n"]):
                    raise KeyboardInterrupt

            monkeypatch.setattr(daemon_mod.time, "sleep", fake_sleep)
            return daemon_mod.run_daemon(interval=interval)

        return run

    def test_a_tick_after_switching_to_manual_touches_nothing(self, applied, ticking):
        """Regression: the daemon repeated the CLI's one-time night light drop.

        `lumendusk manual` turns the night light off as it switches. The daemon
        then noticed the switch on its own next tick and turned it off *again* —
        up to a minute later, by which time the user may well have turned it
        back on from the panel menu. Observed on a real desktop: warmth switched
        on at 01:18:44 was gone at 01:18:45.
        """
        config_mod.save(Config(control="auto", nightlight_enabled=True))

        def on_tick(n):
            if n == 1:
                # What the CLI does, then what the user does a moment later.
                cfg = config_mod.load()
                cfg.control = "manual"
                config_mod.save(cfg)
                applied["theme"].clear()
                applied["nightlight"].clear()
                applied["brightness"].clear()
                return True
            return False  # stop; the tick under test has already run

        assert ticking(1, on_tick) == 0
        assert applied["nightlight"] == [], \
            "the daemon must not touch night light the user now owns"
        assert applied["theme"] == []
        assert applied["brightness"] == []

    def test_switching_back_to_auto_still_snaps(self, applied, ticking):
        """The other half: leaving manual must re-apply, or nothing ever would."""
        config_mod.save(Config(control="manual", nightlight_enabled=True))

        def on_tick(n):
            if n == 1:
                cfg = config_mod.load()
                cfg.control = "auto"
                config_mod.save(cfg)
                return True
            return False

        assert ticking(1, on_tick) == 0
        assert len(applied["theme"]) == 1, "should snap to the current phase"


class TestStatus:
    def test_reports_control_alongside_mode_and_phase(self, capsys):
        config_mod.save(Config(control="manual"))
        assert main(["status"]) == 0
        out = capsys.readouterr().out
        assert "control=manual" in out
        assert "mode=" in out and "phase=" in out

    def test_does_not_nag_about_a_missing_location_while_manual(self, capsys):
        """In manual the location is irrelevant — the warning would be noise."""
        config_mod.save(Config(control="manual", mode="sun"))
        main(["status"])
        assert "no location set" not in capsys.readouterr().out
