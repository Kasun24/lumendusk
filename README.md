# Lumendusk

> Automatic dark/light theme **and** night light (warm color temperature) for your desktop — driven by the time of day.

Lumendusk is a lightweight background tool that does two things automatically, with no interaction needed:

1. Switches the system theme between **light** (day) and **dark** (night).
2. Turns **night light / warm screen tint** on at night and off during the day.

Built for **Linux Mint (Cinnamon)** first, then expanding to Windows and macOS.

**Core principles:** simple · automatic · low resource usage · cross-platform.

---

## Status

🚧 Early development — Phase 1 (Linux Mint daemon). See the roadmap below.

## How it works

- Runs quietly in the background as a daemon.
- Decides day vs. night from either **sunrise/sunset** (calculated from your location) or **fixed times** you set.
- On a state change, it applies the matching theme and toggles night light.
- Wakes up about once a minute; idle in between, so it stays light on resources.

## Quick start (development)

```bash
git clone git@github.com:Kasun24/lumendusk.git
cd lumendusk
python3 -m lumendusk --help
```

## Roadmap

| Phase | Focus |
|-------|-------|
| 1 | Linux Mint daemon: day/night detection + theme switch + night light |
| 2 | Test & polish (full day/night cycle, low CPU/mem, on/off toggle) |
| 3 | Cross-platform (Windows registry, macOS gaps) |
| 4 | Publish (Cinnamon Spices, Flathub/Snap, Microsoft Store) |

## License

[MIT](LICENSE)
