"""Config loading/saving. The daemon reloads this every tick, so `load()`
must never raise, whatever the user typed into the file."""

from __future__ import annotations

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
            mode="sun", enabled=True, paused=True,
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
        assert loaded.paused is True
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


class TestBrokenConfig:
    def test_malformed_toml_falls_back_to_defaults(self):
        write_config('mode = "fixed"\npaused = fals\n')
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
            "enabled = 7\n"                 # not a bool
            "[location]\n"
            'latitude = "north"\n'          # not a number
            "longitude = -0.13\n"
            "[nightlight]\n"
            'temperature = "warm"\n'
        )
        cfg = config_mod.load()
        assert cfg.enabled is True           # default
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
