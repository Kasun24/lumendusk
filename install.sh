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
APPLET_DEST="$HOME/.local/share/cinnamon/applets/$UUID"
VENV="$HOME/.local/share/lumendusk/venv"

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
"$VENV/bin/pip" install --quiet -e "$ROOT[sun]"

echo "==> Installing the Cinnamon applet to:"
echo "    $APPLET_DEST"
mkdir -p "$APPLET_DEST"
cp -r "$APPLET_SRC/." "$APPLET_DEST/"

cat <<EOF

Done.

Next steps:
  1. Right-click your panel → "Add applets".
  2. Select "Lumendusk" and click the "+" (add) button.
  3. Click the new panel icon → "Open config file" to set your location
     (latitude/longitude) or fixed times.

The engine lives in its own venv ($VENV) — nothing was installed into your
system Python. Command line, if you want it:
  $VENV/bin/lumendusk --once

Optional system tools for full functionality:
  - ddcutil       (external-monitor brightness over DDC/CI; add yourself to the
                   'i2c' group and load the i2c-dev module)
  - brightnessctl (internal-panel brightness without root)
  - gammastep     (night-light fallback if Cinnamon's own keys are missing)
EOF
