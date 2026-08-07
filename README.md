# Lumendusk

> Automatic dark/light theme, **night light** (warm color temperature), **and monitor brightness** for your desktop — driven by the time of day.

Lumendusk is a lightweight tool that adjusts your desktop automatically, with no interaction needed:

1. Switches the system theme between **light** (day) and **dark** (night).
2. Turns **night light / warm screen tint** on at night and off during the day.
3. Sets **monitor brightness** to a day level and a dimmer night level.

The main way you use it is as a **panel applet** you add to your panel — a small
icon with a dropdown menu. A background engine does the work behind it.

Built for **Linux Mint (Cinnamon)** first, then Windows (system-tray icon) and
macOS (menu-bar extra).

**Core principles:** simple · automatic · offline-first · low resource usage · cross-platform.

---

## Status

🚧 Early development — Phase 1 (Linux Mint). Working today:

- Two modes, **Automatic** and **Manual**, switchable from the panel menu.
  Automatic follows the schedule; Manual hands the desktop back to you.
- Sun (offline, via `astral`) or fixed-time day/night detection.
- **Whole-desktop dark/light switching** — driven by Mint's own style catalog,
  it moves the shell, panel, window borders, GTK/GTK4 apps, Flatpak apps (XApp
  portal), icons and accent together (not just the GTK theme), and night light
  on/off.
- A brightness read/set/list tool across sysfs/brightnessctl, ddcutil, and
  xrandr backends (Step B1).
- A Cinnamon **panel applet**: the mode switch, Light/Dark and a night light
  toggle in Manual, and a brightness slider.
- A **settings panel** (right-click → Configure) for mode, location, times,
  night-light warmth and brightness presets — including one-click location
  detection from your system timezone.
- A background daemon that **autostarts on login**.

Next: brightness on day/night transitions (Step B3).

## How it works

- Runs quietly in the background, started with the applet / on login.
- Decides day vs. night from either **sunrise/sunset** (computed offline from
  your latitude/longitude via [`astral`](https://pypi.org/project/astral/)) or
  **fixed times** you set.
- On a day↔night transition it applies the matching theme, toggles night light,
  and (if enabled) sets the brightness preset.
- Applies only *on transitions*, so a manual change you make by hand sticks until
  the next transition. Wakes about once a minute; idle in between.

### Automatic and Manual

One switch decides who is driving, and it's the first thing in the panel menu.

**Automatic** is the normal state: Lumendusk follows your schedule, and the menu
just tells you what it's doing ("Following sunrise and sunset · night"). It
deliberately offers no dark/light buttons here — a choice that silently expires
at the next sunrise is worse than no choice at all.

**Manual** hands the desktop back to you. The menu grows **Light** / **Dark**
and a **Night light** switch, and nothing changes on its own until you switch
back — not on a transition, not after a suspend, not on your next login.
Switching *into* Manual drops the night light once, so colors are true for a
film; after that the toggle is yours.

Both live in the settings panel too, so the menu and Configure never disagree.

## Install (Linux Mint / Cinnamon)

Needs **Python 3.9+** and `python3-venv` (`sudo apt install python3-venv`) —
Mint 21 and 22 both ship a new enough Python.

```bash
git clone https://github.com/Kasun24/lumendusk.git
cd lumendusk
./install.sh
```

`install.sh` builds a self-contained venv under
`~/.local/share/lumendusk/venv` (nothing is installed into your system Python),
copies the applet into place, and starts the background daemon.

Then right-click your panel → **Add applets** → **Lumendusk** → **+**.

Optional system tools, each unlocking one feature:

| Tool | What it adds |
|------|--------------|
| `ddcutil` | Brightness on external monitors over DDC/CI (needs the `i2c-dev` module and your user in the `i2c` group) |
| `brightnessctl` | Laptop-panel brightness without root |
| `gammastep` or `xsct` | Night light where Cinnamon's own keys are missing |

### Uninstall

```bash
./uninstall.sh
```

Removes the venv, the applet, and the autostart entry. Your config is kept
unless you pass `--purge`.

## Setting it up

**Right-click the panel icon → Configure.** Everything lives there: Automatic
vs. Manual, whether to follow the sun or fixed times, your location, how yellow
the night light goes, and the brightness presets.

Day/night comes from either your **location** (sunrise/sunset, computed
offline) or **fixed times**. Fixed times (dark 19:00, light 07:00) are the
default, because there is no way to guess a location offline.

Switching to **Sunrise and sunset** needs coordinates. Rather than making you
look them up, **Detect from my timezone** reads the location your system
timezone already implies — `Asia/Colombo` → 6.93, 79.85. That comes from
`/usr/share/zoneinfo`, so it works with no network and no extra dependency.
It's accurate to the timezone's main city, which puts sunset within a minute or
two for most people; the fields stay editable if you want it exact.

The same thing from a terminal:

```bash
lumendusk location                   # what's set, and what would be detected
lumendusk location --detect          # take it from the system timezone
lumendusk location 51.5074 -0.1278   # or set it yourself → switches to sun mode
lumendusk status                     # mode, current phase, and where config/log live
```

Settings are stored in `~/.config/lumendusk/config.toml`; the settings panel is
a view onto that file and writes changes straight back to it, so the CLI and the
panel can't disagree. Editing the file by hand works too (the applet's **Open
config file** item opens it) — just note that Lumendusk rewrites the file when
anything changes, so comments you add won't survive.

## Command line (for testing / headless)

```bash
lumendusk --once                 # apply the correct day/night state now, then exit
lumendusk                        # run the background daemon
lumendusk status                 # control / mode / phase, plus config + log paths
lumendusk auto                   # follow the schedule, and apply it right now
lumendusk manual                 # leave the desktop to you (night light off)
lumendusk toggle                 # flip between the two
lumendusk nightlight on|off|toggle|status   # the warm tint, right now
lumendusk location               # show the current + auto-detected location
lumendusk location --detect      # set it from the system timezone
lumendusk location LAT LON       # set your location and switch to sun mode
lumendusk config show            # every setting as key=value
lumendusk config set KEY VALUE   # change one setting (validated)
lumendusk brightness list        # show monitors + which backend each uses
lumendusk brightness get         # current brightness
lumendusk brightness set 60      # set brightness to 60%
lumendusk brightness day|night   # apply the day/night brightness preset
lumendusk appearance toggle      # flip whole-desktop dark <-> light (or dark|light|status)

# From a source checkout without installing:
PYTHONPATH=src python3 -m lumendusk --once
```

`pause` and `resume` still work as aliases for `manual` and `auto`. If you're
upgrading, a config with the old `enabled = false` or `paused = true` becomes
`control = "manual"` the first time it's read — an upgrade shouldn't start
changing a desktop that was deliberately left alone.

## Troubleshooting

The daemon runs detached, so it writes to a log file rather than a terminal:

```bash
tail -f ~/.local/state/lumendusk/lumendusk.log
```

That's the first place to look if a theme, night light, or brightness change
didn't happen — a missing backend or an unreadable config is reported there.
Lumendusk keeps running on the last good settings rather than exiting.

## Development

```bash
pip install -e '.[sun,dev]'
pytest
```

## Roadmap

| Phase | Focus |
|-------|-------|
| 1 | Linux Mint: day/night detection + theme + night light + brightness tool, as a panel applet |
| 2 | Test & polish (full cycle incl. suspend, brightness automation, low CPU/mem) |
| 3 | Cross-platform (Windows system tray + registry, macOS menu bar) |
| 4 | Publish (Cinnamon Spices, Flathub/Snap, Microsoft Store) |

## License

[MIT](LICENSE)
