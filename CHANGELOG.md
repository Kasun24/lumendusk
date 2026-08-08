# Changelog

All notable changes to Lumendusk. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-08-08

First release worth a version number. Phase 1 (Linux Mint / Cinnamon) is
functionally complete: the panel applet, the settings panel, and a background
engine that switches theme, night light and brightness on a schedule.

Pre-1.0 because Windows and macOS are Phase 3, and because this has not yet
been observed running a full unattended day/night cycle.

### Added

- **Cinnamon panel applet** (`lumendusk@kasun`) with an Automatic / Manual
  switch, Light / Dark and a live night-light toggle in Manual, a brightness
  slider, and Apply day/night now.
- **Settings panel** (right-click → Configure) covering mode, location, fixed
  times, night-light warmth and brightness presets, including one-click
  location detection from the system timezone — offline, from
  `/usr/share/zoneinfo`.
- **Whole-desktop dark/light switching**, driven by Mint's own style catalog
  in `/usr/share/cinnamon/styles.d`, so the shell, panel, window borders,
  GTK/GTK4, Flatpak (XApp portal), icons and accent all move together.
- **Day/night detection** from sunrise/sunset (offline, via `astral`) or fixed
  times. Sun mode compares solar *elevation* rather than today's sunrise and
  sunset times, which is what makes it correct across the Americas, the
  Pacific, and inside the polar circles.
- **Brightness** across sysfs/brightnessctl, ddcutil (DDC/CI) and xrandr,
  normalised to 0–100 %, applied at each transition when enabled.
- **Self-contained applet bundle** (`packaging/build-applet.sh`) carrying the
  engine and its pure-Python dependencies, because a Cinnamon Spices install
  extracts a zip and runs no installer.
- Autostart on login, and a log at `~/.local/state/lumendusk/lumendusk.log`.

### Fixed

- **ddcutil is now serialised across processes.** DDC/CI is a shared bus and
  concurrent calls do not queue — they fail. Twelve deliberately overlapping
  operations produced 16 errors before the lock and none after, including a
  brightness *write* lost to `DDCRC_RETRIES`.
- **Applying a phase no longer rewrites settings that are already correct.**
  dconf notifies on every write, so the old behaviour made Cinnamon reload its
  theme for nothing at every login and every switch back to Automatic.
- **Every command the daemon waits for now has a timeout.** A hung `ddcutil`
  used to stop the daemon mid-tick with its process still alive and its log
  simply silent — indistinguishable from a healthy idle daemon.
- **The panel menu stays open** when you pick a mode or an appearance.
  Clicking Manual is what reveals Light / Dark, so closing at that moment hid
  the controls the click had just unlocked.
- **Manual mode no longer has its night light undone by the daemon.** The
  one-time drop on entering Manual was implemented in both the CLI and the
  daemon loop; the daemon's copy could land up to a minute later and reverse a
  toggle the user had just made.
- Brightness changes are logged, and a write that failed on every monitor is
  no longer reported as a success.

### Changed

- The four overlapping "don't automate" controls (`enabled`, `paused`, a Dark
  mode switch, and Switch to Day/Night) collapsed into a single
  **Automatic / Manual** choice. Old configs migrate on load; `pause` and
  `resume` remain as aliases.
- Monitor discovery is cached in `~/.cache/lumendusk/monitors.json`, keyed on
  which displays the kernel reports as connected, so a hotplug invalidates it
  at once rather than waiting out a timer.
- `ruff` runs in CI, with the rule set pinned so a ruff release cannot fail the
  build on rules nobody chose.
