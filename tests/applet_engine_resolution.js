/*
 * Which engine does the applet run?
 *
 * The applet is JavaScript executed by Cinnamon's GJS, so the Python tests
 * can't see it and CI has no Cinnamon to load it into. But the engine lookup
 * is pure logic over GLib calls, and getting it wrong is not subtle: the applet
 * shows "Engine not found" and every menu item silently does nothing, on a
 * machine where the engine is installed and working.
 *
 * So: pull findEngineArgv() out of applet.js, run it against a stubbed GLib,
 * and assert the order. Run with `node tests/applet_engine_resolution.js`.
 */

const fs = require("fs");
const path = require("path");

const appletPath = path.join(__dirname, "..", "applet", "lumendusk@kasun", "applet.js");
const source = fs.readFileSync(appletPath, "utf8");

// Take everything from the candidate list to the settings block: that is the
// lookup and nothing else. Slicing the real file rather than copying it means
// the test can't drift away from the code it is testing.
const start = source.indexOf("const ENGINE_CANDIDATES");
const end = source.indexOf("// Settings we mirror");
if (start === -1 || end === -1 || end <= start) {
    console.error("Could not find the engine lookup in applet.js — has it moved?");
    process.exit(1);
}
const lookup = source.slice(start, end);

function resolve({ executables = [], onPath = null, appletDir = null, python = true,
                   dataDir = "/home/kasun/.local/share" }) {
    const GLib = {
        get_home_dir: () => "/home/kasun",
        get_user_data_dir: () => dataDir,
        FileTest: { IS_EXECUTABLE: 1, EXISTS: 2 },
        file_test: (p) => executables.includes(p),
        find_program_in_path: (name) =>
            name === "python3" ? (python ? "/usr/bin/python3" : null) : onPath,
    };
    // `_appletDir` is module state in the applet, set from metadata.path on init.
    const fn = new Function("GLib", "__appletDir",
        lookup + "\n_appletDir = __appletDir;\nreturn findEngineArgv();");
    return JSON.stringify(fn(GLib, appletDir));
}

const VENV = "/home/kasun/.local/share/lumendusk/venv/bin/lumendusk";
const USER = "/home/kasun/.local/bin/lumendusk";
const APPLET_DIR = "/home/kasun/.local/share/cinnamon/applets/lumendusk@kasun";
const BUNDLED = APPLET_DIR + "/engine/run.py";

const cases = [
    {
        name: "venv install (install.sh)",
        input: { executables: [VENV] },
        expect: `["${VENV}"]`,
    },
    {
        name: "pip install --user",
        input: { executables: [USER] },
        expect: `["${USER}"]`,
    },
    {
        name: "distro package",
        input: { executables: ["/usr/bin/lumendusk"] },
        expect: `["/usr/bin/lumendusk"]`,
    },
    {
        name: "anything else on PATH",
        input: { onPath: "/opt/lumendusk/bin/lumendusk" },
        expect: `["/opt/lumendusk/bin/lumendusk"]`,
    },
    {
        // The Spices case: a zip was extracted and nothing else happened.
        name: "bundled engine only",
        input: { executables: [BUNDLED], appletDir: APPLET_DIR },
        expect: `["/usr/bin/python3","${BUNDLED}"]`,
    },
    {
        // A dev checkout must win, or edits would appear to do nothing.
        name: "a real install beats the bundled copy",
        input: { executables: [VENV, BUNDLED], appletDir: APPLET_DIR },
        expect: `["${VENV}"]`,
    },
    {
        name: "venv beats ~/.local/bin",
        input: { executables: [VENV, USER] },
        expect: `["${VENV}"]`,
    },
    {
        name: "bundled copy is useless without python3",
        input: { executables: [BUNDLED], appletDir: APPLET_DIR, python: false },
        expect: "null",
    },
    {
        name: "nothing installed",
        input: {},
        expect: "null",
    },
    {
        // XDG_DATA_HOME moved, so the venv did too. Hardcoding ~/.local/share
        // here would have the applet report "engine not found" on a machine
        // where install.sh had just put one in place.
        name: "venv under a relocated XDG_DATA_HOME",
        input: {
            executables: ["/data/kasun/lumendusk/venv/bin/lumendusk"],
            dataDir: "/data/kasun",
        },
        expect: `["/data/kasun/lumendusk/venv/bin/lumendusk"]`,
    },
];

let failed = 0;
for (const { name, input, expect } of cases) {
    const got = resolve(input);
    if (got === expect) {
        console.log("  ok   " + name);
    } else {
        failed++;
        console.log("  FAIL " + name);
        console.log("         got  " + got);
        console.log("         want " + expect);
    }
}

if (failed) {
    console.log(failed + " of " + cases.length + " failed");
    process.exit(1);
}
console.log("all " + cases.length + " engine resolution cases pass");
