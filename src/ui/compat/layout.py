"""Box pack semantics + child-add (upgrade-architecture.md §3, seam 4).

Owns exactly one toolkit difference: how a child is placed in a container.

- ``box_add``   : GTK3 ``box.pack_start(child, expand, fill, padding)``
                  ↔ GTK4 ``box.append(child)`` + expand/align properties.
- ``set_child`` : GTK3 ``container.add(child)``
                  ↔ GTK4 ``container.set_child(child)`` (Window, ScrolledWindow,
                  Frame, Viewport, Button…).
- ``box_remove``: GTK3 ``box.remove(child)`` ↔ GTK4 ``box.remove(child)``
                  (same spelling; kept here so no UI file calls it raw).

This is the ONLY module allowed to call ``pack_start``/``pack_end`` or the bare
``container.add(...)`` (the gate bans them everywhere else). The GTK4 spellings
(``append``/``set_child``) are not banned, so they may appear anywhere — but
routing every add through here keeps the flip point singular.
"""

from .gtk_env import Gtk, GTK_MAJOR


def box_add(box, child, expand=False, fill=False, padding=0):
    """Append ``child`` to a ``Gtk.Box`` with GTK3 pack semantics preserved.

    On GTK4 ``fill`` is folded into the child's align (FILL vs START) and
    ``expand`` into hexpand/vexpand along the box's orientation; ``padding``
    maps to a leading margin on the box's main axis.
    """
    if GTK_MAJOR >= 4:
        box.append(child)
        horizontal = box.get_orientation() == Gtk.Orientation.HORIZONTAL
        if expand:
            if horizontal:
                child.set_hexpand(True)
            else:
                child.set_vexpand(True)
        if fill:
            align = Gtk.Align.FILL
        else:
            align = Gtk.Align.START
        if horizontal:
            child.set_valign(Gtk.Align.FILL)
            child.set_halign(align if expand else Gtk.Align.START)
        else:
            child.set_halign(Gtk.Align.FILL)
            child.set_valign(align if expand else Gtk.Align.START)
        if padding:
            if horizontal:
                child.set_margin_start(padding)
                child.set_margin_end(padding)
            else:
                child.set_margin_top(padding)
                child.set_margin_bottom(padding)
    else:
        box.pack_start(child, expand, fill, padding)


def set_child(container, child):
    """Set the single child of a bin-style container."""
    if GTK_MAJOR >= 4:
        container.set_child(child)
    else:
        container.add(child)


def box_remove(box, child):
    """Remove ``child`` from ``box`` (identical spelling on both toolkits)."""
    box.remove(child)
