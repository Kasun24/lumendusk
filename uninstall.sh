#!/usr/bin/env bash
#
# Remove Lumendusk: stops the daemon, then deletes the engine venv, the Cinnamon
# applet, and the autostart entry — i.e. everything install.sh created.
#
# Your settings are left alone unless you ask for them to go:
#   ./uninstall.sh --purge
#
# The repo checkout itself is never touched; delete it yourself if you want it
# gone.
#
set -euo pipefail

UUID="lumendusk@kasun"
APPLET_DEST="$HOME/.local/share/cinnamon/applets/$UUID"
VENV="$HOME/.local/share/lumendusk/venv"
AUTOSTART="$HOME/.config/autostart/lumendusk.desktop"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/lumendusk"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/lumendusk"

PURGE=0
for arg in "$@"; do
    case "$arg" in
        --purge) PURGE=1 ;;
        -h|--help)
            echo "Usage: $0 [--purge]"
            echo "  --purge   also delete your config and log ($CONFIG_DIR, $STATE_DIR)"
            exit 0
            ;;
        *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
    esac
done

echo "==> Stopping the daemon…"
# Matches install.sh's own pgrep pattern. No daemon running is fine, so don't
# let `set -e` treat "nothing matched" as a failure.
if pkill -f "$VENV/bin/lumendusk\$" 2>/dev/null; then
    echo "    stopped."
else
    echo "    not running."
fi

echo "==> Removing the autostart entry…"
rm -f "$AUTOSTART"

echo "==> Removing the Cinnamon applet…"
rm -rf "$APPLET_DEST"

echo "==> Removing the engine venv…"
rm -rf "$VENV"
# Only if it's now empty — the user may keep other things under this directory.
rmdir "$HOME/.local/share/lumendusk" 2>/dev/null || true

if [ "$PURGE" -eq 1 ]; then
    echo "==> Removing settings and log…"
    rm -rf "$CONFIG_DIR" "$STATE_DIR"
fi

cat <<EOF

Done.

EOF
if [ "$PURGE" -eq 0 ]; then
    cat <<EOF
Your settings were kept at:
  $CONFIG_DIR
Re-run with --purge to remove them (and the log at $STATE_DIR) too.

EOF
fi
cat <<EOF
If the applet is still on your panel, right-click it → "Remove 'Lumendusk'".
EOF
