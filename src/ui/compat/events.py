"""Click / key / motion controllers + accelerators (upgrade-architecture.md §3,
seam 3; gtk4-port.md §4.3).

Owns the input-plumbing differences:

- ``click_gesture`` : GTK3 ``Gtk.GestureMultiPress`` ↔ GTK4 ``Gtk.GestureClick``
  (a rename, not a shared name) — the reason no UI file may connect
  ``button-press-event`` directly (the gate bans that signal outside this file).
- ``key_controller`` / ``motion_controller`` : ``EventControllerKey`` /
  ``EventControllerMotion`` exist in BOTH toolkits; only the attach step
  differs (GTK3 constructs against the widget; GTK4 uses ``add_controller``).
- ``make_action`` / ``set_accels`` : accelerators via ``Gio.SimpleAction`` +
  ``set_accels_for_action`` — the portable seam (``ShortcutController`` is
  GTK4-only and is banned).

Adapters carry no feature logic: callbacks receive normalized arguments and the
caller decides what to do.
"""

from .gtk_env import Gtk, Gio, Gdk, GTK_MAJOR


def _attach(widget, controller):
    """Attach an event controller to ``widget`` (GTK4) — no-op on GTK3 where
    the controller is bound at construction."""
    if GTK_MAJOR >= 4:
        widget.add_controller(controller)


def click_gesture(widget, on_pressed, button=0, min_press=1):
    """Install a click gesture on ``widget``.

    ``min_press`` > 1 gates the callback to multi-clicks (r090: the
    Processes band gauges open Basics on DOUBLE-click). The gate lives here
    — the portable "pressed" signal already carries the running press count —
    because GtkGestureMultiPress.set_n_press is missing from some bindings.
    

    ``on_pressed`` is called ``on_pressed(gesture, n_press, x, y)`` — the
    "pressed" signal shape shared by both GestureMultiPress and GestureClick.
    Returns the gesture (the caller must keep a reference alive).
    """
    def _gated(gesture, n, x, y):
        if n >= min_press:
            on_pressed(gesture, n, x, y)

    if GTK_MAJOR >= 4:
        gesture = Gtk.GestureClick.new()
        if button:
            gesture.set_button(button)
        gesture.connect("pressed", _gated)
        _attach(widget, gesture)
    else:
        gesture = Gtk.GestureMultiPress.new(widget)
        if button:
            gesture.set_button(button)
        gesture.connect("pressed", _gated)
    return gesture




def key_controller(widget, on_key_pressed):
    """Install a key controller. ``on_key_pressed`` gets the shared
    ``(controller, keyval, keycode, state)`` signature of "key-pressed"."""
    if GTK_MAJOR >= 4:
        controller = Gtk.EventControllerKey.new()
        controller.connect("key-pressed", on_key_pressed)
        _attach(widget, controller)
    else:
        controller = Gtk.EventControllerKey.new(widget)
        controller.connect("key-pressed", on_key_pressed)
    return controller


def motion_controller(widget, on_motion):
    """Install a motion controller. ``on_motion`` gets the shared
    ``(controller, x, y)`` signature of "motion"."""
    if GTK_MAJOR >= 4:
        controller = Gtk.EventControllerMotion.new()
        controller.connect("motion", on_motion)
        _attach(widget, controller)
    else:
        controller = Gtk.EventControllerMotion.new(widget)
        controller.connect("motion", on_motion)
    return controller


def make_action(name, on_activate, parameter_type=None):
    """Create a ``Gio.SimpleAction`` wired to ``on_activate`` (same on both
    toolkits) — the portable accelerator target."""
    action = Gio.SimpleAction.new(name, parameter_type)
    action.connect("activate", on_activate)
    return action


def set_accels(app, detailed_action_name, accels):
    """Bind keyboard accelerators to an action (identical API on both
    toolkits). ``accels`` is a list like ``["<Primary>f"]``."""
    app.set_accels_for_action(detailed_action_name, accels)
