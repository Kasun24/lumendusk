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

        // Refresh the pause switch each time the menu opens, in case it was
        // changed from the CLI or another instance.
        this.menu.connect("open-state-changed", (menu, open) => {
            if (open && this._pauseSwitch) {
                this._pauseSwitch.setToggleState(this._readPaused());
            }
        });

        this._brightnessDebounce = 0;
        this._buildMenu();
    },

    _buildMenu: function () {
        this.menu.removeAll();

        let title = new PopupMenu.PopupMenuItem("Lumendusk", { reactive: false });
        this.menu.addMenuItem(title);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Pause automation (e.g. while watching a movie): turns night light off
        // for true colors and freezes theme + brightness until switched back on.
        this._pauseSwitch = new PopupMenu.PopupSwitchMenuItem(
            "Pause automation", this._readPaused());
        this._pauseSwitch.connect("toggled", (item, value) =>
            this._runEngine(value ? "pause" : "resume"));
        this.menu.addMenuItem(this._pauseSwitch);
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

    _runEngine: function (args) {
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

    _openConfig: function () {
        let path = GLib.get_user_config_dir() + "/lumendusk/config.toml";
        // Ensure it exists (the engine creates defaults on first run), then open.
        Util.spawnCommandLine(ENGINE + " --once");
        Util.spawnCommandLine("xdg-open " + GLib.shell_quote(path));
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
