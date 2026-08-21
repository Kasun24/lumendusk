#!/usr/bin/env bash
#
# Build the Cinnamon Spices submission tree in dist/spices/.
#
# The Spices repository does not take the applet the way Cinnamon installs it.
# It wants two layers: an outer directory whose contents are for the website
# and for GitHub, and an inner one holding exactly what gets zipped up and
# extracted onto a user's machine.
#
#   lumendusk@kasun/
#     info.json                 author + license, for the website
#     screenshot.png            shown on the applet's page
#     README.md                 rendered on the page and on GitHub
#     files/
#       lumendusk@kasun/        ← this, and only this, becomes the zip
#         applet.js, metadata.json, settings-schema.json, icon.png, …
#         engine/               the Python engine and its vendored deps
#
# So this script builds the ordinary bundle (build-applet.sh), drops it in as
# the inner directory, adds the three outer files from packaging/spices/, and
# then checks the result against the rules the upstream `validate-spice` script
# enforces. Those checks are repeated here rather than deferred to submission
# time because the upstream script only exists inside a clone of a ~1 GB
# repository, and finding out about a forbidden field after opening a pull
# request wastes a reviewer's time instead of ours.
#
# This is a maintainer step. Users install from Spices or from install.sh.
#
# Run: ./packaging/build-spices.sh
#
set -euo pipefail

UUID="lumendusk@kasun"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist/spices/$UUID"

echo "==> Building the applet bundle first"
"$ROOT/packaging/build-applet.sh" >/dev/null

echo "==> Assembling the Spices tree"
rm -rf "$ROOT/dist/spices"
mkdir -p "$OUT/files"

# files/ has to contain the UUID directory and nothing else — a stray file
# there makes the spice uninstallable from System Settings, which is a failure
# no test on this machine would ever show.
cp -r "$ROOT/dist/$UUID" "$OUT/files/$UUID"

cp "$ROOT/packaging/spices/info.json" "$OUT/info.json"
cp "$ROOT/packaging/spices/README.md" "$OUT/README.md"
cp "$ROOT/packaging/screenshot.png" "$OUT/screenshot.png"

echo "==> Validating"
python3 - "$OUT" "$UUID" <<'PY'
import json
import os
import struct
import subprocess
import sys

out, uuid = sys.argv[1], sys.argv[2]
problems = []


def check(condition, message):
    if not condition:
        problems.append(message)


inner = os.path.join(out, "files", uuid)

# The five files the repository requires, and the one it forbids: an icon.png
# at the spice root is where the *old* layout put it, and leaving one there is
# the classic way a resubmitted applet fails.
for rel in ("info.json", "screenshot.png",
            "files/%s/metadata.json" % uuid,
            "files/%s/icon.png" % uuid,
            "files/%s/applet.js" % uuid):
    check(os.path.isfile(os.path.join(out, rel)), "missing: %s" % rel)
check(not os.path.exists(os.path.join(out, "icon.png")),
      "icon.png at the spice root is forbidden (it belongs in files/%s/)" % uuid)

entries = sorted(os.listdir(os.path.join(out, "files")))
check(entries == [uuid],
      "files/ must contain only %s, found: %s" % (uuid, ", ".join(entries)))

info = json.load(open(os.path.join(out, "info.json"), encoding="utf-8"))
author = info.get("author", "")
check(bool(author), "info.json has no author")
# The website links the author to a GitHub account, so this is a username, not
# a person's name — and a name with a space in it is the usual mistake.
check(author == author.strip() and " " not in author and "\t" not in author,
      "info.json author must be a GitHub username with no whitespace: %r" % author)

meta = json.load(open(os.path.join(inner, "metadata.json"), encoding="utf-8"))
check(meta.get("uuid") == uuid,
      "metadata.json uuid %r does not match the directory name" % meta.get("uuid"))
for field in ("uuid", "name", "description"):
    check(bool(meta.get(field)), "metadata.json is missing %s" % field)
for field in ("icon", "dangerous", "last-edited"):
    # `icon` is the surprising one: it works locally, and the applet does show
    # that icon in the panel — but it is set in applet.js anyway, and the
    # Spices listing uses icon.png. `last-edited` is written by the Spices
    # infrastructure at install time and must not be shipped.
    check(field not in meta, "metadata.json must not contain %r" % field)
for field, value in meta.items():
    for text in ([value] if isinstance(value, str) else
                 value if isinstance(value, list) else []):
        if isinstance(text, str) and not text.isascii():
            problems.append("metadata.json %s contains non-ASCII text: %r"
                            % (field, text))

with open(os.path.join(inner, "icon.png"), "rb") as fh:
    width, height = struct.unpack(">II", fh.read(24)[16:24])
check(width == height, "icon.png must be square, is %dx%d" % (width, height))

# Translations: sources only, in one place, one template.
pots = []
for dirpath, dirnames, filenames in os.walk(out):
    for name in dirnames:
        check(" " not in name, "directory name contains a space: %s" % name)
    for name in filenames:
        path = os.path.join(dirpath, name)
        rel = os.path.relpath(path, out)
        if name.endswith(".mo"):
            problems.append("compiled translation must not be shipped: %s" % rel)
        elif name.endswith((".po", ".pot")):
            check(os.path.dirname(rel) == os.path.join("files", uuid, "po"),
                  "translations belong in files/%s/po/, found %s" % (uuid, rel))
            if name.endswith(".pot"):
                pots.append(rel)
            if subprocess.call(["msgfmt", "--check-format", "-o", os.devnull, path],
                               stderr=subprocess.DEVNULL) != 0:
                problems.append("msgfmt rejects %s" % rel)
check(len(pots) <= 1, "at most one .pot file, found: %s" % ", ".join(pots))

if problems:
    print("\n!! The tree would fail validate-spice:", file=sys.stderr)
    for problem in problems:
        print("   - %s" % problem, file=sys.stderr)
    sys.exit(1)
print("    passes the checks validate-spice makes.")
PY

echo
echo "Spices tree: $OUT ($(du -sh "$OUT" | cut -f1))"
echo "To submit, copy it into a clone of the applets repository and validate there:"
echo "  cp -r $OUT <clone>/"
echo "  cd <clone> && ./validate-spice $UUID"
