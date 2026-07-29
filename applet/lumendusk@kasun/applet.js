/*
 * Lumendusk — Cinnamon panel applet.
 *
 * This is a thin JS shell for the panel: an icon + dropdown menu. The actual
 * work (deciding day/night, switching theme, night light, brightness) is done
 * by the Python engine, which this applet calls via `python3 -m lumendusk ...`.
 *
 * Phase-1 scaffold: menu wired to the engine's CLI. Persistent settings
 * (location, times, theme names) live in ~/.config/lumendusk/config.toml; the
 * "Open config file" item opens it for now, and a proper settings panel comes
 * with Brightness Step B2.
 */

const Applet = imports.ui.applet;
const PopupMenu = imports.ui.popupMenu;
const Util = imports.misc.util;
const GLib = imports.gi.GLib;
const Gio = imports.gi.Gio;
const Mainloop = imports.mainloop;

// The engine runs from its own venv (created by install.sh), so we don't touch
// the system Python. Absolute path keeps it working regardless of the panel's PATH.
const ENGINE = GLib.get_home_dir() + "/.local/share/lumendusk/venv/bin/lumendusk";

function LumenduskApplet(orientation, panelHeight, instanceId) {
    this._init(orientation, panelHeight, instanceId);
}

LumenduskApplet.prototype = {
    __proto__: Applet.IconApplet.prototype,

    _init: function (orientation, panelHeight, instanceId) {
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
        if (!this._brightnessSlider || !this._engineInstalled()) return;
        try {
            let proc = new Gio.Subprocess({
                argv: [ENGINE, "brightness", "get"],
                flags: Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
            });
            proc.init(null);
            proc.communicate_utf8_async(null, null, (source, result) => {
                try {
                    let [, stdout] = source.communicate_utf8_finish(result);
                    let percent = this._firstPercent(stdout);
                    if (percent === null) return;
                    this._syncingSlider = true;
                    this._brightnessSlider.setValue(percent / 100);
                    this._syncingSlider = false;
                } catch (e) {
                    global.logError("Lumendusk: brightness read failed: " + e);
                    this._syncingSlider = false;
                }
            });
        } catch (e) {
            global.logError("Lumendusk: could not run the engine: " + e);
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
    },
};

function main(metadata, orientation, panelHeight, instanceId) {
    return new LumenduskApplet(orientation, panelHeight, instanceId);
}
