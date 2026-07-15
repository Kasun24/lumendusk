"""Load and save Lumendusk configuration.

Config lives at ``~/.config/lumendusk/config.toml``. Reading uses the stdlib
``tomllib`` (Python 3.11+). Writing uses a tiny purpose-built serializer so we
don't need a third-party TOML writer — our schema is small and known.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, asdict
from pathlib import Path


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "lumendusk"


def config_path() -> Path:
    return config_dir() / "config.toml"


@dataclass
class Config:
    """All user-tunable settings, flattened for easy access.

    Nested TOML tables (``[location]``, ``[theme]``, ``[brightness]`` …) are
    mapped to/from these flat fields by :func:`load` and :func:`save`.
    """

    # day/night decision
    mode: str = "sun"                # "sun" (astral) or "fixed"
    enabled: bool = True             # master on/off
    latitude: float = 0.0
    longitude: float = 0.0
    dark_start: str = "19:00"        # fixed mode: when night begins
    light_start: str = "07:00"       # fixed mode: when day begins

    # theme
    theme_light: str = "Mint-Y"
    theme_dark: str = "Mint-Y-Dark"

    # night light
    nightlight_enabled: bool = True
    nightlight_temperature: int = 4000

    # brightness (feature track B1–B3)
    brightness_enabled: bool = False
    brightness_day: int = 80
    brightness_night: int = 35
    brightness_fade_minutes: int = 0


def _from_toml(data: dict) -> Config:
    loc = data.get("location", {})
    fixed = data.get("fixed", {})
    theme = data.get("theme", {})
    night = data.get("nightlight", {})
    bright = data.get("brightness", {})
    d = Config()
    return Config(
        mode=data.get("mode", d.mode),
        enabled=data.get("enabled", d.enabled),
        latitude=loc.get("latitude", d.latitude),
        longitude=loc.get("longitude", d.longitude),
        dark_start=fixed.get("dark_start", d.dark_start),
        light_start=fixed.get("light_start", d.light_start),
        theme_light=theme.get("light", d.theme_light),
        theme_dark=theme.get("dark", d.theme_dark),
        nightlight_enabled=night.get("enabled", d.nightlight_enabled),
        nightlight_temperature=night.get("temperature", d.nightlight_temperature),
        brightness_enabled=bright.get("enabled", d.brightness_enabled),
        brightness_day=bright.get("day", d.brightness_day),
        brightness_night=bright.get("night", d.brightness_night),
        brightness_fade_minutes=bright.get("fade_minutes", d.brightness_fade_minutes),
    )


def _to_toml(c: Config) -> str:
    def s(v: str) -> str:
        return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'

    def b(v: bool) -> str:
        return "true" if v else "false"

    return (
        "# Lumendusk configuration\n"
        "# mode = \"sun\" uses your latitude/longitude (offline, via astral).\n"
        "# mode = \"fixed\" uses the [fixed] times below.\n\n"
        f"mode = {s(c.mode)}\n"
        f"enabled = {b(c.enabled)}\n\n"
        "[location]\n"
        f"latitude = {c.latitude}\n"
        f"longitude = {c.longitude}\n\n"
        "[fixed]\n"
        f"dark_start = {s(c.dark_start)}\n"
        f"light_start = {s(c.light_start)}\n\n"
        "[theme]\n"
        f"light = {s(c.theme_light)}\n"
        f"dark = {s(c.theme_dark)}\n\n"
        "[nightlight]\n"
        f"enabled = {b(c.nightlight_enabled)}\n"
        f"temperature = {c.nightlight_temperature}\n\n"
        "[brightness]\n"
        f"enabled = {b(c.brightness_enabled)}\n"
        f"day = {c.brightness_day}\n"
        f"night = {c.brightness_night}\n"
        f"fade_minutes = {c.brightness_fade_minutes}\n"
    )


def load() -> Config:
    """Load config, returning defaults (and creating the file) if absent."""
    path = config_path()
    if not path.exists():
        cfg = Config()
        save(cfg)
        return cfg
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return _from_toml(data)


def save(config: Config) -> None:
    """Write config to disk, creating the config directory if needed."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_toml(config), encoding="utf-8")


# Silence "asdict imported but unused" for tooling; it's part of the public
# surface people reach for when serializing Config elsewhere.
__all__ = ["Config", "config_dir", "config_path", "load", "save", "asdict"]
