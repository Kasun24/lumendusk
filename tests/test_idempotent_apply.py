"""Applying a phase must not rewrite settings that are already correct.

Most calls into the apply backends are reconciliation, not change: the daemon
snaps to the current phase on startup, on resume, and when you switch back to
automatic, and nearly always finds the desktop already in that phase. Writing
the keys anyway is not harmless — dconf notifies on every write, identical
value or not, so Cinnamon reloads its theme and the screen flickers for
nothing.

The other half matters just as much: a key that has genuinely drifted must
still be corrected, and the explicit "apply now" must still force everything.
Skip too eagerly and the repair button stops repairing.
"""

from __future__ import annotations

import pytest

from lumendusk.apply import appearance, nightlight

_NL_SCHEMA = "org.cinnamon.settings-daemon.plugins.color"


@pytest.fixture
def gsettings(monkeypatch):
    """A fake dconf: a dict of values, plus a record of what was written.

    Both modules wrap gsettings in their own tiny get/set pair, so stubbing
    those four functions replaces the subprocess layer entirely — the logic
    under test is which writes get issued, and that is exactly what ``writes``
    captures.
    """
    store: dict[tuple[str, str], str] = {}
    writes: list[tuple[str, str, str]] = []

    def get(schema, key):
        return store.get((schema, key))

    def write(schema, key, value):
        writes.append((schema, key, value))
        store[(schema, key)] = value
        return True

    monkeypatch.setattr(appearance, "_get", get)
    monkeypatch.setattr(appearance, "_set", write)
    monkeypatch.setattr(nightlight, "_gsettings_get", get)
    monkeypatch.setattr(nightlight, "_gsettings_set", write)
    return store, writes


VARIANT = appearance.Variant(
    family="Mint-Y", mode="dark", accent="orange",
    themes="Mint-Y-Dark-Orange", cinnamon="Mint-Y-Dark-Orange",
    icons="Mint-Y-Yaru", cursor="Adwaita", color="#ff7139",
)


def _seed(store, variant):
    """Put the fake dconf in the state ``variant`` would produce."""
    for schema, key, value in appearance._targets(variant):
        store[(schema, key)] = value


class TestAppearance:
    def test_already_correct_writes_nothing(self, gsettings):
        store, writes = gsettings
        _seed(store, VARIANT)
        assert appearance.apply_variant(VARIANT) is True
        assert writes == [], "a no-op apply must not touch dconf at all"

    def test_a_drifted_key_is_still_corrected(self, gsettings):
        """Per-key, not all-or-nothing: fix the one, leave the eleven."""
        store, writes = gsettings
        _seed(store, VARIANT)
        store[("org.cinnamon.theme", "name")] = "Mint-Y-Aqua"

        assert appearance.apply_variant(VARIANT) is True
        assert writes == [("org.cinnamon.theme", "name", "Mint-Y-Dark-Orange")]

    def test_a_real_switch_writes_everything(self, gsettings):
        store, writes = gsettings
        light = appearance.Variant(
            family="Mint-Y", mode="light", accent="orange",
            themes="Mint-Y-Orange", cinnamon="Mint-Y-Orange",
            icons="Mint-Y-Yaru", cursor="Adwaita", color="#ff7139")
        _seed(store, light)

        appearance.apply_variant(VARIANT)
        written = {(s, k) for s, k, _ in writes}
        # Icons, cursor and accent match across the two variants, so only the
        # keys that actually differ should move.
        assert ("org.cinnamon.theme", "name") in written
        assert ("org.gnome.desktop.interface", "color-scheme") in written
        assert ("org.cinnamon.desktop.interface", "cursor-theme") not in written

    def test_force_rewrites_correct_keys(self, gsettings):
        store, writes = gsettings
        _seed(store, VARIANT)
        assert appearance.apply_variant(VARIANT, force=True) is True
        assert len(writes) == len(appearance._targets(VARIANT))

    def test_an_unreadable_key_is_written(self, gsettings):
        """Uncertainty must fall through to writing, never to skipping."""
        store, writes = gsettings
        _seed(store, VARIANT)
        del store[("org.cinnamon.theme", "name")]     # reads as None
        appearance.apply_variant(VARIANT)
        assert ("org.cinnamon.theme", "name", "Mint-Y-Dark-Orange") in writes


class TestNightlight:
    def test_already_off_writes_nothing(self, gsettings):
        store, writes = gsettings
        store[(_NL_SCHEMA, "night-light-enabled")] = "false"
        nightlight.set_nightlight(False)
        assert writes == []

    def test_already_on_at_the_same_temperature_writes_nothing(self, gsettings):
        store, writes = gsettings
        store[(_NL_SCHEMA, "night-light-enabled")] = "true"
        store[(_NL_SCHEMA, "night-light-temperature")] = "uint32 4000"
        store[(_NL_SCHEMA, "night-light-schedule-mode")] = "always"
        nightlight.set_nightlight(True, 4000)
        assert writes == []

    def test_gsettings_prints_ints_typed(self, gsettings):
        """`gsettings get` returns 'uint32 4000', not '4000'.

        Comparing the raw string would never match, so every apply would look
        like a change — the exact bug this whole path exists to avoid.
        """
        store, _ = gsettings
        store[(_NL_SCHEMA, "night-light-temperature")] = "uint32 4000"
        assert nightlight._gsettings_int(
            _NL_SCHEMA, "night-light-temperature") == 4000

    def test_a_temperature_change_is_applied(self, gsettings):
        store, writes = gsettings
        store[(_NL_SCHEMA, "night-light-enabled")] = "true"
        store[(_NL_SCHEMA, "night-light-temperature")] = "uint32 4000"
        store[(_NL_SCHEMA, "night-light-schedule-mode")] = "always"
        nightlight.set_nightlight(True, 3200)
        assert (_NL_SCHEMA, "night-light-temperature", "3200") in writes

    def test_cinnamons_own_schedule_is_taken_back(self, gsettings):
        """schedule-mode 'auto' means Cinnamon is running its own sunset.

        That disagrees with our times and leaves the screen warm in daylight,
        so "already on" must not be judged by the enabled flag alone.
        """
        store, writes = gsettings
        store[(_NL_SCHEMA, "night-light-enabled")] = "true"
        store[(_NL_SCHEMA, "night-light-temperature")] = "uint32 4000"
        store[(_NL_SCHEMA, "night-light-schedule-mode")] = "auto"
        nightlight.set_nightlight(True, 4000)
        assert (_NL_SCHEMA, "night-light-schedule-mode", "always") in writes

    def test_force_rewrites(self, gsettings):
        store, writes = gsettings
        store[(_NL_SCHEMA, "night-light-enabled")] = "false"
        nightlight.set_nightlight(False, force=True)
        assert writes == [(_NL_SCHEMA, "night-light-enabled", "false")]
