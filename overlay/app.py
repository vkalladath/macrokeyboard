"""Transparent, scroll-driven overlay menu driven by the macro pad knob.

Run:      python3 -m overlay.app
Preview:  python3 -m overlay.app --preview     (opens immediately; arrow keys
                                                and Enter also work)
"""

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import audio, menus  # noqa: E402
from .pad import PadReader  # noqa: E402

IDLE_CLOSE_SECONDS = 12


class Overlay(Gtk.Application):
    def __init__(self, preview=False):
        super().__init__(application_id="io.github.vkalladath.macropadmenu")
        self.preview = preview
        self.stack = []
        self.index = 0
        self._idle_id = 0
        self._rows = []
        self.window = None
        self.reader = None

    # ---- setup ---------------------------------------------------------

    def do_activate(self):
        self._build()
        self._load_css()

        self.reader = PadReader(self._on_encoder)
        nodes = self.reader.start()
        if nodes:
            print(f"pad: reading {', '.join(nodes)}", file=sys.stderr)
        else:
            print("warning: no pad found — arrow keys + Enter still work",
                  file=sys.stderr)

        if self.preview:
            self.open_menu()

    def _build(self):
        win = Gtk.ApplicationWindow(application=self)
        win.set_decorated(False)
        win.set_resizable(False)
        win.set_title("Macro pad menu")
        win.add_css_class("overlay")
        win.set_default_size(340, -1)

        # Margins leave the window itself fully transparent around the panel.
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        panel.add_css_class("panel")
        panel.set_margin_top(10)
        panel.set_margin_bottom(10)
        panel.set_margin_start(10)
        panel.set_margin_end(10)

        self.title_label = Gtk.Label(xalign=0)
        self.title_label.add_css_class("title")
        panel.append(self.title_label)

        self.items_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        panel.append(self.items_box)

        self.status_label = Gtk.Label(xalign=0)
        self.status_label.add_css_class("status")
        self.status_label.set_wrap(True)
        self.status_label.set_max_width_chars(34)
        panel.append(self.status_label)

        hint = Gtk.Label(label="scroll  ·  click", xalign=0)
        hint.add_css_class("hint")
        panel.append(hint)

        win.set_child(panel)

        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_key)
        win.add_controller(controller)

        self.hold()  # keep the process alive while the window is hidden
        self.window = win

    def _load_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_path(str(Path(__file__).with_name("style.css")))
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    # ---- rendering -----------------------------------------------------

    def _visible(self):
        return bool(self.window) and self.window.get_visible()

    def _render(self):
        if not self.stack:
            return
        items = menus.items_for(self.stack[-1])
        self.index = min(self.index, len(items) - 1)

        for row in self._rows:
            self.items_box.remove(row)
        self._rows = []

        for position, item in enumerate(items):
            row = Gtk.Label(label=item.label, xalign=0)
            row.add_css_class("item")
            if position == self.index:
                row.add_css_class("selected")
            self.items_box.append(row)
            self._rows.append(row)

        self.title_label.set_label(menus.title_for(self.stack[-1]).upper())
        self.status_label.set_label(audio.status_line())

    # ---- menu state ----------------------------------------------------

    def open_menu(self):
        self.stack = ["main"]
        self.index = 0
        self.window.present()
        self._render()
        self._reset_idle()

    def close_menu(self):
        self._cancel_idle()
        self.stack = []
        self.index = 0
        if self.window:
            self.window.set_visible(False)

    def _move(self, delta):
        if not self.stack:
            return
        count = len(menus.items_for(self.stack[-1]))
        if count:
            self.index = (self.index + delta) % count
            self._render()

    def _back(self):
        if len(self.stack) > 1:
            self.stack.pop()
            self.index = 0
            self._render()

    def _select(self):
        if not self.stack:
            return
        item = menus.items_for(self.stack[-1])[self.index]

        if item.close:
            self.close_menu()
        elif item.back:
            self._back()
        elif item.submenu:
            self.stack.append(item.submenu)
            self.index = 0
            self._render()
        elif item.action:
            try:
                item.action()
            except Exception as error:  # keep the overlay alive on failure
                print(f"action failed: {error}", file=sys.stderr)
            if item.keep_open:
                self._render()
            else:
                self.close_menu()

    # ---- idle auto-dismiss ---------------------------------------------

    def _reset_idle(self):
        self._cancel_idle()
        if not self.preview:
            self._idle_id = GLib.timeout_add_seconds(IDLE_CLOSE_SECONDS, self._on_idle)

    def _cancel_idle(self):
        if self._idle_id:
            GLib.source_remove(self._idle_id)
            self._idle_id = 0

    def _on_idle(self):
        self._idle_id = 0
        self.close_menu()
        return False

    # ---- input ---------------------------------------------------------

    def _on_encoder(self, action):
        if self._visible():
            self._reset_idle()
            if action == "cw":
                self._move(+1)
            elif action == "ccw":
                self._move(-1)
            else:
                self._select()
            return

        # Menu closed: the knob behaves as a plain volume knob again.
        try:
            if action == "press":
                self.open_menu()
            elif action == "cw":
                audio.volume_step(+1)
            elif action == "ccw":
                audio.volume_step(-1)
        except Exception as error:
            print(f"volume failed: {error}", file=sys.stderr)

    def _on_key(self, _controller, keyval, _keycode, _state):
        """Arrow keys + Enter, so the menu can be tested without the pad."""
        if keyval == Gdk.KEY_Escape:
            self.close_menu()
            return True
        if not self._visible():
            return False
        if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            self._move(+1)
        elif keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            self._move(-1)
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self._select()
        else:
            return False
        self._reset_idle()
        return True


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    app = Overlay(preview="--preview" in argv)
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
