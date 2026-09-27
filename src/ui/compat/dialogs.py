"""Confirm / entry windows + close semantics (upgrade-architecture.md §3,
seam 6; gtk4-port.md §4.6).

kill / renice / signal confirmations are plain ``Gtk.Window`` with a header bar
and an action row — a pattern that works identically on both toolkits — rather
than ``Gtk.Dialog``/``MessageDialog`` (both banned by the gate). ``AlertDialog``
is a GTK4≥4.10 convenience gated behind ``HAS_ALERT_DIALOG``; this task ships
only the portable plain-window path.

This is the ONLY module allowed to call ``.destroy()`` (the gate bans it
elsewhere) — and even here the rule is ``close()`` only, so dismissal never
tears the widget down out from under a signal handler.
"""

from .gtk_env import Gtk, Gdk, GTK_MAJOR
from . import layout

from log import get_logger
log = get_logger("dialogs")


def confirm_window(parent, title, message, on_confirm,
                   confirm_label="Confirm", cancel_label="Cancel"):
    """Build a modal confirm window (plain-window pattern, both toolkits).

    ``on_confirm`` is invoked with no arguments when the confirm button is
    clicked; the window is closed afterward. Returns the window; the caller
    calls ``present()`` (or the returned window is shown by the caller).
    """
    window = Gtk.Window()
    window.set_title(title)
    window.set_modal(True)
    if parent is not None:
        window.set_transient_for(parent)
    # r065 hang fix: a modal window that maps BEHIND the active window still
    # holds a grab — the app looks hung (nothing is clickable) while the
    # dialog is invisible. DIALOG type-hint + center-on-parent makes the WM
    # map it on top and focused (GTK3 spelling; GTK4 WMs center transients).
    if GTK_MAJOR == 3:
        window.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        window.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)

    header = Gtk.HeaderBar()
    # HeaderBar title spelling differs; the portable subset is set_title_widget
    # on GTK4 vs set_title on GTK3 — kept minimal here (title lives on window).
    window.set_titlebar(header)

    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    content.set_margin_top(16)
    content.set_margin_bottom(16)
    content.set_margin_start(16)
    content.set_margin_end(16)

    label = Gtk.Label(label=message)
    label.set_xalign(0)
    layout.box_add(content, label, expand=True, fill=True, padding=0)

    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    actions.set_halign(Gtk.Align.END)

    cancel = Gtk.Button(label=cancel_label)
    cancel.connect("clicked", lambda _btn: close(window))
    layout.box_add(actions, cancel, expand=False, fill=False, padding=0)

    confirm = Gtk.Button(label=confirm_label)

    def _on_confirm(_btn):
        on_confirm()
        close(window)

    confirm.connect("clicked", _on_confirm)
    window.connect("map", lambda _w: log.info("confirm dialog mapped: %s", title))
    window.connect("unmap", lambda _w: log.info("confirm dialog closed: %s", title))
    layout.box_add(actions, confirm, expand=False, fill=False, padding=0)

    layout.box_add(content, actions, expand=False, fill=False, padding=0)
    layout.set_child(window, content)
    return window


def close(window):
    """Dismiss a window — ``close()`` only, never ``destroy()`` (GTK4 has no
    ``Gtk.Window.destroy``; the reference is dropped by the caller)."""
    window.close()
