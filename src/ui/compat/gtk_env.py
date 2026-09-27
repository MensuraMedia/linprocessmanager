"""The single toolkit-binding entry point (upgrade-architecture.md §3).

This is the ONLY module in the codebase that calls ``gi.require_version`` and
the ONLY module that issues ``from gi.repository import ...``. Everything else
under ``src/ui/`` and ``src/pages/`` (and ``src/main.py``) imports its toolkit
symbols from the ``compat`` package, never from ``gi`` directly — so the whole
tree is version-blind and the 3→4 port is a one-file flip here (§2 import law,
gate-enforced by ``tests/test_gates.py``).

The port flips ``Gtk`` AND ``Gdk`` together ("3.0" ↔ "4.0" — they are coupled);
``GdkPixbuf`` stays "2.0"; ``GLib``/``Gio``/``GObject`` take no version. That
single edit is the entire binding delta of the major port.

Capability flags (``HAS_*``) follow debian-compatibility.md §2: UI code asks a
named flag, never a raw version number, so ≥4.10 conveniences (AlertDialog)
sit behind a probe instead of a bare call.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gio, GObject, Pango  # noqa: E402

# ---------------------------------------------------------------------------
# Version identity — the one place the running toolkit is interrogated.
# ---------------------------------------------------------------------------

GTK_MAJOR = Gtk.get_major_version()
GTK_MINOR = Gtk.get_minor_version()
GTK_MICRO = Gtk.get_micro_version()


def compute_capability_flags(major, minor):
    """Derive the ``HAS_*`` capability map from a (major, minor) pair.

    Pure integer logic — no toolkit objects — so the selection rules are unit
    testable for both GTK3 and GTK4 on any interpreter (see
    upgrade-architecture.md §3: a process holds one Gtk version, but the
    branch-selection logic of both paths is exercised every run).
    """
    return {
        # Gtk.AlertDialog is GTK4-only and lands at 4.10 — confirm dialogs
        # probe this flag before using it, else fall back to the plain-window
        # pattern (dialogs.py).
        "HAS_ALERT_DIALOG": (major, minor) >= (4, 10),
        # Click gesture is GestureMultiPress on GTK3, renamed GestureClick on
        # GTK4 (events.py switches on this).
        "HAS_GESTURE_CLICK": major >= 4,
        # Renderers take Gdk.Texture on GTK4; Gtk.Image.new_from_pixbuf is the
        # GTK3 path (icons.py).
        "HAS_TEXTURE": major >= 4,
        # CSS provider registration is per-display on GTK4, per-screen on GTK3
        # (css.py).
        "HAS_DISPLAY_PROVIDER": major >= 4,
    }


_FLAGS = compute_capability_flags(GTK_MAJOR, GTK_MINOR)

HAS_ALERT_DIALOG = _FLAGS["HAS_ALERT_DIALOG"]
HAS_GESTURE_CLICK = _FLAGS["HAS_GESTURE_CLICK"]
HAS_TEXTURE = _FLAGS["HAS_TEXTURE"]
HAS_DISPLAY_PROVIDER = _FLAGS["HAS_DISPLAY_PROVIDER"]


__all__ = [
    "Gtk", "Gdk", "GdkPixbuf", "GLib", "Gio", "GObject",
    "GTK_MAJOR", "GTK_MINOR", "GTK_MICRO",
    "compute_capability_flags",
    "HAS_ALERT_DIALOG", "HAS_GESTURE_CLICK", "HAS_TEXTURE",
    "HAS_DISPLAY_PROVIDER",
]


def load_repository(name, version=None):
    """Import an OPTIONAL gi repository inside the compat seam (r072: tray
    backends). Only this module may touch gi — the raw-import ban holds."""
    if version:
        gi = __import__("gi")
        gi.require_version(name, version)
    module = __import__(f"gi.repository.{name}", fromlist=[name])
    return module
