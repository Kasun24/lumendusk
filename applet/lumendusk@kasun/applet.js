/*
 * Lumendusk — Cinnamon panel applet.
 *
 * This is a thin JS shell for the panel: an icon + dropdown menu. The actual
 * work (deciding day/night, switching theme, night light, brightness) is done
 * by the Python engine, which this applet calls via its CLI.
 *
 * Settings (right-click → Configure) are defined in settings-schema.json.
 * Cinnamon stores those in its own per-instance JSON, but the engine's source
 * of truth is ~/.config/lumendusk/config.toml — so the panel is kept as a view
 * onto that file: we seed it from `lumendusk config show` on startup, and write
 * every change back with `lumendusk config set`. Nothing here parses TOML.
 */

const Applet = imports.ui.applet;
const PopupMenu = imports.ui.popupMenu;
const Settings = imports.ui.settings;
const Util = imports.misc.util;
const GLib = imports.gi.GLib;
const Gio = imports.gi.Gio;
const Mainloop = imports.mainloop;

// The engine runs from its own venv (created by install.sh), so we don't touch
// the system Python. Absolute path keeps it working regardless of the panel's PATH.
const ENGINE = GLib.get_home_dir() + "/.local/share/lumendusk/venv/bin/lumendusk";

// Settings we mirror into config.toml. Names match the engine's config keys
// exactly, which is what lets the sync below stay generic.
const SYNCED_KEYS = [
    "enabled", "mode", "latitude", "longitude", "dark_start", "light_start",
    "nightlight_enabled", "nightlight_temperature",
    "brightness_enabled", "brightness_day", "brightness_night",
];

function LumenduskApplet(metadata, orientation, panelHeight, instanceId) {
    this._init(metadata, orientation, panelHeight, instanceId);
}

LumenduskApplet.prototype = {
    __proto__: Applet.IconApplet.prototype,

    _init: function (metadata, orientation, panelHeight, instanceId) {
        Applet.IconApplet.prototype._init.call(this, orientation, panelHeight, instanceId);

        this.set_applet_icon_symbolic_name("weather-clear-night");
        this.set_applet_tooltip("Lumendusk — auto theme, night light & brightness");

        this.menuManager = new PopupMenu.PopupMenuManager(this);
        this.menu = new Applet.AppletPopupMenu(this, orientation);
        this.menuManager.addMenu(this.menu);

        // Refresh state each time the menu opens, in case it was changed from
        // the CLI, another instance, or Cinnamon's own settings.
        this.menu.connect("open-state-changed", (menu, open) => {
            if (!open) return;
            if (this._pauseSwitch) this._pauseSwitch.setToggleState(this._readPaused());
            if (this._darkSwitch) this._darkSwitch.setToggleState(this._readDark());
            this._refreshBrightness();
        });

        this._brightnessDebounce = 0;
        // Guards the slider's value-changed handler while we're setting the
        // slider ourselves — otherwise syncing the real value straight back to
        // the engine would re-apply it (and fight the user mid-drag).
        this._syncingSlider = false;
        this._buildMenu();
        this._initSettings(metadata, instanceId);
    },

    // ---- settings panel <-> config.toml -------------------------------------

    _initSettings: function (metadata, instanceId) {
        // Guards the write-back while we're loading values *from* the engine,
        // so seeding the panel doesn't immediately write them all back out.
        this._loadingSettings = true;
        // What we believe the engine already has, so a settings-changed signal
        // only writes the keys that actually moved.
        this._pushed = {};

        let uuid = (metadata && metadata.uuid) || "lumendusk@kasun";
        try {
            this.settings = new Settings.AppletSettings(this, uuid, instanceId);
        } catch (e) {
            global.logError("Lumendusk: could not open applet settings: " + e);
            this._loadingSettings = false;
            return;
        }

        for (let i = 0; i < SYNCED_KEYS.length; i++) {
            let key = SYNCED_KEYS[i];
            // Bound to this.cfg_<key>. The callback fires per-key on older
            // Cinnamon versions; "settings-changed" covers the newer ones. Both
            // land in the same place, and _pushSettings only writes real diffs,
            // so being called twice is harmless.
            this.settings.bind(key, "cfg_" + key, () => this._onSettingsChanged());
        }
        try {
            this.settings.connect("settings-changed",
                                  () => this._onSettingsChanged());
        } catch (e) {
            // Older Cinnamon without the signal — the per-key binds above carry it.
        }

        this._pullSettings();
    },

    _onSettingsChanged: function () {
        if (this._loadingSettings) return;
        this._pushSettings();
    },

    _pullSettings: function () {
        // Seed the panel from config.toml, which is what the engine actually
        // reads. Without this the panel would show schema defaults and the
        // first edit would quietly overwrite the user's real settings.
        this._runEngineAsync(["config", "show"], (stdout) => {
            if (stdout === null) {
                this._loadingSettings = false;
                return;
            }
            this._loadingSettings = true;
            try {
                let values = this._parseKeyValues(stdout);
                for (let key in values) {
                    if (SYNCED_KEYS.indexOf(key) === -1) continue;
                    let value = values[key];
                    this._pushed[key] = value;
                    try {
                        this.settings.setValue(key, value);
                    } catch (e) {
                        global.logError("Lumendusk: could not set '" + key + "': " + e);
                    }
                }
            } finally {
                this._loadingSettings = false;
            }
        });
    },

    _pushSettings: function () {
        // Write back only what changed — one `config set` per edited key. The
        // engine validates; a rejected value is logged and the panel is
        // resynced so it can't keep showing something that was never stored.
        if (!this.settings) return;
        let rejected = false;
        for (let i = 0; i < SYNCED_KEYS.length; i++) {
            let key = SYNCED_KEYS[i];
            let value = this["cfg_" + key];
            if (value === undefined) continue;
            if (this._pushed[key] === value) continue;
            this._pushed[key] = value;
            let text = (typeof value === "boolean")
                ? (value ? "true" : "false") : String(value);
            this._runEngineAsync(["config", "set", key, text], (out, err) => {
                if (out !== null) return;
                global.logError("Lumendusk: rejected " + key + "=" + text +
                                (err ? " (" + err.trim() + ")" : ""));
                if (!rejected) {
                    rejected = true;
                    this._pullSettings();
                }
            });
        }
    },

    onDetectLocation: function () {
        // settings-schema.json button callback.
        this._runEngineAsync(["location", "--detect"], (stdout, stderr) => {
            if (stdout === null) {
                global.logError("Lumendusk: location detection failed" +
                                (stderr ? ": " + stderr.trim() : ""));
                return;
            }
            // The engine wrote a location and switched to sun mode; pull it back
            // so the latitude/longitude fields show what was actually stored.
            this._pullSettings();
        });
    },

    _parseKeyValues: function (text) {
        // "key=value" per line, from `lumendusk config show`. Values are typed
        // to match the schema: Cinnamon stores what it's given, and handing a
        // spinbutton a string would break it.
        let out = {};
        let lines = (text || "").split("\n");
        for (let i = 0; i < lines.length; i++) {
            let split = lines[i].indexOf("=");
            if (split <= 0) continue;
            let key = lines[i].substring(0, split).trim();
            let raw = lines[i].substring(split + 1).trim();
            if (raw === "true" || raw === "false") {
                out[key] = (raw === "true");
            } else if (/^-?\d+$/.test(raw)) {
                out[key] = parseInt(raw, 10);
            } else if (/^-?\d*\.\d+$/.test(raw)) {
                out[key] = parseFloat(raw);
            } else {
                out[key] = raw;
            }
        }
        return out;
    },

    _buildMenu: function () {
        this.menu.removeAll();

        let title = new PopupMenu.PopupMenuItem("Lumendusk", { reactive: false });
        this.menu.addMenuItem(title);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Without the engine every menu item below is a no-op, which looks like
        // a broken applet. Say so instead of failing silently.
        if (!this._engineInstalled()) {
            let missing = new PopupMenu.PopupMenuItem(
                "Engine not found — run install.sh", { reactive: false });
            this.menu.addMenuItem(missing);
            let hint = new PopupMenu.PopupMenuItem(
                "Expected: " + ENGINE, { reactive: false });
            hint.actor.set_style("font-size: 8pt;");
            this.menu.addMenuItem(hint);
            this.set_applet_tooltip("Lumendusk — engine not installed");
            return;
        }

        // Pause automation (e.g. while watching a movie): turns night light off
        // for true colors and freezes theme + brightness until switched back on.
        this._pauseSwitch = new PopupMenu.PopupSwitchMenuItem(
            "Pause automation", this._readPaused());
        this._pauseSwitch.connect("toggled", (item, value) =>
            this._runEngine(value ? "pause" : "resume"));
        this.menu.addMenuItem(this._pauseSwitch);

        // Dark mode: standalone whole-desktop dark/light switch (system UI +
        // apps), independent of the day/night automation. A manual override.
        this._darkSwitch = new PopupMenu.PopupSwitchMenuItem(
            "Dark mode", this._readDark());
        this._darkSwitch.connect("toggled", (item, value) =>
            this._runEngine(value ? "appearance dark" : "appearance light"));
        this.menu.addMenuItem(this._darkSwitch);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Apply the correct phase right now (theme + night light + brightness).
        let applyNow = new PopupMenu.PopupIconMenuItem(
            "Apply day/night now", "view-refresh-symbolic", imports.gi.St.IconType.SYMBOLIC);
        applyNow.connect("activate", () => this._runEngine("--once"));
        this.menu.addMenuItem(applyNow);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Brightness (all monitors) slider.
        let bLabel = new PopupMenu.PopupMenuItem("Brightness (all monitors)", { reactive: false });
        this.menu.addMenuItem(bLabel);
        this._brightnessSlider = new PopupMenu.PopupSliderMenuItem(0.8);
        this._brightnessSlider.connect("value-changed", (slider, value) =>
            this._onBrightnessChanged(value));
        this.menu.addMenuItem(this._brightnessSlider);

        // Full-mode overrides: theme + night light + brightness together. These
        // stick until the next scheduled day/night transition.
        let dayItem = new PopupMenu.PopupMenuItem("Switch to Day mode");
        dayItem.connect("activate", () => this._runEngine("mode day"));
        this.menu.addMenuItem(dayItem);

        let nightItem = new PopupMenu.PopupMenuItem("Switch to Night mode");
        nightItem.connect("activate", () => this._runEngine("mode night"));
        this.menu.addMenuItem(nightItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Settings (config file) — a real panel arrives with Step B2.
        let settings = new PopupMenu.PopupIconMenuItem(
            "Open config file", "document-edit-symbolic", imports.gi.St.IconType.SYMBOLIC);
        settings.connect("activate", () => this._openConfig());
        this.menu.addMenuItem(settings);
    },

    _onBrightnessChanged: function (value) {
        if (this._syncingSlider) return;   // we set it, don't echo it back
        // DDC/CI is slow — debounce so dragging the slider doesn't spam writes.
        let percent = Math.round(value * 100);
        if (this._brightnessDebounce) {
            Mainloop.source_remove(this._brightnessDebounce);
        }
        this._brightnessDebounce = Mainloop.timeout_add(200, () => {
            this._brightnessDebounce = 0;
            this._runEngine("brightness set " + percent);
            return false;
        });
    },

    _refreshBrightness: function () {
        // Show what the monitors are actually at, rather than a hardcoded
        // guess — otherwise the first touch of the slider jumps them to it.
        // Read asynchronously: ddcutil takes a few hundred ms per monitor and
        // this runs on the compositor's thread.
        if (!this._brightnessSlider) return;
        this._runEngineAsync(["brightness", "get"], (stdout) => {
            if (stdout === null) return;
            let percent = this._firstPercent(stdout);
            if (percent === null) return;
            this._syncingSlider = true;
            try {
                this._brightnessSlider.setValue(percent / 100);
            } finally {
                this._syncingSlider = false;
            }
        });
    },

    _runEngineAsync: function (argv, callback) {
        // Runs the engine off the compositor thread and hands stdout back.
        // stdout is null when it couldn't run or exited non-zero; stderr comes
        // along so callers can report why. Never blocks the panel.
        if (!this._engineInstalled()) {
            callback(null, "engine not installed at " + ENGINE);
            return;
        }
        try {
            let proc = new Gio.Subprocess({
                argv: [ENGINE].concat(argv),
                flags: Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
            });
            proc.init(null);
            proc.communicate_utf8_async(null, null, (source, result) => {
                try {
                    let [, stdout, stderr] = source.communicate_utf8_finish(result);
                    callback(source.get_successful() ? stdout : null, stderr);
                } catch (e) {
                    global.logError("Lumendusk: '" + argv.join(" ") + "' failed: " + e);
                    callback(null, "" + e);
                }
            });
        } catch (e) {
            global.logError("Lumendusk: could not run the engine: " + e);
            callback(null, "" + e);
        }
    },

    _firstPercent: function (text) {
        // Engine prints one line per monitor: "  ddc1: 33%" (or "?%" on error).
        let match = /(\d+)%/.exec(text || "");
        return match ? parseInt(match[1], 10) : null;
    },

    _engineInstalled: function () {
        return GLib.file_test(ENGINE, GLib.FileTest.IS_EXECUTABLE);
    },

    _runEngine: function (args) {
        if (!this._engineInstalled()) {
            global.logError("Lumendusk: engine not found at " + ENGINE +
                            " — run install.sh from the repo.");
            return;
        }
        Util.spawnCommandLine(ENGINE + " " + args);
    },

    _readPaused: function () {
        // Read paused state straight from config.toml (cheap, no subprocess).
        try {
            let path = GLib.get_user_config_dir() + "/lumendusk/config.toml";
            let [ok, data] = GLib.file_get_contents(path);
            if (!ok) return false;
            let text = (data instanceof Uint8Array)
                ? imports.byteArray.toString(data)
                : ("" + data);
            return /paused\s*=\s*true/.test(text);
        } catch (e) {
            return false;
        }
    },

    _readDark: function () {
        // The Cinnamon shell theme name is the reliable "is it dark" signal.
        try {
            let s = new Gio.Settings({ schema_id: "org.cinnamon.theme" });
            return s.get_string("name").indexOf("-Dark") !== -1;
        } catch (e) {
            return false;
        }
    },

    _openConfig: function () {
        let path = GLib.get_user_config_dir() + "/lumendusk/config.toml";
        let open = () => Util.spawnCommandLine("xdg-open " + GLib.shell_quote(path));
        if (GLib.file_test(path, GLib.FileTest.EXISTS)) {
            open();
            return;
        }
        // First run: the engine writes the default config. Give it a moment
        // before handing the path to xdg-open, or we open nothing.
        this._runEngine("--once");
        Mainloop.timeout_add(700, () => { open(); return false; });
    },

    on_applet_clicked: function () {
        this.menu.toggle();
    },

    on_applet_removed_from_panel: function () {
        if (this._brightnessDebounce) {
            Mainloop.source_remove(this._brightnessDebounce);
            this._brightnessDebounce = 0;
        }
        // Drops the file monitor Cinnamon keeps on the settings file.
        if (this.settings) {
            this.settings.finalize();
            this.settings = null;
        }
    },
};

function main(metadata, orientation, panelHeight, instanceId) {
    return new LumenduskApplet(metadata, orientation, panelHeight, instanceId);
}
