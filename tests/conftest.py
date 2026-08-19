"""Shared fixtures.

Every test runs against a throwaway XDG config/state directory so nothing
touches the developer's real ``~/.config/lumendusk/config.toml``.
"""

from __future__ import annotations

import pytest

from lumendusk import config as config_mod
from lumendusk import daemon as daemon_mod
from lumendusk import schedule as schedule_mod
from lumendusk.apply.theme import appearance_for


@pytest.fixture(autouse=True)
def isolated_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    # These modules cache state across calls on purpose (last-good config,
    # warn-once flags); reset it so tests don't leak into each other.
    monkeypatch.setattr(config_mod, "_last_good", None, raising=False)
    monkeypatch.setattr(config_mod, "_warned_bad_config", False, raising=False)
    for flag in ("_warned_no_astral", "_warned_no_location", "_warned_bad_times",
                 "_warned_astral_failed", "_warned_bad_mode"):
        monkeypatch.setattr(schedule_mod, flag, False, raising=False)
    return tmp_path


@pytest.fixture
def applies(monkeypatch):
    """Record what gets applied to the desktop, instead of applying it.

    One dict of three lists, so a test can assert not only that the right thing
    moved but that nothing *else* did — which is most of what the transition-only
    rule is about.
    """
    calls: dict[str, list] = {"theme": [], "nightlight": [], "brightness": []}
    monkeypatch.setattr(daemon_mod, "set_theme",
                        lambda dark, cfg, force=False:
                        calls["theme"].append(appearance_for(dark, cfg)))
    monkeypatch.setattr(daemon_mod, "set_nightlight",
                        lambda on, temp=None, force=False:
                        calls["nightlight"].append((on, temp)))
    monkeypatch.setattr(daemon_mod.brightness_mod, "set_brightness",
                        lambda level, target: calls["brightness"].append(level))
    return calls


@pytest.fixture
def run_ticks(monkeypatch, applies):
    """Drive :func:`run_daemon` for a few ticks with no real waiting.

    ``on_tick(n)`` runs in place of each sleep and returns False to stop, which
    is where a test edits the config to stand in for the user changing a setting
    mid-period.
    """
    def run(on_tick, interval: int = 1):
        count = {"n": 0}

        def fake_sleep(_seconds):
            count["n"] += 1
            if not on_tick(count["n"]):
                raise KeyboardInterrupt

        monkeypatch.setattr(daemon_mod.time, "sleep", fake_sleep)
        assert daemon_mod.run_daemon(interval=interval) == 0
        return applies

    return run
