"""The applet settings panel has to agree with the engine's config.

Three files have to stay in step: settings-schema.json (what the panel shows),
SYNCED_KEYS in applet.js (what gets written back), and the Config dataclass
(what the engine reads). Nothing at runtime checks that, and a mismatch is
quiet — a renamed key just stops saving. So check it here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from lumendusk.config import Config

APPLET_DIR = Path(__file__).resolve().parent.parent / "applet" / "lumendusk@kasun"
SCHEMA_PATH = APPLET_DIR / "settings-schema.json"
APPLET_JS = APPLET_DIR / "applet.js"

# Schema entries that are presentation only — no value behind them.
NON_SETTING_TYPES = {"label", "button", "separator", "layout"}


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def synced_keys() -> list:
    """The SYNCED_KEYS array out of applet.js."""
    text = APPLET_JS.read_text(encoding="utf-8")
    match = re.search(r"const SYNCED_KEYS = \[(.*?)\];", text, re.S)
    assert match, "SYNCED_KEYS not found in applet.js"
    return re.findall(r'"([^"]+)"', match.group(1))


def _value_keys(schema: dict) -> dict:
    return {
        name: node for name, node in schema.items()
        if name != "layout" and isinstance(node, dict)
        and node.get("type") not in NON_SETTING_TYPES
    }


class TestSchemaStructure:
    def test_every_page_and_section_resolves(self, schema):
        layout = schema["layout"]
        for page in layout["pages"]:
            assert page in layout, f"page '{page}' is not defined"
            for section in layout[page]["sections"]:
                assert section in layout, f"section '{section}' is not defined"

    def test_every_referenced_key_is_defined(self, schema):
        layout = schema["layout"]
        for name, node in layout.items():
            if not isinstance(node, dict) or node.get("type") != "section":
                continue
            for key in node.get("keys", []):
                assert key in schema, f"section '{name}' references unknown '{key}'"

    def test_every_defined_key_is_shown_somewhere(self, schema):
        """An orphaned key is invisible in the panel — almost always a mistake."""
        shown = set()
        for node in schema["layout"].values():
            if isinstance(node, dict) and node.get("type") == "section":
                shown.update(node.get("keys", []))
        orphans = set(schema) - shown - {"layout"}
        assert not orphans, f"defined but never shown: {sorted(orphans)}"

    def test_button_callbacks_exist_in_applet_js(self, schema):
        js = APPLET_JS.read_text(encoding="utf-8")
        for name, node in schema.items():
            if isinstance(node, dict) and node.get("type") == "button":
                callback = node["callback"]
                assert re.search(rf"\b{callback}\s*:\s*function", js), \
                    f"button '{name}' calls {callback}(), which applet.js lacks"


class TestSyncedKeys:
    def test_all_synced_keys_exist_in_the_schema(self, schema, synced_keys):
        values = _value_keys(schema)
        for key in synced_keys:
            assert key in values, f"applet.js syncs '{key}', not in the schema"

    def test_all_synced_keys_exist_on_config(self, synced_keys):
        for key in synced_keys:
            assert hasattr(Config(), key), \
                f"applet.js syncs '{key}', which the engine's Config has no field for"

    def test_every_schema_setting_is_synced(self, schema, synced_keys):
        """A widget that isn't synced silently does nothing when you change it."""
        for key in _value_keys(schema):
            assert key in synced_keys, \
                f"schema exposes '{key}' but applet.js never writes it back"


class TestDefaultsAgree:
    def test_schema_defaults_match_the_engine_defaults(self, schema, synced_keys):
        """Otherwise the panel opens showing something the engine isn't doing."""
        defaults = Config()
        for key in synced_keys:
            assert schema[key]["default"] == getattr(defaults, key), (
                f"'{key}': schema default {schema[key]['default']!r} != "
                f"config default {getattr(defaults, key)!r}"
            )

    def test_numeric_ranges_contain_their_default(self, schema, synced_keys):
        for key in synced_keys:
            node = schema[key]
            if "min" not in node:
                continue
            assert node["min"] <= node["default"] <= node["max"], \
                f"'{key}' default sits outside its own min/max"

    def test_percentages_and_coordinates_use_sane_bounds(self, schema):
        assert (schema["latitude"]["min"], schema["latitude"]["max"]) == (-90, 90)
        assert (schema["longitude"]["min"], schema["longitude"]["max"]) == (-180, 180)
        for key in ("brightness_day", "brightness_night"):
            assert (schema[key]["min"], schema[key]["max"]) == (0, 100)

    def test_mode_options_match_what_the_engine_accepts(self, schema):
        assert set(schema["mode"]["options"].values()) == {"sun", "fixed"}
