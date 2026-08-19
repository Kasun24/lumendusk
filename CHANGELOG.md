# Changelog

All notable changes to Lumendusk. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] — 2026-08-19

### Fixed

- **Night light and brightness settings did nothing until the next
  transition.** Changing the warmth or a brightness preset in Screen settings
  stored the value and left the screen alone — for up to a whole phase, which
  looked like a control that wasn't wired up. Only the appearance setting had
  been given this treatment in 0.2.0; the other two now behave the same way.
  Still narrow, so it can't be mistaken for the daemon overriding you: only the
  setting that actually changed is applied, and only if it affects the phase
  you are in. Editing the day brightness after dark changes nothing tonight,
  and a level you nudged by hand this evening survives the edit.

- **The settings panel's sliders no longer fire once per step.** Cinnamon
  reports every value a slider passes on the way to where you let go, which was
  harmless while those values only reached a file and is not now that they reach
  the screen. Edits are coalesced, and only one write per setting is ever out at
  a time with the newest value winning — so a brightness drag lands where you
  left it, instead of replaying every stop on the way at DDC/CI's pace.

### Changed

- `lumendusk config set` takes `--apply`, which shows the stored change now
  instead of waiting for the daemon's next tick. This is what the settings
  panel uses, so the panel and the schedule agree on what a changed setting
  means rather than each deciding for itself.

## [0.2.0] — 2026-08-12

### Added

- **Each phase chooses its own appearance.** Day → light and night → dark were
  hard-coded; they are now settings (Screen → Appearance, or `theme_day` /
  `theme_night` in the config file). Set the daytime appearance to Dark and the
  desktop stays dark at noon while the night light and brightness still follow
  the clock — the common case of preferring dark without giving up the rest.
  Setting both phases the same simply stops the theme from changing.
- `lumendusk appearance auto` applies whichever appearance the schedule calls
  for right now, and nothing else.

### Changed

- The daemon applies a changed appearance setting at once instead of waiting
  for the next transition. Transition-only apply exists to protect changes the
  user makes *by hand*; a setting they just edited is a request, not drift.
- The panel's status line reports the phase rather than reading it off the
  shell theme, which stops being the same thing once the day can be dark.

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
