"""Peripherals page (r092) — everything connected, on one page.

USB devices (from :func:`modules.sysfs.usb_devices`) as cards, plus the
sysfs sensor chips (temperatures, fans, CPU frequency, GPU) as info bars.
A Refresh button re-scans so freshly plugged hardware appears without a
restart. Missing attributes render "—" (r039 taxonomy); a machine with no
peripherals shows empty sections and works fine (universality mandate).

Boundary law: consumes sysfs module readers only; every toolkit call
through the compat seams. Bars are FIXED boxes (bounding-box policy §5b)
in the single accent color (r088 consistency rule).
"""

from ui.compat import Gtk, GLib, Pango, css, layout, charts

from pages.page_base import BasePage
from modules import sysfs

_ACCENT = (0x00 / 255.0, 0x78 / 255.0, 0xD7 / 255.0)
_TROUGH = (0x1b / 255.0, 0x1b / 255.0, 0x1b / 255.0)
_CARD_W, _CARD_H = 360, 118


def _escape(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _span(text, color):
    return "<span foreground='%s'>%s</span>" % (color, text)


def _dash(value):
    return value if value else "—"


class PeripheralsPage(BasePage):
    """Connected devices + sensor chips, with a manual refresh."""

    def build_content(self):
        self.add_title("Peripherals")
        self.add_markup_label(
            "<span foreground='#909090'>Everything connected — USB devices "
            "and hardware sensors. Plug something in, then press "
            "Refresh.</span>", wrap=True, spacing_after=6)

        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        refresh = Gtk.Button(label="Refresh")
        refresh.set_tooltip_text("Re-scan connected devices and sensors")
        css.add_css_class(refresh, "nav-button")
        refresh.connect("clicked", self._on_refresh)
        layout.box_add(tools, refresh, False, False, 0)
        layout.box_add(self, tools, False, False, 0)

        self._devices_title = self._section_label("Connected devices")
        self._devices_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                    spacing=10)
        self._devices_children = []
        layout.box_add(self, self._devices_box, False, False, 0)

        self._sensors_title = self._section_label("Sensors")
        self._sensors_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                    spacing=10)
        self._sensors_children = []
        layout.box_add(self, self._sensors_box, True, True, 0)

        self.refresh()

    def _reveal(self, widget):
        """Show a freshly rebuilt subtree. show_all() is gate-banned and the
        window's initial show_all only covered widgets existing at startup —
        rebuilt sections must show themselves, per widget (basics pattern)."""
        def walk(w):
            if hasattr(w, "forall"):
                w.forall(lambda c: walk(c))
            w.show()
        walk(widget)

    def _swap(self, box, tracked, builder):
        """Clear a tracked-children section, rebuild it, reveal it."""
        for child in tracked:
            layout.box_remove(box, child)
        tracked.clear()
        builder()
        self._reveal(box)

    # -- refresh ----------------------------------------------------------

    def _on_refresh(self, _button):
        # Re-scan off the click handler's hot path is unnecessary — sysfs
        # reads are cheap — but idle keeps the button responsive regardless.
        GLib.idle_add(self.refresh)

    def refresh(self):
        """Re-enumerate devices + sensors and rebuild the dynamic sections."""
        self._swap(self._devices_box, self._devices_children,
                   self._build_devices)
        self._swap(self._sensors_box, self._sensors_children,
                   self._build_sensors)
        return False

    # -- devices ----------------------------------------------------------

    def _build_devices(self):
        devices = sysfs.usb_devices()
        if not devices:
            note = self._note(
                "No USB devices detected — connect one and press Refresh.")
            layout.box_add(self._devices_box, note, False, False, 0)
            self._devices_children.append(note)
            return
        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_max_children_per_line(3)
        flow.set_min_children_per_line(1)
        flow.set_homogeneous(True)
        flow.set_column_spacing(10)
        flow.set_row_spacing(10)
        for dev in devices:
            flow.insert(self._device_card(dev), -1)
        layout.box_add(self._devices_box, flow, False, False, 0)
        self._devices_children.append(flow)

    def _device_card(self, dev):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.set_size_request(_CARD_W, _CARD_H)
        css.add_css_class(card, "basics-card")   # same card language as Basics

        name = Gtk.Label()
        name.set_xalign(0)
        name.set_use_markup(True)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        badge = ("removable" if dev["removable"] == "removable"
                 else _dash(dev["removable"]))
        name.set_markup("%s%s" % (
            _escape(dev["name"]),
            "  " + _span(_escape(badge), "#888888")))
        layout.box_add(card, name, False, False, 0)

        def row(label, value):
            lbl = Gtk.Label()
            lbl.set_xalign(0)
            lbl.set_use_markup(True)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_markup("%s: %s" % (
                _span(_escape(label), "#888888"), _escape(_dash(value))))
            layout.box_add(card, lbl, False, False, 0)

        ids = "—"
        if dev["vendor_id"] and dev["product_id"]:
            ids = "%s:%s" % (dev["vendor_id"], dev["product_id"])
        row("Manufacturer", dev["manufacturer"])
        row("USB ID", ids)
        where = "bus %s · port %s" % (_dash(dev["bus"]), _dash(dev["port"]))
        if dev["speed_mbps"] is not None:
            where += " · %s Mbps" % dev["speed_mbps"]
        row("Location", where)
        return card

    # -- sensors ----------------------------------------------------------

    def _section_label(self, text):
        label = Gtk.Label(label=text)
        label.set_xalign(0)
        css.add_css_class(label, "basics-contrib-title")
        layout.box_add(self, label, False, False, 0)
        return label

    def _note(self, text):
        label = Gtk.Label()
        label.set_xalign(0)
        label.set_line_wrap(True)
        label.set_markup(_span(_escape(text), "#888888"))
        return label

    def _build_sensors(self):
        chips = Gtk.FlowBox()  # noqa: keep FlowBox for the grid layout
        chips.set_selection_mode(Gtk.SelectionMode.NONE)
        chips.set_max_children_per_line(4)
        chips.set_min_children_per_line(1)
        chips.set_homogeneous(True)
        chips.set_column_spacing(10)
        chips.set_row_spacing(10)

        made = []

        def chip(label, value_text, fill=None):
            child = self._sensor_chip(label, value_text, fill)
            chips.insert(child, -1)
            made.append(child)

        for temp in sysfs.read_temperatures():
            celsius = temp["celsius"]
            fill = None if celsius is None else min(
                1.0, max(0.0, celsius / 100.0))
            chip(temp["label"],
                 "%s °C" % _dash(None if celsius is None
                                 else "%.1f" % celsius), fill)
        for fan in sysfs.read_fans():
            chip(fan["label"], "%s RPM" % _dash(fan["rpm"]))
        freq = sysfs.read_cpu_freq()
        if freq is not None:
            chip("CPU frequency", "%.2f–%.2f GHz · avg %.2f" % (
                freq["min"] / 1000.0, freq["max"] / 1000.0,
                freq["avg"] / 1000.0))
        # read_gpu_busy returns the first card's integer percent (or None).
        gpu = sysfs.read_gpu_busy()
        if gpu is not None:
            chip("GPU busy (amdgpu)", "%.0f%%" % gpu, gpu / 100.0)

        if not made:
            note = self._note(
                "No sensors found on this machine — that is normal on VMs.")
            chips.insert(note, -1)
            made.append(note)
        self._sensors_children.append(chips)

    def _sensor_chip(self, label, value_text, fill):
        """Fixed-size sensor chip: label, value, one accent mini-bar (§5b)."""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.set_size_request(220, 84)
        css.add_css_class(card, "basics-card")

        head = Gtk.Label()
        head.set_xalign(0)
        head.set_use_markup(True)
        head.set_ellipsize(Pango.EllipsizeMode.END)
        head.set_markup("%s  %s" % (
            _span(_escape(label), "#9a9a9a"),
            _escape(value_text)))
        layout.box_add(card, head, False, False, 0)

        bar = charts.ChartArea(
            draw_func=lambda cr, w, h, f=fill: self._draw_bar(cr, w, h, f))
        bar.set_size_request(-1, 8)
        bar.set_hexpand(True)
        layout.box_add(card, bar, False, False, 0)
        return card

    @staticmethod
    def _draw_bar(cr, width, height, fill):
        cr.set_source_rgb(*_TROUGH)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        if not fill:
            return
        cr.set_source_rgb(*_ACCENT)
        cr.rectangle(0, 0, max(0.0, min(1.0, fill)) * width, height)
        cr.fill()
