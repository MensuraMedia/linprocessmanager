"""Pixbuf → widget image (upgrade-architecture.md §3, seam 7; gtk4-port.md
§4.7).

The Pillow → GdkPixbuf tint pipeline is unchanged across the port; only the
final pixbuf → widget step differs:

- GTK3 : ``Gtk.Image.new_from_pixbuf(pixbuf)``
- GTK4 : ``Gtk.Image.new_from_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))``
  (renderers take ``Gdk.Texture``/``Paintable``; ``GdkPixbuf`` still loads).

One helper hides the difference so no UI file names the pixbuf→image call.
"""

from .gtk_env import Gtk, Gdk, GTK_MAJOR


def image_from_pixbuf(pixbuf):
    """Wrap a ``GdkPixbuf.Pixbuf`` in a ``Gtk.Image`` for the active toolkit."""
    if GTK_MAJOR >= 4:
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        return Gtk.Image.new_from_paintable(texture)
    return Gtk.Image.new_from_pixbuf(pixbuf)
