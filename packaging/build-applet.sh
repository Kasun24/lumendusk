#!/usr/bin/env bash
#
# Build the self-contained Cinnamon applet bundle in dist/.
#
# Cinnamon Spices installs an applet by extracting a zip into
# ~/.local/share/cinnamon/applets/<uuid>/ and running nothing at all — no
# scripts, no venv, no pip, no network. Anything the applet needs has to be
# inside that zip. So this bundles the Python engine and its pure-Python
# dependencies alongside applet.js:
#
#   lumendusk@kasun/
#     applet.js, metadata.json, settings-schema.json
#     engine/run.py            entry point (sets sys.path, calls the CLI)
#     engine/lumendusk/        the engine itself
#     engine/vendor/           astral (+ tomli on Python < 3.11)
#
# This is a maintainer step, not something users run — install.sh still builds
# a venv for development, and the applet prefers a real install over the
# bundled copy (see findEngineArgv in applet.js).
#
# Needs network for pip. Run: ./packaging/build-applet.sh
#
set -euo pipefail

UUID="lumendusk@kasun"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist/$UUID"

# Pinned so a rebuild produces the same bundle. Bump deliberately.
ASTRAL_VERSION="3.2"
# tomli only matters on Python < 3.11 (Mint 21 ships 3.10); 3.11+ has tomllib
# in the stdlib and never looks at it.
TOMLI_VERSION="2.0.1"

if ! command -v python3 >/dev/null; then
    echo "!! python3 is required to build the bundle." >&2
    exit 1
fi

echo "==> Assembling $UUID"
rm -rf "$OUT"
mkdir -p "$OUT/engine/vendor"

cp "$ROOT/applet/$UUID/applet.js" \
   "$ROOT/applet/$UUID/metadata.json" \
   "$ROOT/applet/$UUID/settings-schema.json" \
   "$ROOT/applet/$UUID/icon.png" \
   "$ROOT/applet/$UUID/icon.svg" \
   "$OUT/"

# Spices shows the changelog on the applet's page, and every applet in the
# repository carries one next to its icon.
cp "$ROOT/CHANGELOG.md" "$OUT/"

# The engine is copied from src/ every build rather than kept as a second copy
# in git. Two checked-in copies would drift, and the drift would only show up
# on someone else's desktop.
cp -r "$ROOT/src/lumendusk" "$OUT/engine/lumendusk"
find "$OUT/engine/lumendusk" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
cp "$ROOT/packaging/engine-entry.py" "$OUT/engine/run.py"

echo "==> Fetching dependencies (astral $ASTRAL_VERSION, tomli $TOMLI_VERSION)…"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
if ! python3 -m pip install --quiet --target "$TMP" \
        "astral==$ASTRAL_VERSION" "tomli==$TOMLI_VERSION" 2>"$TMP/pip.err"; then
    echo "!! Could not download dependencies. Needs network and pip:" >&2
    sed 's/^/   /' "$TMP/pip.err" >&2
    exit 1
fi

echo "==> Trimming astral to the modules the engine actually reaches…"
# astral ships ~160K, but the engine only imports Observer and sun.elevation.
# Rather than hardcode a file list that goes stale the moment someone imports
# astral.moon, walk the real import graph from what the engine uses.
python3 - "$TMP" "$OUT" <<'PY'
import ast
import os
import shutil
import sys

src, out = sys.argv[1], sys.argv[2]
vendor = os.path.join(out, "engine", "vendor")


def module_file(root, mod):
    p = os.path.join(root, mod.replace(".", "/"))
    return p + "/__init__.py" if os.path.isdir(p) else p + ".py"


# Seed from what the engine imports, read out of the engine source itself.
seeds = set()
for dirpath, _, names in os.walk(os.path.join(out, "engine", "lumendusk")):
    for name in names:
        if not name.endswith(".py"):
            continue
        tree = ast.parse(open(os.path.join(dirpath, name), encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] == "astral":
                    seeds.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "astral":
                        seeds.add(alias.name)

if not seeds:
    sys.exit("no astral imports found in the engine — has sun mode been removed?")

# Transitive closure over astral's own imports.
need, seen = set(seeds) | {"astral"}, set()
while need - seen:
    mod = (need - seen).pop()
    seen.add(mod)
    path = module_file(src, mod)
    if not os.path.exists(path):
        continue
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] == "astral":
                need.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "astral":
                    need.add(alias.name)

os.makedirs(os.path.join(vendor, "astral"), exist_ok=True)
for mod in sorted(seen):
    path = module_file(src, mod)
    if not os.path.exists(path):
        continue
    rel = os.path.relpath(path, src)
    dest = os.path.join(vendor, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(path, dest)
    print("      astral: %s" % rel)

# tomli is small and has no submodules worth trimming.
if os.path.isdir(os.path.join(src, "tomli")):
    shutil.copytree(os.path.join(src, "tomli"),
                    os.path.join(vendor, "tomli"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    print("      tomli: whole package")

# Both are third-party and separately licensed — carry the notices.
for info in sorted(os.listdir(src)):
    if not info.endswith(".dist-info"):
        continue
    for name in ("LICENSE", "LICENSE.txt", "LICENCE", "COPYING"):
        lic = os.path.join(src, info, name)
        if os.path.exists(lic):
            shutil.copy2(lic, os.path.join(vendor, "LICENSE-%s" % info.split("-")[0]))
            break
PY

cat > "$OUT/engine/vendor/README" <<'EOF'
Third-party code bundled so the applet works when installed from Cinnamon
Spices, which extracts a zip and runs no installer.

  astral  — sunrise/sunset, Apache-2.0, see LICENSE-astral.
            Trimmed to the modules the engine imports.
  tomli   — TOML parser for Python < 3.11, MIT, see LICENSE-tomli.
            Unused on 3.11+, which has tomllib in the stdlib.

Neither is modified. Both are pure Python with no compiled extensions.
EOF

echo "==> Verifying the bundle runs with nothing installed…"
# The point of the bundle is that it works on a machine with a bare python3, so
# check it that way: no venv, no PYTHONPATH, and an empty environment so a
# stray site-packages can't make a missing vendor file look fine.
if ! env -i PATH=/usr/bin:/bin HOME="$TMP" python3 "$OUT/engine/run.py" --help >/dev/null; then
    echo "!! The bundled engine failed to run. The bundle is not usable." >&2
    exit 1
fi
echo "    engine runs."

if command -v zip >/dev/null; then
    (cd "$ROOT/dist" && rm -f "$UUID.zip" && zip -qr "$UUID.zip" "$UUID")
    echo "==> dist/$UUID.zip  ($(du -h "$ROOT/dist/$UUID.zip" | cut -f1))"
else
    echo "==> zip not installed; bundle left unarchived at dist/$UUID"
fi

echo
echo "Bundle: $OUT ($(du -sh "$OUT" | cut -f1))"
echo "Test it like a Spices user would:"
echo "  rm -rf ~/.local/share/cinnamon/applets/$UUID"
echo "  cp -r $OUT ~/.local/share/cinnamon/applets/"
echo "  # then restart Cinnamon (Alt+F2, r)"
