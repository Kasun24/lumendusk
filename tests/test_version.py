"""The version is written in three files, and they must agree.

Bumping a release means editing pyproject.toml (the Python package),
metadata.json (what Cinnamon and the Spices site show), and __init__.py (what
`lumendusk --version` prints). Nothing links them, and the third is easy to
miss — a user reporting a bug against "0.0.1" when the applet says "0.1.0"
wastes everyone's time.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import lumendusk

ROOT = Path(__file__).resolve().parent.parent


def test_all_three_version_strings_agree():
    pyproject = re.search(
        r'^version\s*=\s*"([^"]+)"',
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert pyproject, "no version in pyproject.toml"

    metadata = json.loads(
        (ROOT / "applet/lumendusk@kasun/metadata.json").read_text(encoding="utf-8")
    )

    assert lumendusk.__version__ == pyproject.group(1) == metadata["version"], (
        f"version drift: __init__.py={lumendusk.__version__}, "
        f"pyproject.toml={pyproject.group(1)}, metadata.json={metadata['version']}"
    )
