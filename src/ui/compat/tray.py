#!/usr/bin/env python3
"""System-tray / pane icon for linprocman (r072).

Tries, in order (Mint-first, all optional — none is a hard dependency):
  1. XApp.StatusIcon          (gir1.2-xapp-1.0 — native on Mint/Cinnamon/MATE/XFCE)
  2. AyatanaAppIndicator3     (gir1.2-ayatanaappindicator3-1 — Ubuntu/Debian panel SNI)
  3. Gtk.StatusIcon           (legacy GTK3; works on X11, deprecated upstream)
If none is importable, the tray is simply absent and the window keeps its
icon (ALT+Tab / taskbar) — logged, never fatal. Online mandates: the icon
is a local PNG; no dbus activation beyond the session bus the desktop
already provides.
"""

import os

from .gtk_env import load_repository
from . import Gtk
from log import get_logger

log = get_logger("tray")

# r082: the brand raster path is owned by ui.branding and passed in by
# main — this seam no longer hardcodes resource locations.
ICON_NAME = "linprocman"


def _try_xapp(on_activate, on_quit, icon_path=None):
    XApp = load_repository("XApp", "1.0")
    # r092: probe the capability BEFORE construction. This XApp binding
    # lacks StatusIcon.set_title; the old path constructed the icon (which
    # registers DBus object-manager callbacks inside libxapp), aborted on
    # the AttributeError, and the in-flight callback later hit freed memory
    # — a SEGV in g_dbus_object_manager_server_set_connection ~1s after
    # launch (journal 22:07). Fail fast with NO object created.
    if not hasattr(XApp.StatusIcon, "set_title"):
        raise AttributeError(
            "XApp.StatusIcon lacks set_title — failing fast before "
            "DBus registration")
    icon = XApp.StatusIcon()
    icon.set_icon_name(ICON_NAME)
    icon.set_title("linprocman")
    icon.set_tooltip_text("linprocman — process manager")
    # XApp: primary activation = toggle; secondary menu via Gtk.Menu
    icon.connect("activate", lambda _i: on_activate())

    def _menu(_icon, _x, _y, _kt):
        menu = Gtk.Menu()
        item_show = Gtk.MenuItem(label="Show / Hide")
        item_show.connect("activate", lambda _i: on_activate())
        menu.append(item_show)
        item_quit = Gtk.MenuItem(label="Quit")
        item_quit.connect("activate", lambda _i: on_quit())
        menu.append(item_quit)
        for child in menu.get_children():
            child.show()
        menu.popup_at_pointer(None)

    icon.connect("button-press-event",
                 lambda _i, x, y, b: _menu(_i, x, y, b) if b == 3 else None)
    return icon, "xapp"


def _try_indicator(on_activate, on_quit, icon_path=None):
    AppIndicator = load_repository("AyatanaAppIndicator3", "0.1")
    icon = AppIndicator.Indicator.new(
        "linprocman", ICON_NAME, AppIndicator.IndicatorCategory.APPLICATION_STATUS)
    icon.set_status(AppIndicator.IndicatorStatus.ACTIVE)
    # r082: an explicit brand raster wins over the theme-name lookup
    if icon_path:
        icon.set_icon_full(icon_path, "linprocman")
    menu = Gtk.Menu()
    item_show = Gtk.MenuItem(label="Show / Hide")
    item_show.connect("activate", lambda _i: on_activate())
    menu.append(item_show)
    item_quit = Gtk.MenuItem(label="Quit")
    item_quit.connect("activate", lambda _i: on_quit())
    menu.append(item_quit)
    for child in menu.get_children():
        child.show()
    icon.set_menu(menu)
    return icon, "ayatana"


def _try_statusicon(on_activate, on_quit, icon_path=None):
    icon = Gtk.StatusIcon.new_from_file(icon_path)
    icon.set_tooltip_text("linprocman — process manager")
    icon.connect("activate", lambda _i: on_activate())  # left click
    menu = Gtk.Menu()
    item_show = Gtk.MenuItem(label="Show / Hide")
    item_show.connect("activate", lambda _i: on_activate())
    menu.append(item_show)
    item_quit = Gtk.MenuItem(label="Quit")
    item_quit.connect("activate", lambda _i: on_quit())
    menu.append(item_quit)
    for child in menu.get_children():
        child.show()
    icon.connect("popup-menu",
                 lambda _i, _btn, _t: menu.popup_at_pointer(None))
    return icon, "gtk-statusicon"


def create(on_toggle, on_quit, icon_path=None):
    """Build the tray icon via the first available backend.

    on_toggle: called on left-click/Show-Hide (bring the window back).
    on_quit:   called for the tray Quit item.
    icon_path: brand raster (r082) — passed in by main from ui.branding;
               XApp keeps the theme-name lookup so panel scaling stays crisp.
    Returns (backend_name, icon) or (None, None) when unsupported.
    """
    last_error = None
    for builder in (_try_xapp, _try_indicator, _try_statusicon):
        try:
            icon, backend = builder(on_toggle, on_quit, icon_path=icon_path)
            log.info("tray icon active via %s", backend)
            return backend, icon
        except Exception as e:  # noqa: BLE001 — optional backends only
            last_error = e
            log.info("tray backend unavailable: %s", e)
    log.warning("no tray backend available — pane icon disabled "
                "(install gir1.2-xapp-1.0 on Mint for the tray icon)")
    return None, None
