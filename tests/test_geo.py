"""Timezone → approximate coordinates, read from the system's zone table."""

from __future__ import annotations

import pytest

from lumendusk import geo

ZONE_TAB = (
    "# comment line\tignored\n"
    "LK\t+0656+07951\tAsia/Colombo\n"
    "US\t+404251-0740023\tAmerica/New_York\tEastern (most areas)\n"
    "AU\t-3352+15113\tAustralia/Sydney\n"
    "GB\t+513030-0000731\tEurope/London\n"
    "\n"
)


class TestIso6709:
    @pytest.mark.parametrize("text,lat,lon", [
        ("+0656+07951", 6.9333, 79.8500),           # degrees + minutes
        ("+404251-0740023", 40.7142, -74.0064),     # with seconds, west
        ("-3352+15113", -33.8667, 151.2167),        # southern hemisphere
        ("+0000+00000", 0.0, 0.0),
    ])
    def test_parses_coordinates(self, text, lat, lon):
        got = geo._parse_iso6709(text)
        assert got is not None
        assert got[0] == pytest.approx(lat, abs=0.001)
        assert got[1] == pytest.approx(lon, abs=0.001)

    @pytest.mark.parametrize("text", [
        "", "garbage", "+0656", "0656+07951",
        "+9956+07951",     # latitude past the pole
        "+0656+19951",     # longitude past the antimeridian
    ])
    def test_rejects_nonsense(self, text):
        assert geo._parse_iso6709(text) is None


class TestZoneTableLookup:
    @pytest.fixture(autouse=True)
    def fake_zoneinfo(self, tmp_path, monkeypatch):
        (tmp_path / "zone1970.tab").write_text(ZONE_TAB, encoding="utf-8")
        monkeypatch.setattr(geo, "_ZONEINFO_DIR", tmp_path)
        return tmp_path

    def test_finds_a_known_timezone(self):
        lat, lon = geo._zone_table_lookup("Asia/Colombo")
        assert (round(lat, 2), round(lon, 2)) == (6.93, 79.85)

    def test_ignores_trailing_comment_columns(self):
        lat, lon = geo._zone_table_lookup("America/New_York")
        assert lat == pytest.approx(40.71, abs=0.01)
        assert lon == pytest.approx(-74.01, abs=0.01)

    def test_unknown_timezone_gives_nothing(self):
        assert geo._zone_table_lookup("Mars/Olympus_Mons") is None

    def test_missing_zone_table_gives_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(geo, "_ZONEINFO_DIR", tmp_path / "nope")
        assert geo._zone_table_lookup("Asia/Colombo") is None


class TestSystemTimezone:
    def test_tz_environment_variable_wins(self, monkeypatch):
        monkeypatch.setenv("TZ", "Europe/London")
        assert geo.system_timezone() == "Europe/London"

    def test_bare_tz_value_is_ignored(self, monkeypatch, tmp_path):
        # TZ can hold POSIX forms like "UTC" or "IST-5:30" that aren't zone
        # names; those must not be looked up as if they were.
        monkeypatch.setenv("TZ", "IST-5:30")
        monkeypatch.setattr(geo, "_TIMEZONE_FILE", tmp_path / "missing")
        monkeypatch.setattr(geo, "_LOCALTIME_LINK", tmp_path / "missing-too")
        assert geo.system_timezone() is None

    def test_falls_back_to_etc_timezone(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TZ", raising=False)
        tz_file = tmp_path / "timezone"
        tz_file.write_text("Asia/Colombo\n", encoding="utf-8")
        monkeypatch.setattr(geo, "_TIMEZONE_FILE", tz_file)
        assert geo.system_timezone() == "Asia/Colombo"

    def test_falls_back_to_the_localtime_symlink(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TZ", raising=False)
        monkeypatch.setattr(geo, "_TIMEZONE_FILE", tmp_path / "missing")
        zoneinfo = tmp_path / "usr" / "share" / "zoneinfo" / "Europe"
        zoneinfo.mkdir(parents=True)
        (zoneinfo / "London").write_text("TZif", encoding="utf-8")
        link = tmp_path / "localtime"
        link.symlink_to(zoneinfo / "London")
        monkeypatch.setattr(geo, "_LOCALTIME_LINK", link)
        assert geo.system_timezone() == "Europe/London"


class TestDetectLocation:
    def test_returns_coordinates_for_a_known_timezone(self, tmp_path, monkeypatch):
        (tmp_path / "zone.tab").write_text(ZONE_TAB, encoding="utf-8")
        monkeypatch.setattr(geo, "_ZONEINFO_DIR", tmp_path)
        monkeypatch.setenv("TZ", "Australia/Sydney")
        found = geo.detect_location()
        assert found is not None
        assert found.timezone == "Australia/Sydney"
        assert found.latitude == pytest.approx(-33.87, abs=0.01)
        assert found.longitude == pytest.approx(151.22, abs=0.01)

    def test_gives_nothing_rather_than_a_guess(self, tmp_path, monkeypatch):
        """A wrong location is worse than none — sun mode would be confidently
        wrong instead of visibly unset."""
        (tmp_path / "zone.tab").write_text(ZONE_TAB, encoding="utf-8")
        monkeypatch.setattr(geo, "_ZONEINFO_DIR", tmp_path)
        monkeypatch.setenv("TZ", "Mars/Olympus_Mons")
        assert geo.detect_location() is None

    def test_result_is_usable_as_a_real_location(self, tmp_path, monkeypatch):
        """What we detect must not read as 'unset' to the rest of the app."""
        from lumendusk.config import Config
        (tmp_path / "zone.tab").write_text(ZONE_TAB, encoding="utf-8")
        monkeypatch.setattr(geo, "_ZONEINFO_DIR", tmp_path)
        monkeypatch.setenv("TZ", "Asia/Colombo")
        found = geo.detect_location()
        cfg = Config(latitude=found.latitude, longitude=found.longitude)
        assert cfg.location_is_set() is True
