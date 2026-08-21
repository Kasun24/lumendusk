#!/usr/bin/env bash
#
# Install Lumendusk on Linux Mint (Cinnamon):
#   1. installs the Python engine into a self-contained venv (no system Python
#      changes, works around PEP 668 externally-managed environments), and
#   2. copies the Cinnamon applet into place so you can add it to your panel.
#
# After running, right-click your panel → "Add applets" → Lumendusk → "+".
#
set -euo pipefail

UUID="lumendusk@kasun"
ROOT="$(cd "$(dirname "$0")" && pwd)"
APPLET_SRC="$ROOT/applet/$UUID"
# XDG base directories, same as the engine reads (and the same defaults). Worth
# honouring rather than hardcoding ~/.local/share: Cinnamon finds applets
# through the same variable, so a machine that sets it would have us install
# where nothing looks.
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
APPLET_DEST="$DATA_HOME/cinnamon/applets/$UUID"
VENV="$DATA_HOME/lumendusk/venv"

echo "==> Creating the engine venv at:"
echo "    $VENV"
if ! python3 -m venv "$VENV" 2>/dev/null; then
    echo "!! Could not create a venv. Install it with:  sudo apt install python3-venv" >&2
    exit 1
fi

echo "==> Installing the Python engine (with offline sun times)…"
"$VENV/bin/pip" install --quiet --upgrade pip
# Editable install: the venv references this repo, so code edits take effect
# without reinstalling. Keep the repo where it is after installing.
"$VENV/bin/pip" install --quiet -e "${ROOT}[sun]"

echo "==> Installing the Cinnamon applet to:"
echo "    $APPLET_DEST"
mkdir -p "$APPLET_DEST"
cp -r "$APPLET_SRC/." "$APPLET_DEST/"

echo "==> Installing autostart entry (runs the daemon on login)…"
AUTOSTART_DIR="$CONFIG_HOME/autostart"
mkdir -p "$AUTOSTART_DIR"
sed "s|@ENGINE@|$VENV/bin/lumendusk|g" \
    "$ROOT/packaging/lumendusk.desktop.in" > "$AUTOSTART_DIR/lumendusk.desktop"

echo "==> Starting the daemon now (if not already running)…"
if ! pgrep -f "$VENV/bin/lumendusk\$" >/dev/null 2>&1; then
    setsid "$VENV/bin/lumendusk" >/dev/null 2>&1 < /dev/null &
    echo "    started."
else
    echo "    already running."
fi

cat <<EOF

Done.

Next steps:
  1. Right-click your panel → "Add applets".
  2. Select "Lumendusk" and click the "+" (add) button.
  3. Tell it when your day is. It uses fixed times (dark 19:00, light 07:00)
     until you give it a location, since there's no way to guess one offline:
       $VENV/bin/lumendusk location <latitude> <longitude>
     e.g. 51.5074 -0.1278 for London. That switches it to sunrise/sunset.
     Everything else is in the config file (applet → "Open config file").

The background daemon is now running and will start automatically on login.
Manage it from Cinnamon's "Startup Applications", or:
  pkill -f "$VENV/bin/lumendusk\$"                 # stop it now
  rm $AUTOSTART_DIR/lumendusk.desktop              # disable autostart
  ./uninstall.sh                                   # remove it all

The engine lives in its own venv ($VENV) — nothing was installed into your
system Python. Command line, if you want it:
  $VENV/bin/lumendusk --once      # apply the correct state right now
  $VENV/bin/lumendusk status      # control / mode / phase, plus file locations
  $VENV/bin/lumendusk manual      # leave the desktop to you (movie mode)
  $VENV/bin/lumendusk auto        # follow the schedule again

The daemon runs detached, so if something doesn't happen, look here:
  tail -f ${XDG_STATE_HOME:-$HOME/.local/state}/lumendusk/lumendusk.log

Optional system tools for full functionality:
  - ddcutil       (external-monitor brightness over DDC/CI; add yourself to the
                   'i2c' group and load the i2c-dev module)
  - brightnessctl (internal-panel brightness without root)
  - gammastep     (night-light fallback if Cinnamon's own keys are missing)
EOF
