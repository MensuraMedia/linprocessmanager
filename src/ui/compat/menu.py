"""Model-driven menus (upgrade-architecture.md §3, seam 2; gtk4-port.md §4.2).

Every menu in the app is a ``Gio.Menu`` model shown through a popover; the
``Gio.Menu`` model ports cleanly, but the popover wiring does NOT:

- GTK3 : ``Gtk.Popover`` + ``popover.bind_model(model, ...)``
- GTK4 : ``Gtk.PopoverMenu.new_from_model(model)``

``Gtk.Menu``/``Gtk.MenuItem`` are forbidden by the gate — menus are model +
adapter from day one, so the port is zero-work. No menus exist yet (this task
stands the seam up); menu *contents* are out of scope.
"""

from .gtk_env import Gtk, GTK_MAJOR


def model_popover(menu_model, relative_to=None):
    """Build a popover showing ``menu_model`` (a ``Gio.Menu``).

    Returns a ``Gtk.Popover`` (GTK3) or ``Gtk.PopoverMenu`` (GTK4); both expose
    ``popup()``/``set_parent()`` so callers stay version-blind.
    """
    if GTK_MAJOR >= 4:
        popover = Gtk.PopoverMenu.new_from_model(menu_model)
        if relative_to is not None:
            popover.set_parent(relative_to)
    else:
        popover = Gtk.Popover()
        popover.bind_model(menu_model, None)
        if relative_to is not None:
            popover.set_relative_to(relative_to)
    return popover
