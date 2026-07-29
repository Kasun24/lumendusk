"""`config show` / `config set` — the applet settings panel's write path.

The panel has no TOML parser: it reads these key=value lines and writes back one
key at a time. So the format is a contract, and bad values have to be refused
here rather than landing in config.toml.
"""

from __future__ import annotations

import pytest

from lumendusk import config as config_mod
from lumendusk.cli import main


def show(capsys) -> dict:
    assert main(["config", "show"]) == 0
    out = capsys.readouterr().out
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


class TestShow:
    def test_prints_every_config_field(self, capsys):
        import dataclasses
        values = show(capsys)
        expected = {f.name for f in dataclasses.fields(config_mod.Config)}
        assert set(values) == expected

    def test_booleans_are_lowercase_words(self, capsys):
        """The applet parses these literally; Python's "True" wouldn't match."""
        values = show(capsys)
        assert values["enabled"] == "true"
        assert values["paused"] == "false"

    def test_reflects_what_was_saved(self, capsys):
        config_mod.save(config_mod.Config(mode="sun", latitude=6.9333,
                                          longitude=79.85))
        values = show(capsys)
        assert values["mode"] == "sun"
        assert float(values["latitude"]) == pytest.approx(6.9333)


class TestSet:
    @pytest.mark.parametrize("key,value,expected", [
        ("mode", "sun", "sun"),
        ("dark_start", "18:30", "18:30"),
        ("latitude", "6.9333", 6.9333),
        ("brightness_day", "65", 65),
        ("nightlight_temperature", "3200", 3200),
    ])
    def test_writes_the_value_through(self, key, value, expected, capsys):
        assert main(["config", "set", key, value]) == 0
        capsys.readouterr()
        assert getattr(config_mod.load(), key) == expected

    @pytest.mark.parametrize("value,expected", [
        ("true", True), ("false", False), ("on", True), ("off", False),
        ("1", True), ("0", False),
    ])
    def test_accepts_the_boolean_spellings_the_applet_might_send(
            self, value, expected, capsys):
        assert main(["config", "set", "nightlight_enabled", value]) == 0
        capsys.readouterr()
        assert config_mod.load().nightlight_enabled is expected

    def test_tolerates_a_float_for_an_integer_field(self, capsys):
        """Cinnamon's scale widgets hand back 80.0, not 80."""
        assert main(["config", "set", "brightness_day", "80.0"]) == 0
        capsys.readouterr()
        assert config_mod.load().brightness_day == 80

    @pytest.mark.parametrize("key,value", [
        ("mode", "banana"),
        ("dark_start", "7pm"),
        ("light_start", "25:00"),
        ("latitude", "91"),
        ("longitude", "-181"),
        ("brightness_day", "150"),
        ("brightness_night", "-5"),
        ("nightlight_temperature", "50"),
        ("nightlight_enabled", "maybe"),
        ("brightness_fade_minutes", "-1"),
    ])
    def test_refuses_bad_values(self, key, value, capsys):
        before = getattr(config_mod.load(), key)
        assert main(["config", "set", key, value]) == 2
        assert getattr(config_mod.load(), key) == before, "config was modified anyway"

    def test_refuses_an_unknown_key(self, capsys):
        assert main(["config", "set", "colour_of_the_sky", "blue"]) == 2

    def test_rejection_explains_itself_on_stderr(self, capsys):
        main(["config", "set", "dark_start", "7pm"])
        err = capsys.readouterr().err
        assert "18:00" in err, "the error should show the expected format"


class TestLocation:
    def test_detect_sets_a_location_and_switches_to_sun(self, capsys, monkeypatch):
        from lumendusk import geo
        monkeypatch.setattr(
            geo, "detect_location",
            lambda: geo.DetectedLocation(6.9333, 79.85, "Asia/Colombo"))
        assert main(["location", "--detect"]) == 0
        cfg = config_mod.load()
        assert cfg.mode == "sun"
        assert cfg.location_is_set() is True
        assert "Asia/Colombo" in capsys.readouterr().out

    def test_detect_failure_is_reported_not_guessed(self, capsys, monkeypatch):
        from lumendusk import geo
        monkeypatch.setattr(geo, "detect_location", lambda: None)
        assert main(["location", "--detect"]) == 1
        assert config_mod.load().location_is_set() is False
        assert "by hand" in capsys.readouterr().err

    def test_bare_location_reports_without_changing_anything(self, capsys):
        before = config_mod.load()
        assert main(["location"]) == 0
        assert config_mod.load() == before
        assert "location:" in capsys.readouterr().out

    def test_one_coordinate_alone_is_refused(self, capsys):
        assert main(["location", "51.5"]) == 2
