"""What the night light *says* it did, versus what it did.

The rest of the suite stubs :func:`set_nightlight` out, because most tests care
about when it is called rather than what it does. These are the other half: the
backend ladder — Cinnamon's own keys, then gammastep, then xsct, then nothing —
and the report each rung produces. A wrong report here is expensive out of all
proportion to its size, because the log is the only place anyone looks when the
screen didn't change.
"""

from __future__ import annotations

import subprocess

import pytest

from lumendusk.apply import nightlight as nl


@pytest.fixture
def desktop(monkeypatch):
    """A fake machine: which tools exist, whether gsettings works, what it holds.

    ``ran`` collects every command actually executed, so a test can assert the
    ladder stopped where it should have.
    """
    state = {
        "tools": set(),          # which binaries exist on this imaginary PATH
        "gsettings_ok": False,   # do the Cinnamon schemas answer at all
        "keys": {},              # what `gsettings get` reports
        "fail": set(),           # binaries that run but exit non-zero
        "ran": [],
    }

    def which(name):
        return f"/usr/bin/{name}" if name in state["tools"] else None

    def run(argv, **kwargs):
        state["ran"].append(argv)
        if argv[0] in state["fail"]:
            raise subprocess.CalledProcessError(1, argv)
        if argv[0] == "gsettings":
            if not state["gsettings_ok"]:
                raise subprocess.CalledProcessError(1, argv, stderr="no such schema")
            if argv[1] == "get":
                return subprocess.CompletedProcess(
                    argv, 0, stdout=state["keys"].get(argv[3], "") + "\n", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(nl.shutil, "which", which)
    monkeypatch.setattr(nl.subprocess, "run", run)
    return state


class TestReportsWhatActuallyHappened:
    def test_says_nothing_succeeded_when_nothing_can(self, desktop, logged):
        """No Cinnamon keys, no gammastep, no xsct — a bare or foreign desktop."""
        assert nl.set_nightlight(True, 4000, force=True) is False

        assert any("no night-light backend available" in m for m in logged)
        assert any("could not be turned on" in m for m in logged)
        # The bug this test exists for: the success line printed regardless,
        # one line under the warning saying nothing could do it.
        assert not any(m.startswith("night light → on") for m in logged)

    def test_reports_success_through_cinnamon(self, desktop, logged):
        desktop["tools"].add("gsettings")
        desktop["gsettings_ok"] = True

        assert nl.set_nightlight(True, 3500, force=True) is True

        assert any("night light → on @ 3500K" in m for m in logged)
        # The fallback must not run when the real thing worked.
        assert all(argv[0] == "gsettings" for argv in desktop["ran"])

    def test_names_the_fallback_that_did_it(self, desktop, logged):
        """Worth naming: it says the warmth isn't coming from Cinnamon."""
        desktop["tools"].update({"gsettings", "gammastep"})   # present, but failing

        assert nl.set_nightlight(True, 4000, force=True) is True

        assert any("(via gammastep)" in m for m in logged)
        assert ["gammastep", "-O", "4000"] in desktop["ran"]

    def test_falls_through_to_xsct(self, desktop, logged):
        desktop["tools"].add("xsct")

        assert nl.set_nightlight(False, 4000, force=True) is True

        assert any("(via xsct)" in m for m in logged)
        assert ["xsct", "6500"] in desktop["ran"], "off means back to daylight"

    def test_a_fallback_that_fails_is_not_a_success(self, desktop, logged):
        desktop["tools"].add("gammastep")
        desktop["fail"].add("gammastep")

        assert nl.set_nightlight(True, 4000, force=True) is False

        assert any("fallback failed" in m for m in logged)
        assert not any(m.startswith("night light → on") for m in logged)

    def test_already_correct_counts_as_success(self, desktop, logged):
        """Nothing to do is not a failure — and must not touch the screen."""
        desktop["tools"].add("gsettings")
        desktop["gsettings_ok"] = True
        desktop["keys"]["night-light-enabled"] = "false"

        assert nl.set_nightlight(False, 4000) is True

        assert any("already off" in m for m in logged)
        assert not any(argv[1] == "set" for argv in desktop["ran"]), \
            "an already-correct desktop must not be written to"
