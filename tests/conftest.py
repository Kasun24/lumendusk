"""Shared fixtures.

Every test runs against a throwaway XDG config/state directory so nothing
touches the developer's real ``~/.config/lumendusk/config.toml``.
"""

from __future__ import annotations

import pytest

from lumendusk import config as config_mod
from lumendusk import schedule as schedule_mod


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
