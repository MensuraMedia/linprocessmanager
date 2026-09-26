"""Cairo draw hookup for chart/custom-drawn widgets (upgrade-architecture.md
§3, seam 5; gtk4-port.md §4.5).

Cairo drawing is toolkit-agnostic; only the callback hookup differs:

- GTK3 : ``drawing_area.connect("draw", cb)`` — ``cb(widget, cr)``.
- GTK4 : ``drawing_area.set_draw_func(cb)`` — ``cb(area, cr, width, height)``.

``ChartArea`` is the ONLY place allowed to connect the ``draw`` signal (the
gate bans that connection elsewhere). It normalizes both paths to a single
draw callback ``cb(area, cr, width, height)`` so chart code talks only to the
adapter + a cairo context. Chart *implementations* (ring buffers, axes) are out
of scope — this is the hookup adapter only.
"""

from .gtk_env import Gtk, GTK_MAJOR


class ChartArea(Gtk.DrawingArea):
    """A ``Gtk.DrawingArea`` whose draw callback is version-normalized.

    Pass ``draw_func=cb`` or call ``set_draw_callback(cb)`` later. ``cb`` is
    always invoked as ``cb(area, cr, width, height)`` on both toolkits.
    """

    def __init__(self, draw_func=None):
        super().__init__()
        self._draw_func = None
        self._gtk3_handler_id = None
        if draw_func is not None:
            self.set_draw_callback(draw_func)

    def set_draw_callback(self, draw_func):
        """Register the normalized draw callback, wiring the version path."""
        self._draw_func = draw_func
        if GTK_MAJOR >= 4:
            self.set_draw_func(self._on_draw_gtk4)
        else:
            if self._gtk3_handler_id is None:
                self._gtk3_handler_id = self.connect("draw", self._on_draw_gtk3)

    def _on_draw_gtk3(self, widget, cr):
        allocation = widget.get_allocation()
        if self._draw_func is not None:
            self._draw_func(widget, cr, allocation.width, allocation.height)
        return False

    def _on_draw_gtk4(self, area, cr, width, height):
        if self._draw_func is not None:
            self._draw_func(area, cr, width, height)
