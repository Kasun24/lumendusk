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

🚧 Early development — Phase 1 (Linux Mint). The engine and a first Cinnamon
applet exist; sun/fixed day-night detection, theme + night-light switching, and
a brightness read/set tool are in place.

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

```bash
git clone git@github.com:Kasun24/lumendusk.git
cd lumendusk
./install.sh
```

Then right-click your panel → **Add applets** → **Lumendusk** → **+**. Click the
panel icon → **Open config file** to set your location or fixed times.

## Command line (for testing / headless)

```bash
lumendusk --once                 # apply the correct day/night state now, then exit
lumendusk                        # run the background daemon
lumendusk brightness list        # show monitors + which backend each uses
lumendusk brightness get         # current brightness
lumendusk brightness set 60      # set brightness to 60%
lumendusk brightness day|night   # apply the day/night brightness preset

# From a source checkout without installing:
PYTHONPATH=src python3 -m lumendusk --once
```

Config lives at `~/.config/lumendusk/config.toml`.

## Roadmap

| Phase | Focus |
|-------|-------|
| 1 | Linux Mint: day/night detection + theme + night light + brightness tool, as a panel applet |
| 2 | Test & polish (full cycle incl. suspend, brightness automation, low CPU/mem) |
| 3 | Cross-platform (Windows system tray + registry, macOS menu bar) |
| 4 | Publish (Cinnamon Spices, Flathub/Snap, Microsoft Store) |

## License

[MIT](LICENSE)
