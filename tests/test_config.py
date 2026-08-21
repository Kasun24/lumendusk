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
        )
        config_mod.save(original)
        loaded = config_mod.load()
        # Every field, not a hand-picked few: the round trip is only worth
        # testing if nothing can quietly drop out of it.
        assert loaded == original

    def test_a_config_from_an_older_version_still_loads(self):
        """Settings that were removed must not turn a config file into an error.

        `theme.light`, `theme.dark` and `brightness.fade_minutes` were read
        once and did nothing; they are gone now. Every file written before that
        still has them, and the daemon reads the file every tick — so the
        removal has to be a non-event, with the settings that *do* mean
        something around them coming through untouched.
        """
        write_config(
            'control = "auto"\n'
            'mode = "fixed"\n'
            "\n"
            "[fixed]\n"
            'dark_start = "21:00"\n'
            "\n"
            "[theme]\n"
            'day = "dark"\n'
            'night = "dark"\n'
            'light = "Mint-Y"\n'          # removed
            'dark = "Mint-Y-Dark"\n'      # removed
            "\n"
            "[brightness]\n"
            "enabled = true\n"
            "day = 90\n"
            "fade_minutes = 5\n"          # removed
        )
        cfg = config_mod.load()
        assert cfg.dark_start == "21:00"
        assert cfg.theme_day == "dark"
        assert cfg.brightness_enabled is True
        assert cfg.brightness_day == 90
        # And they don't come back as attributes by some other route.
        assert not hasattr(cfg, "brightness_fade_minutes")
        assert not hasattr(cfg, "theme_light")

    def test_rewriting_an_old_config_drops_the_removed_keys(self):
        """The file catches up the next time anything is saved."""
        write_config('[brightness]\nfade_minutes = 5\n[theme]\nlight = "Mint-Y"\n')
        config_mod.save(config_mod.load())
        text = config_mod.config_path().read_text(encoding="utf-8")
        assert "fade_minutes" not in text
        assert "\nlight =" not in text

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
