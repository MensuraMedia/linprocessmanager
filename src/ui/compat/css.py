"""CSS provider registration + style-class helpers (upgrade-architecture.md §3,
seam 8; gtk4-port.md §4.8).

Two toolkit differences, one file:

- Provider registration:
  GTK3 ``Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), …)``
  ↔ GTK4 ``Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), …)``.
- Style-class spelling:
  GTK3 ``widget.get_style_context().add_class(name)``
  ↔ GTK4 ``widget.add_css_class(name)`` (and ``remove_css_class``).

Classes and state selectors only — no layout through CSS (the r034 lesson).
"""

from .gtk_env import Gtk, Gdk, GTK_MAJOR


DEFAULT_PRIORITY = Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION


def add_provider(provider, priority=DEFAULT_PRIORITY):
    """Register a ``Gtk.CssProvider`` app-wide for the default screen/display."""
    if GTK_MAJOR >= 4:
        display = Gdk.Display.get_default()
        Gtk.StyleContext.add_provider_for_display(display, provider, priority)
    else:
        screen = Gdk.Screen.get_default()
        Gtk.StyleContext.add_provider_for_screen(screen, provider, priority)


def add_css_class(widget, name):
    """Add a CSS class to ``widget`` (GTK4 spelling, GTK3 fallback)."""
    if GTK_MAJOR >= 4:
        widget.add_css_class(name)
    else:
        widget.get_style_context().add_class(name)


def remove_css_class(widget, name):
    """Remove a CSS class from ``widget`` (GTK4 spelling, GTK3 fallback)."""
    if GTK_MAJOR >= 4:
        widget.remove_css_class(name)
    else:
        widget.get_style_context().remove_class(name)
