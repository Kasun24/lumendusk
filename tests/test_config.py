"""Config loading/saving. The daemon reloads this every tick, so `load()`
must never raise, whatever the user typed into the file."""

from __future__ import annotations

import pytest

from lumendusk import config as config_mod
from lumendusk.config import Config


def write_config(text: str) -> None:
    path = config_mod.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestDefaults:
    def test_default_mode_is_fixed(self):
        """Sun mode can't work without a location, so it can't be the default."""
        assert Config().mode == "fixed"

    def test_zero_location_counts_as_unset(self):
        assert Config().location_is_set() is False
        assert Config(latitude=51.5, longitude=-0.13).location_is_set() is True
        assert Config(latitude=0.0, longitude=-0.13).location_is_set() is True

    def test_first_load_creates_the_file(self):
        assert not config_mod.config_path().exists()
        cfg = config_mod.load()
        assert config_mod.config_path().exists()
        assert cfg == Config()


class TestRoundTrip:
    def test_saved_config_loads_back_identical(self):
        original = Config(
            control="manual", mode="sun",
            latitude=51.5074, longitude=-0.1278,
            dark_start="20:30", light_start="06:15",
            theme_accent="aqua",
            nightlight_enabled=False, nightlight_temperature=3500,
            brightness_enabled=True, brightness_day=90, brightness_night=20,
            brightness_fade_minutes=5,
        )
        config_mod.save(original)
        loaded = config_mod.load()
        # theme_light/theme_dark are legacy read-only fields we no longer write.
        assert loaded.mode == original.mode
        assert loaded.control == "manual"
        assert (loaded.latitude, loaded.longitude) == (51.5074, -0.1278)
        assert loaded.dark_start == "20:30"
        assert loaded.theme_accent == "aqua"
        assert loaded.nightlight_enabled is False
        assert loaded.nightlight_temperature == 3500
        assert loaded.brightness_day == 90
        assert loaded.brightness_fade_minutes == 5

    def test_save_is_atomic_and_leaves_no_temp_files(self):
        config_mod.save(Config())
        leftovers = list(config_mod.config_dir().glob(".config.*"))
        assert leftovers == []


class TestControl:
    """`control` replaced the old enabled/paused pair, so old files must migrate."""

    def test_defaults_to_automatic(self):
        assert Config().control == "auto"
        assert Config().is_auto() is True

    @pytest.mark.parametrize("legacy,expected", [
        ("paused = true\n", "manual"),
        ("enabled = false\n", "manual"),
        ("paused = true\nenabled = false\n", "manual"),
        ("paused = false\nenabled = true\n", "auto"),
        ("", "auto"),
    ])
    def test_old_configs_migrate(self, legacy, expected):
        """Someone who had paused automation must not have it resume on upgrade."""
        write_config('mode = "fixed"\n' + legacy)
        assert config_mod.load().control == expected

    def test_control_wins_over_leftover_legacy_keys(self):
        """Once we've written `control`, stale booleans must not override it."""
        write_config('control = "auto"\npaused = true\nenabled = false\n')
        assert config_mod.load().control == "auto"

    def test_a_nonsense_control_falls_back_to_the_default(self):
        write_config('control = "sideways"\npaused = true\n')
        assert config_mod.load().control == "auto"

    def test_the_legacy_keys_are_no_longer_written(self):
        """The migration is one-way; leaving them behind invites disagreement.

        Only the root table matters — the legacy keys were top-level, whereas
        ``[nightlight] enabled`` and ``[brightness] enabled`` are current
        settings that happen to share the name.
        """
        config_mod.save(Config(control="manual"))
        text = config_mod.config_path().read_text(encoding="utf-8")
        root = text.split("\n[", 1)[0]
        assert 'control = "manual"' in root
        assert "paused" not in root
        assert "enabled" not in root

    def test_only_auto_counts_as_automatic(self):
        """A typo should leave the desktop alone, not start driving it."""
        assert Config(control="manual").is_auto() is False
        assert Config(control="").is_auto() is False


class TestBrokenConfig:
    def test_malformed_toml_falls_back_to_defaults(self):
        write_config('mode = "fixed"\ncontrol = auto\n')   # unquoted: not TOML
        assert config_mod.load() == Config()

    def test_malformed_toml_keeps_the_last_good_values(self):
        config_mod.save(Config(mode="sun", latitude=51.5, longitude=-0.13))
        good = config_mod.load()
        assert good.latitude == 51.5

        write_config("this is not toml at all {{{")
        recovered = config_mod.load()
        assert recovered.latitude == 51.5, "should keep serving the last good config"

    def test_recovers_when_the_file_is_fixed_again(self):
        write_config("broken {{{")
        assert config_mod.load() == Config()
        config_mod.save(Config(theme_accent="teal"))
        assert config_mod.load().theme_accent == "teal"

    def test_wrong_types_fall_back_per_field(self):
        write_config(
            'mode = "fixed"\n'
            "control = 7\n"                 # not a string
            "[location]\n"
            'latitude = "north"\n'          # not a number
            "longitude = -0.13\n"
            "[nightlight]\n"
            'temperature = "warm"\n'
        )
        cfg = config_mod.load()
        assert cfg.control == "auto"         # default
        assert cfg.latitude == 0.0           # default
        assert cfg.longitude == -0.13        # the valid one survives
        assert cfg.nightlight_temperature == 4000

    def test_bool_is_not_accepted_as_a_number(self):
        write_config("[location]\nlatitude = true\nlongitude = 2.0\n")
        cfg = config_mod.load()
        assert cfg.latitude == 0.0

    def test_wrong_shape_tables_are_ignored(self):
        write_config('location = "somewhere"\n')
        assert config_mod.load().latitude == 0.0

    def test_empty_file_gives_defaults(self):
        write_config("")
        assert config_mod.load() == Config()
