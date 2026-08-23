"""Rules the Cinnamon Spices repository enforces on what we ship.

``packaging/build-spices.sh`` checks the assembled tree against all of them,
but that script needs pip and a network, so it only runs in CI. These are the
subset that can be checked against the files in git — which is also the subset
someone is most likely to break by hand, months after the last release, by
adding a field to ``metadata.json`` that looks entirely reasonable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
UUID = "lumendusk@kasun"
APPLET = ROOT / "applet" / UUID


@pytest.fixture
def metadata() -> dict:
    return json.loads((APPLET / "metadata.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("field", ["icon", "dangerous", "last-edited"])
def test_metadata_omits_the_fields_spices_forbids(metadata, field):
    # `icon` is the tempting one: it works locally, and the applet really does
    # show that icon — but applet.js sets it, and the Spices listing uses
    # icon.png. `last-edited` is written by the Spices infrastructure at
    # install time, so shipping one means shipping a lie.
    assert field not in metadata


def test_metadata_uuid_matches_the_directory():
    assert json.loads((APPLET / "metadata.json").read_text(encoding="utf-8"))["uuid"] \
        == UUID


@pytest.mark.parametrize("field", ["uuid", "name", "description"])
def test_metadata_has_the_mandatory_fields(metadata, field):
    assert metadata.get(field)


def test_metadata_is_ascii(metadata):
    # The prose everywhere else in this project uses real en dashes and
    # ellipses on purpose. Not here: the validator rejects them, and this is
    # the one file where that matters.
    for field, value in metadata.items():
        texts = [value] if isinstance(value, str) else value if isinstance(value, list) else []
        for text in texts:
            assert not isinstance(text, str) or text.isascii(), \
                f"{field} contains non-ASCII text: {text!r}"


def test_translations_are_sources_in_one_place():
    po = APPLET / "po"
    assert not list(APPLET.rglob("*.mo")), "compiled translations must not be shipped"
    assert len(list(po.glob("*.pot"))) == 1, "exactly one template belongs in po/"
    stray = [p for p in APPLET.rglob("*.po*") if p.parent != po]
    assert not stray, f"translations belong in po/, found: {stray}"


def test_the_spice_page_files_exist():
    # These three are the applet's page on the Spices site. They live in
    # packaging/spices/ rather than being generated, because the page is aimed
    # at someone deciding whether to install this, not at someone reading the
    # repository.
    assert (ROOT / "packaging/spices/info.json").is_file()
    assert (ROOT / "packaging/spices/README.md").is_file()
    assert (ROOT / "packaging/screenshot.png").is_file()


@pytest.mark.parametrize("variable", ["XDG_CONFIG_HOME", "XDG_STATE_HOME",
                                      "XDG_CACHE_HOME", "XDG_DATA_HOME"])
def test_uninstall_knows_about_every_directory_the_engine_uses(variable):
    """Uninstalling has to clean up everywhere the engine writes.

    A text check, which is weak — but the bug it guards against is a directory
    quietly added to the engine and never added here, and that one is invisible
    until someone uninstalls and finds their disk still has our files on it.
    The cache is how it happened once already.
    """
    assert variable in (ROOT / "uninstall.sh").read_text(encoding="utf-8")


def test_the_spice_author_is_a_github_username():
    # The site links it to a GitHub account, so a display name with a space in
    # it fails validation — an easy thing to "fix" wrongly by copying the
    # author out of metadata.json, where the full name is correct.
    author = json.loads(
        (ROOT / "packaging/spices/info.json").read_text(encoding="utf-8")
    )["author"]
    assert author
    assert author == author.strip()
    assert " " not in author


def test_the_build_script_strips_compiled_files_after_running_the_engine():
    """The bundle must ship no bytecode, and the build must keep it that way.

    Spices forbids binaries outright. `build-applet.sh` cleans `__pycache__`
    right after copying the engine in — but its last act is a smoke test that
    *runs* that engine, which wrote the bytecode straight back, after the
    cleanup and before the zip. Compiled `.pyc` files shipped in every bundle
    until 0.3.0, and were 30% of its size.

    This checks the two things that keep it fixed: the smoke test disables
    bytecode writing, and the script fails outright if anything compiled
    survives. Checking the script rather than the built tree is deliberate —
    `dist/` is not in git, so there is nothing to inspect until CI builds it,
    and by then the bundle is already wrong.
    """
    script = (ROOT / "packaging/build-applet.sh").read_text(encoding="utf-8")

    smoke = [line for line in script.splitlines()
             if "run.py" in line and "python3" in line]
    assert smoke, "no smoke-test invocation found in build-applet.sh"
    for line in smoke:
        assert "python3 -B" in line, (
            f"the smoke test must not write bytecode into the bundle: {line.strip()}"
        )

    assert "-name \"*.pyc\"" in script, "the build must refuse to ship .pyc files"
