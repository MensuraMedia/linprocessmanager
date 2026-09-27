"""
Branding — one mark, every placement (r082).

The brand mark lives in resources/images/. ``list-checks.svg`` is the
vector source (copied from the ~/projects/assets/icons master — assets are
copied in, never referenced); ``logo.png`` (accent glyph on transparent)
and the ``icon-{size}.png`` set (blue tile + white glyph) are the
checked-in rasters rendered from it by s017. Every placement consumes this
module, so switching the brand means: replace the SVG, re-run s017,
reinstall, restart — no placement code changes.

Placements and what each consumes:

| placement          | runtime? | consumes                          |
|--------------------|----------|-----------------------------------|
| sidebar logo       | yes      | logo_pixbuf(size)                 |
| window / ALT+Tab   | yes      | set_window_icon(win)              |
| tray / pane icon   | yes      | tray_icon_path() (passed in by main) |
| program-menu entry | install  | icon_path(size) set → hicolor     |

Rules: PNG candidates always work (librsvg is optional on the Debian
family; the SVG candidate only renders where the pixbuf loader exists).
Rescale-only at install time. No network, no pip — GdkPixbuf via the
compat seam.
"""

import os

from ui.compat import GdkPixbuf

_IMAGES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "..", "resources", "images")

ICON_SIZES = (16, 32, 48, 64, 128, 512)
TRAY_ICON_SIZE = 128
MENU_ICON_NAME = "linprocman"        # .desktop Icon= (resolves hicolor)

_cache = {}


def _path(name):
    return os.path.join(_IMAGES, name)


def icon_path(size):
    """Checked-in raster for a size (install.sh copies these to hicolor)."""
    return _path("icon-%d.png" % size)


def tray_icon_path():
    return icon_path(TRAY_ICON_SIZE)


def logo_png_path():
    return _path("logo.png")


def logo_svg_path():
    return _path("logo.svg")


def pixbuf_for(path, size):
    """Cached square pixbuf for a brand raster; None when missing/invalid."""
    key = (path, size)
    if key not in _cache:
        if not os.path.exists(path):
            _cache[key] = None
        else:
            try:
                _cache[key] = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    path, size, size, True)
            except Exception:
                _cache[key] = None
    return _cache[key]


def logo_pixbuf(size):
    """Sidebar mark: accent raster first, accent SVG as the loader fallback."""
    return pixbuf_for(logo_png_path(), size) or pixbuf_for(logo_svg_path(),
                                                           size)


def set_window_icon(window, size=TRAY_ICON_SIZE):
    """ALT+Tab / taskbar icon (the pixbuf lands in _NET_WM_ICON)."""
    from ui.compat import Gtk
    pb = pixbuf_for(icon_path(size), size)
    if pb is None:
        return False
    Gtk.Window.set_default_icon(pb)
    window.set_icon(pb)
    return True
