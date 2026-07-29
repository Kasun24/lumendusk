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

- Sun (offline, via `astral`) or fixed-time day/night detection.
- **Whole-desktop dark/light switching** — driven by Mint's own style catalog,
  it moves the shell, panel, window borders, GTK/GTK4 apps, Flatpak apps (XApp
  portal), icons and accent together (not just the GTK theme), and night light
  on/off. There's a **Dark mode** switch in the applet too.
- A brightness read/set/list tool across sysfs/brightnessctl, ddcutil, and
  xrandr backends (Step B1).
- A Cinnamon **panel applet** with a brightness slider, day/night presets, and a
  **"Pause automation"** switch (freeze everything, e.g. while watching a movie).
- A background daemon that **autostarts on login**.

Next: an applet **settings panel** and persistence (Step B2), then brightness on
day/night transitions (Step B3).

## How it works

- Runs quietly in the background, started with the applet / on login.
- Decides day vs. night from either **sunrise/sunset** (computed offline from
  your latitude/longitude via [`astral`](https://pypi.org/project/astral/)) or
  **fixed times** you set.
- On a day↔night transition it applies the matching theme, toggles night light,
  and (if enabled) sets the brightness preset.
- Applies only *on transitions*, so a manual change you make by hand sticks until
  the next transition. Wakes about once a minute; idle in between.

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

Day/night comes from either your **location** (sunrise/sunset, computed
offline) or **fixed times**. Fixed times (dark 19:00, light 07:00) are the
default, because there is no way to guess a location offline.

```bash
lumendusk location 51.5074 -0.1278   # your latitude/longitude → switches to sun mode
lumendusk status                     # mode, current phase, and where the config/log live
```

Everything else lives in `~/.config/lumendusk/config.toml` — the applet's
**Open config file** item opens it. Note that Lumendusk rewrites this file when
you change something from the applet or CLI, so comments you add won't survive.

## Command line (for testing / headless)

```bash
lumendusk --once                 # apply the correct day/night state now, then exit
lumendusk                        # run the background daemon
lumendusk status                 # mode / phase / paused, plus config + log paths
lumendusk location LAT LON       # set your location and switch to sun mode
lumendusk pause | resume         # freeze automation (e.g. while watching a movie)
lumendusk brightness list        # show monitors + which backend each uses
lumendusk brightness get         # current brightness
lumendusk brightness set 60      # set brightness to 60%
lumendusk brightness day|night   # apply the day/night brightness preset
lumendusk appearance toggle      # flip whole-desktop dark <-> light (or dark|light|status)

# From a source checkout without installing:
PYTHONPATH=src python3 -m lumendusk --once
```

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
