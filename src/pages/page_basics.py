"""Basics page — the read-only "am I OK?" system summary (Phase 4.5).

Spec: docs/modules/metric-band-basics.md §3. The calm, glanceable counterpart to
the Processes page: the same six gauges rendered large, each with a 5-minute
mini-sparkline and a persistent top-contributor list. No editing, no actions —
power features stay on Processes.

Boundary law: this page consumes snapshots only. It installs NO sampler drain of
its own — the Processes page owns the single GLib drain source (r046) and
forwards each snapshot here via :meth:`on_snapshot`. Rankings and gauge readings
come from the pure :mod:`modules.manager_rank` model; cairo drawing routes
through ``ui.compat.charts`` and every toolkit call through a compat seam.

Ring law (r059): the sparklines hold ``(ts, value)`` tuples, exclude
``from_backoff`` samples, and render time gaps as gaps — a hidden window must
never masquerade as continuous history. As of Phase 5 the sparklines read the
shared :mod:`modules.manager_history` rings (the interim per-metric deque is
gone); the same ``(ts, value)`` contract, now shared with the Graphs surfaces.
"""

from collections import deque

from ui.compat import Gtk, css, layout, charts

from pages.page_base import BasePage
from config.app_settings import AppSettings
from modules import manager_rank as mr

# Gauge order matches the Processes-page band (Variant 2).
_GAUGES = [
    ("cpu", "CPU"),
    ("memory", "Memory"),
    ("swap", "Swap"),
    ("disk", "Disk I/O"),
    ("network", "Network"),
    ("load", "Load"),
]

# ~5 minutes of history at the fastest cadence (0.5 s) is 600 points; the age
# trim below keeps the window honest regardless of the chosen interval.
_RING_MAX = 600
_RING_AGE_S = 300.0

# A time gap larger than this (seconds) between kept samples renders as a break
# in the sparkline — a pause or backoff window, never a straight interpolation.
_GAP_S = 8.0

_ZONE_RGB = {
    mr.ZONE_NOMINAL: (0x7f / 255.0, 0xd0 / 255.0, 0xa0 / 255.0),
    mr.ZONE_MEDIUM: (0xe8 / 255.0, 0xc2 / 255.0, 0x68 / 255.0),
    mr.ZONE_NEAR: (0xe0 / 255.0, 0x4c / 255.0, 0x4c / 255.0),
}
_TROUGH_RGB = (0x3a / 255.0, 0x3a / 255.0, 0x3a / 255.0)

_NET_EMPTY = ("per-process network not available from /proc — "
              "interface totals on the Network graph")


def _fmt_bytes(value):
    if value is None or value < 0:
        return "—"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            if unit == "B":
                return "%d B" % int(size)
            return "%.1f %s" % (size, unit)
        size /= 1024.0
    return "%.1f TB" % size


def _fmt_rate(value):
    if value is None or value < 0:
        return "—"
    return _fmt_bytes(value) + "/s"


class BasicsPage(BasePage):
    """Read-only, glanceable summary of system health."""

    def build_content(self):
        self.settings = AppSettings.load()
        self._show_sparklines = bool(
            self.settings.get("basics.show_sparklines", True))
        self._jump = None
        self._history = None   # shared manager_history rings (injected)
        self._last_procs = {}
        self._last_system = {}
        self._net_history = deque(maxlen=_RING_MAX)
        self._prev = {}       # metric -> previous scalar (delta arrows)
        self._state = {}      # metric -> {"fraction", "zone"}
        self._gauges = {}     # metric -> widget refs

        self.add_title("Basics")
        self.add_markup_label(
            "<span foreground='#909090'>A calm, read-only summary — the "
            "\"am I OK?\" view. Click any contributor to jump to it on "
            "Processes.</span>",
            wrap=True, spacing_after=6)

        for metric, label in _GAUGES:
            self._build_gauge(metric, label)

    # -- external wiring --------------------------------------------------

    def set_jump_callback(self, callback):
        """Install ``callback(key)`` — navigate to Processes with ``key``
        ((pid, starttime)) selected. Wired by the content area, which owns the
        navigation manager and the Processes page reference."""
        self._jump = callback

    def set_history(self, history):
        """Inject the shared :mod:`modules.manager_history` ring store — the
        sparklines slice it directly (the content area owns the single writer,
        fed on the Processes-page drain thread)."""
        self._history = history

    # -- gauge construction ----------------------------------------------

    def _build_gauge(self, metric, label):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        css.add_css_class(card, "basics-card")

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name = Gtk.Label(label=label)
        name.set_xalign(0)
        css.add_css_class(name, "basics-gauge-k")
        value = Gtk.Label()
        value.set_xalign(1)
        value.set_hexpand(True)
        value.set_halign(Gtk.Align.END)
        css.add_css_class(value, "basics-gauge-v")
        value.set_markup("<span foreground='#888888'>—</span>")
        layout.box_add(head, name, False, False, 0)
        layout.box_add(head, value, True, True, 0)
        layout.box_add(card, head, False, False, 0)

        bar = charts.ChartArea(
            draw_func=lambda a, cr, w, h, m=metric: self._draw_bar(cr, w, h, m))
        bar.set_size_request(-1, 16)
        bar.set_hexpand(True)
        layout.box_add(card, bar, False, True, 0)

        spark = None
        if self._show_sparklines:
            spark = charts.ChartArea(
                draw_func=lambda a, cr, w, h, m=metric: self._draw_spark(cr, w, h, m))
            spark.set_size_request(-1, 44)
            spark.set_hexpand(True)
            css.add_css_class(spark, "basics-spark")
            layout.box_add(card, spark, False, True, 0)

        caption = Gtk.Label()
        caption.set_xalign(0)
        css.add_css_class(caption, "basics-gauge-sub")
        layout.box_add(card, caption, False, False, 0)

        contrib_title = Gtk.Label(label="Top contributors")
        contrib_title.set_xalign(0)
        css.add_css_class(contrib_title, "basics-contrib-title")
        layout.box_add(card, contrib_title, False, False, 0)

        contrib = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        layout.box_add(card, contrib, False, False, 0)

        layout.box_add(self, card, False, False, 0)
        self._state[metric] = {"fraction": None, "zone": None}
        self._gauges[metric] = {
            "value": value, "caption": caption, "bar": bar,
            "spark": spark, "contrib": contrib, "rows": [],
        }

    # -- snapshot application (forwarded by the Processes page) -----------

    def on_snapshot(self, snapshot):
        """Apply one snapshot — no drain here; the Processes page forwards it."""
        system = snapshot.system or {}
        self._last_procs = snapshot.procs or {}
        self._last_system = system

        net = mr.net_reading(system)
        if not snapshot.from_backoff and net["total"] is not None:
            self._net_history.append(net["total"])
        ceiling = mr.network_ceiling(
            max(self._net_history) if self._net_history else None)

        for metric, _label in _GAUGES:
            frac, zone, value_markup, caption, scalar = self._read(
                metric, system, ceiling, net)
            refs = self._gauges[metric]
            refs["value"].set_markup(value_markup)
            refs["caption"].set_text(caption)
            self._state[metric] = {"fraction": frac, "zone": zone}
            refs["bar"].queue_draw()

            # Ring inserts happen in the shared manager_history writer (content
            # area, single drain thread) — here we only ask the spark to redraw
            # from that ring.
            if refs["spark"] is not None:
                refs["spark"].queue_draw()

            self._prev[metric] = scalar
            self._rebuild_contrib(metric)

    # -- readings + formatting -------------------------------------------

    _UP, _DOWN, _FLAT = "▲", "▼", "·"

    @staticmethod
    def _span(text, color):
        return "<span foreground='%s'>%s</span>" % (color, text)

    def _zone_hex(self, zone):
        rgb = _ZONE_RGB.get(zone)
        if rgb is None:
            return "#d0d0d0"
        return "#%02x%02x%02x" % tuple(int(c * 255) for c in rgb)

    def _arrow(self, metric, cur, threshold):
        prev = self._prev.get(metric)
        if cur is None or prev is None:
            return self._span(self._FLAT, "#d0d0d0")
        if abs(cur - prev) < threshold:
            return self._span(self._FLAT, "#d0d0d0")
        if cur > prev:
            return self._span(self._UP, "#e04c4c")
        return self._span(self._DOWN, "#3fbf6f")

    def _read(self, metric, system, ceiling, net):
        """Return ``(fraction, zone, value_markup, caption, scalar)`` for a gauge.

        ``scalar`` is the value pushed to the sparkline ring (percent for the
        percentage gauges, byte-rate for network, ``None`` for load).
        """
        if metric == "cpu":
            pct = mr.cpu_reading(system)["pct"]
            return self._pct_gauge("cpu", pct, "%d%%", "system busy", 1.0)
        if metric == "memory":
            r = mr.mem_reading(system)
            cap = "%s used / %s" % (_fmt_bytes(r["used"]), _fmt_bytes(r["total"]))
            return self._pct_gauge("memory", r["pct"], "%d%%", cap, 0.5)
        if metric == "swap":
            r = mr.swap_reading(system)
            cap = "%s used / %s" % (_fmt_bytes(r["used"]), _fmt_bytes(r["total"]))
            return self._pct_gauge("swap", r["pct"], "%.1f%%", cap, 0.5)
        if metric == "disk":
            r = mr.disk_reading(system)
            busiest = r["busiest"] or "—"
            cap = "device util · busiest: %s" % busiest
            return self._pct_gauge("disk", r["pct"], "%.1f%%", cap, 1.0)
        if metric == "network":
            total = net["total"]
            frac = mr.fraction(total, ceiling)
            zone = mr.capacity_zone((frac or 0.0) * 100.0) if total is not None else None
            value = _fmt_rate(total)
            arrow = self._arrow("network", total, 1024.0)
            markup = self._span(value, self._zone_hex(zone)) + " " + arrow
            cap = "↓%s  ↑%s · ceiling %s" % (
                _fmt_rate(net["rx"]), _fmt_rate(net["tx"]), _fmt_rate(ceiling))
            return frac, zone, markup, cap, total
        # load — no reader yet (probe-first "—").
        ncpu = mr.load_reading(system)["ncpu"] or 0
        markup = self._span("—", "#888888")
        return None, None, markup, "1 min · cores: %d" % ncpu, None

    def _pct_gauge(self, metric, pct, fmt, caption, threshold):
        frac = None if pct is None else max(0.0, min(1.0, pct / 100.0))
        zone = mr.capacity_zone(pct)
        arrow = self._arrow(metric, pct, threshold)
        if pct is None:
            value = self._span("—", "#888888")
        else:
            value = self._span(fmt % pct, self._zone_hex(zone))
        return frac, zone, value + " " + arrow, caption, pct

    # -- contributor lists ------------------------------------------------

    def _rebuild_contrib(self, metric):
        refs = self._gauges[metric]
        box = refs["contrib"]
        # Track our own children (get_children is GTK3-only; show_all is gated).
        for child in refs["rows"]:
            layout.box_remove(box, child)
        refs["rows"] = []

        if metric == "network":
            self._add_note(refs, _NET_EMPTY)
            return

        rows = mr.rank(self._last_procs, metric, mode="by_process", limit=5)
        if not rows:
            self._add_note(refs, "No contributors (—)")
            return

        note = " · ranks by CPU" if metric == "load" else ""
        for i, row in enumerate(rows, 1):
            self._add_row(refs, i, row, metric, note if i == 1 else "")

    def _add_note(self, refs, text):
        label = Gtk.Label()
        label.set_xalign(0)
        label.set_line_wrap(True)
        label.set_markup(self._span(text, "#888888"))
        layout.box_add(refs["contrib"], label, False, False, 0)
        label.show()
        refs["rows"].append(label)

    def _add_row(self, refs, rank, row, metric, extra):
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        css.add_css_class(button, "basics-contrib-row")
        label = Gtk.Label()
        label.set_xalign(0)
        label.set_use_markup(True)
        unit = (" <span size='small' foreground='#888888'>%s</span>"
                % _escape(row["unit"])) if row["unit"] else ""
        label.set_markup(
            "%d. %s%s  <span foreground='#888888'>%s</span>%s" % (
                rank, _escape(row["name"]), unit,
                _escape(self._value_text(metric, row["value"])),
                self._span(extra, "#666666")))
        layout.set_child(button, label)
        label.show()
        key = row["key"]
        button.connect("clicked", lambda _b, k=key: self._on_row_clicked(k))
        layout.box_add(refs["contrib"], button, False, False, 0)
        button.show()
        refs["rows"].append(button)

    def _value_text(self, metric, value):
        if metric in ("cpu", "load"):
            return "%.1f%%" % value
        if metric == "disk":
            return _fmt_rate(value)
        return _fmt_bytes(value)

    def _on_row_clicked(self, key):
        if self._jump is not None:
            self._jump(key)

    # -- cairo drawing ----------------------------------------------------

    def _draw_bar(self, cr, width, height, metric):
        cr.set_source_rgb(*_TROUGH_RGB)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        # Threshold ticks at 60/85 (Variant 2).
        cr.set_source_rgba(1, 1, 1, 0.14)
        for tick in (0.60, 0.85):
            cr.rectangle(tick * width, 0, 1, height)
            cr.fill()
        state = self._state.get(metric) or {}
        frac = state.get("fraction")
        if frac is None:
            return
        rgb = _ZONE_RGB.get(state.get("zone"), _ZONE_RGB[mr.ZONE_NOMINAL])
        cr.set_source_rgb(*rgb)
        cr.rectangle(0, 0, max(0.0, min(1.0, frac)) * width, height)
        cr.fill()

    def _draw_spark(self, cr, width, height, metric):
        # Load has no Basics reading (the gauge shows "—"), so its spark stays
        # empty here even though the shared ring now carries real load data —
        # the Load chart lives on the Graphs page.
        if metric == "load" or self._history is None:
            return
        pts = self._history.slice(metric, _RING_AGE_S)
        if len(pts) < 2:
            return
        if metric == "network":
            vmax = max((v for _t, v in pts if v is not None), default=0.0) or 1.0
        else:
            vmax = 100.0
        t0 = pts[0][0]
        span = max(1e-6, pts[-1][0] - t0)
        rgb = _ZONE_RGB.get(
            (self._state.get(metric) or {}).get("zone"), _ZONE_RGB[mr.ZONE_NOMINAL])
        cr.set_source_rgb(*rgb)
        cr.set_line_width(1.5)
        started = False
        prev_t = None
        for ts, value in pts:
            if value is None:
                started = False
                prev_t = ts
                continue
            if started and prev_t is not None and (ts - prev_t) > _GAP_S:
                started = False  # a pause/backoff window renders as a gap
            x = (ts - t0) / span * width
            y = height - min(1.0, max(0.0, value / vmax)) * (height - 2) - 1
            if not started:
                cr.move_to(x, y)
                started = True
            else:
                cr.line_to(x, y)
            prev_t = ts
        cr.stroke()


def _escape(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
