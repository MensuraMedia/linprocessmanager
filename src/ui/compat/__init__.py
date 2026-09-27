"""``src/ui/compat`` — the toolkit compatibility layer (upgrade-architecture.md
§3). One file per seam; ALL GTK version knowledge lives here.

UI and app code imports toolkit symbols and adapters from this package only —
``from ui.compat import Gtk, Gdk, GObject`` and ``from ui.compat import layout,
events, css`` — never from ``gi.repository`` (gate-enforced). The single flip
point of the GTK3→4 port is ``gtk_env.py``.
"""

from .gtk_env import (
    Gtk, Gdk, GdkPixbuf, GLib, Gio, GObject, Pango,
    GTK_MAJOR, GTK_MINOR, GTK_MICRO,
    compute_capability_flags,
    HAS_ALERT_DIALOG, HAS_GESTURE_CLICK, HAS_TEXTURE, HAS_DISPLAY_PROVIDER,
)

from . import layout, menu, events, dialogs, charts, icons, css

__all__ = [
    # re-exported toolkit symbols
    "Gtk", "Gdk", "GdkPixbuf", "GLib", "Gio", "GObject", "Pango",
    # version identity + capability flags
    "GTK_MAJOR", "GTK_MINOR", "GTK_MICRO", "compute_capability_flags",
    "HAS_ALERT_DIALOG", "HAS_GESTURE_CLICK", "HAS_TEXTURE",
    "HAS_DISPLAY_PROVIDER",
    # seam adapters
    "layout", "menu", "events", "dialogs", "charts", "icons", "css",
]
