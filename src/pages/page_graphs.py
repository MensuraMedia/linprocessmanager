"""Graphs hub — the grid of live mini-charts (Phase 5).

Spec: docs/modules/graphs-hub.md §1 (THE SPEC) + resource-graphs.md (ring law).
A hub of seven live mini-charts (CPU · Memory · Swap · Disk I/O · Network ·
Pressure · Load); **every chart is clickable into its own detail page**
(:mod:`pages.graph_details`). This is the sidebar surface that supersedes the
old Resources entry (retired in the same change).

Each mini-chart shows its title, current value (threshold-zone coloured via the
shared capacity helper), and a sparkline drawn from the shared
:mod:`manager_history` rings — ``(ts, value)`` tuples, backoff excluded, gaps
rendered as gaps.

Boundary law: consumes snapshots + rings only; never reads ``/proc``. All cairo
drawing goes through ``ui.compat.charts``; every toolkit call through a compat
seam.
"""

from ui.compat import Gtk, css, layout, charts

from pages.page_base import BasePage
from modules import manager_rank as mr
from modules import manager_history as mh
from pages.graph_details import DETAIL_SPECS, chart_traces, _disk_rw_rates

# The seven hub charts are exactly the seven detail specs, in order.
HUB_CHARTS = list(DETAIL_SPECS)

# Sparkline window shown on the hub cards (~5 min, the ring depth).
_HUB_WINDOW_S = 300.0
_GAP_S = 8.0

_ZONE_RGB = {
    mr.ZONE_NOMINAL: (0x22 / 255.0, 0xc5 / 255.0, 0x5e / 255.0),
    mr.ZONE_MEDIUM: (0xfa / 255.0, 0xcc / 255.0, 0x15 / 255.0),
    mr.ZONE_NEAR: (0xef / 255.0, 0x44 / 255.0, 0x44 / 255.0),
}
_TRACE_RGB = (0x6c / 255.0, 0xb6 / 255.0, 0xe0 / 255.0)
_PSI_TRACE_RGB = [
    (0x6c / 255.0, 0xb6 / 255.0, 0xe0 / 255.0),
    (0xfa / 255.0, 0xcc / 255.0, 0x15 / 255.0),
    (0xc0 / 255.0, 0x8c / 255.0, 0xe0 / 255.0),
]


def _escape(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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


class GraphsHubPage(BasePage):
    """Grid of clickable live mini-charts, one per metric."""

    def build_content(self):
        self._history = None
        self._navigate = None
        self._last_system = {}
        self._cards = {}   # series -> {"value": label, "spark": ChartArea}
        # Page-local ring for the decomposed sub-series (per-core / rx-tx /
        # read-write) the shared store does not carry — same ring law, fed from
        # on_snapshot, so the mini-charts can draw the same multi-series as the
        # detail pages (spec §2b.4). Compact: no crosshair on the hub.
        self._local = mh.History()

        self.add_title("Graphs")
        self.add_markup_label(
            "<span foreground='#909090'>Live performance charts. Click any "
            "chart to open its dedicated page.</span>", wrap=True, spacing_after=6)

        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_max_children_per_line(3)   # 2×3 grid on ≥1200 px, stacks narrower
        flow.set_min_children_per_line(1)
        flow.set_homogeneous(True)
        flow.set_column_spacing(12)
        flow.set_row_spacing(12)
        for spec in HUB_CHARTS:
            flow.insert(self._build_card(spec), -1)
        layout.box_add(self, flow, True, True, 0)

    # -- external wiring --------------------------------------------------

    def add_basics_section(self, widget):
        """r092 (operator): the Basics cards live at the TOP of the hub —
        above the chart grid — and the standalone Basics page/sidebar entry
        is gone (the submenu experiment is retired). ``widget`` is the
        BasicsPage instance; it keeps receiving snapshots via the normal
        observer list."""
        layout.box_add(self, widget, False, False, 0)
        self.reorder_child(widget, 0)

    def set_history(self, history):
        self._history = history

    def set_navigate(self, callback):
        """``callback(page_id)`` — open a detail page on a card click."""
        self._navigate = callback

    # -- card construction ------------------------------------------------

    def _build_card(self, spec):
        button = Gtk.Button()
        css.add_css_class(button, "graph-card")
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.connect("clicked", lambda _b, pid=spec.page_id: self._go(pid))

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name = Gtk.Label(label=spec.title)
        name.set_xalign(0)
        css.add_css_class(name, "graph-card-k")
        value = Gtk.Label()
        value.set_xalign(1)
        value.set_hexpand(True)
        value.set_halign(Gtk.Align.END)
        css.add_css_class(value, "graph-card-v")
        value.set_markup(self._span("—", "#888888"))
        layout.box_add(head, name, False, False, 0)
        layout.box_add(head, value, True, True, 0)
        layout.box_add(card, head, False, False, 0)

        # Compact legend row (chip + label + live value per series).
        legend_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        css.add_css_class(legend_box, "graph-card-legend")
        layout.box_add(card, legend_box, False, False, 0)

        spark = charts.ChartArea(
            draw_func=lambda a, cr, w, h, s=spec: self._draw_spark(cr, w, h, s))
        spark.set_size_request(220, 72)
        spark.set_hexpand(True)
        css.add_css_class(spark, "graph-card-spark")
        layout.box_add(card, spark, True, True, 0)

        layout.set_child(button, card)
        self._cards[spec.series] = {
            "value": value, "spark": spark, "spec": spec,
            "legend_box": legend_box, "legend_keys": None,
            "legend_labels": {}, "legend_rows": [],
        }
        return button

    # -- snapshot application (forwarded by the Processes page) -----------

    def on_snapshot(self, snapshot):
        self._last_system = snapshot.system or {}
        self._record_local(snapshot)
        for spec in HUB_CHARTS:
            refs = self._cards[spec.series]
            refs["value"].set_markup(self._current_markup(spec))
            self._sync_card_legend(spec, refs)
            refs["spark"].queue_draw()

    def _record_local(self, snapshot):
        """Feed the decomposed sub-series (per-core / rx-tx / read-write) into
        the page-local ring — the shared store carries only the totals."""
        ts = snapshot.ts
        backoff = snapshot.from_backoff
        system = snapshot.system or {}
        per_core = (system.get("cpu") or {}).get("per_core") or {}
        for idx, value in per_core.items():
            self._local.insert("core%d" % idx, ts, value, from_backoff=backoff)
        net = mr.net_reading(system)
        self._local.insert("rx", ts, net["rx"], from_backoff=backoff)
        self._local.insert("tx", ts, net["tx"], from_backoff=backoff)
        read, write = _disk_rw_rates(system)
        self._local.insert("read", ts, read, from_backoff=backoff)
        self._local.insert("write", ts, write, from_backoff=backoff)

    # -- traces + legend --------------------------------------------------

    def _traces(self, spec):
        """The card's chart traces + axis kind (shared with the detail page).

        The per-core CPU legend is collapsed to just ``total`` on the compact
        hub card (the detail page carries the full per-core legend); every other
        card lists all its series.
        """
        traces, axis_kind = chart_traces(
            spec.page_id, self._ncpu(), spec.kind, spec.series,
            spec.extra_series, spec.title)
        legend = traces[:1] if spec.page_id == "graphs_cpu" else traces
        return traces, legend, axis_kind

    def _ncpu(self):
        return (self._last_system.get("cpu") or {}).get("ncpu") or 1

    def _slice(self, desc):
        if desc["store"] == "history":
            return self._history.slice(desc["key"], _HUB_WINDOW_S) \
                if self._history else []
        return self._local.slice(desc["key"], _HUB_WINDOW_S)

    def _last_of(self, desc):
        store = self._history if desc["store"] == "history" else self._local
        if store is None:
            return None
        point = store.last(desc["key"])
        return point[1] if point is not None else None

    def _sync_card_legend(self, spec, refs):
        _traces, legend, axis_kind = self._traces(spec)
        keys = tuple(t["key"] for t in legend)
        extra = (" <span foreground='#666666'>+%d cores</span>" % (self._ncpu())
                 if spec.page_id == "graphs_cpu" else "")
        if keys != refs["legend_keys"]:
            for child in refs["legend_rows"]:
                layout.box_remove(refs["legend_box"], child)
            refs["legend_rows"] = []
            refs["legend_labels"] = {}
            for trace in legend:
                label = Gtk.Label()
                label.set_use_markup(True)
                label.set_xalign(0)
                css.add_css_class(label, "graph-card-legend-item")
                layout.box_add(refs["legend_box"], label, False, False, 0)
                label.show()
                refs["legend_labels"][trace["key"]] = label
            refs["legend_keys"] = keys
        for i, trace in enumerate(legend):
            label = refs["legend_labels"].get(trace["key"])
            if label is None:
                continue
            value = self._last_of(trace)
            chip = "#%02x%02x%02x" % tuple(int(c * 255) for c in trace["color"])
            label.set_markup(
                "<span foreground='%s'>■</span> "
                "<span foreground='#b0b0b0'>%s</span> "
                "<span foreground='#e8e8e8'>%s</span>%s" % (
                    chip, _escape(trace["label"]),
                    _escape(self._fmt_axis(axis_kind, value)),
                    extra if i == len(legend) - 1 else ""))

    @staticmethod
    def _fmt_axis(axis_kind, value):
        if value is None:
            return "—"
        if axis_kind in ("pct", "pressure"):
            return "%.1f%%" % value
        if axis_kind == "rate":
            return _fmt_rate(value)
        if axis_kind == "load":
            return "%.2f" % value
        return "%.1f" % value

    # -- current value + zone ---------------------------------------------

    def _last_value(self, series):
        if self._history is None:
            return None
        point = self._history.last(series)
        return point[1] if point is not None else None

    def _current_markup(self, spec):
        value = self._last_value(spec.series)
        if value is None:
            return self._span("—", "#888888")
        zone, text = self._value_zone_text(spec, value)
        return self._span(text, self._zone_hex(zone))

    def _value_zone_text(self, spec, value):
        kind = spec.kind
        if kind == "pct":
            return mr.capacity_zone(value), "%.0f%%" % value
        if kind == "pressure":
            return mr.capacity_zone(value), "%.1f%%" % value
        if kind == "load":
            ncpu = (self._last_system.get("cpu") or {}).get("ncpu") or 1
            return mr.capacity_zone(100.0 * value / ncpu), "%.2f" % value
        # rate: zone by fraction of an auto-scale ceiling (2× trailing max).
        ceiling = mr.network_ceiling(self._series_peak(spec.series))
        frac = mr.fraction(value, ceiling)
        zone = mr.capacity_zone((frac or 0.0) * 100.0)
        return zone, _fmt_rate(value)

    def _series_peak(self, series):
        if self._history is None:
            return None
        peak = None
        for _ts, value in self._history.slice(series, _HUB_WINDOW_S):
            if value is not None and (peak is None or value > peak):
                peak = value
        return peak

    def _zone_hex(self, zone):
        rgb = _ZONE_RGB.get(zone)
        if rgb is None:
            return "#d0d0d0"
        return "#%02x%02x%02x" % tuple(int(c * 255) for c in rgb)

    @staticmethod
    def _span(text, color):
        return "<span foreground='%s'>%s</span>" % (color, text)

    def _go(self, page_id):
        if self._navigate is not None:
            self._navigate(page_id)

    # -- cairo drawing ----------------------------------------------------

    def _draw_spark(self, cr, width, height, spec):
        traces, _legend, axis_kind = self._traces(spec)
        all_points = [self._slice(t) for t in traces]

        vmax = self._spark_max(axis_kind, all_points)
        if vmax <= 0:
            return
        primary_index = next(
            (i for i, t in enumerate(traces) if t["primary"]), 0)
        # Compact: fills on the primary, no gridlines/zone bands/crosshair.
        charts.render_series(
            cr, width, height, all_points,
            [t["color"] for t in traces],
            vmax=vmax,
            fills=[t["fill"] for t in traces],
            line_widths=[max(1.0, t["width"] - 0.6) for t in traces],
            primary_index=primary_index,
            gridlines=False, zone_bands=False, endpoint_dot=False,
            gap_s=_GAP_S)

    def _spark_max(self, axis_kind, all_points):
        if axis_kind in ("pct", "pressure"):
            return 100.0
        peak = 0.0
        for pts in all_points:
            for _ts, value in pts:
                if value is not None and value > peak:
                    peak = value
        if axis_kind == "load":
            return max(float(self._ncpu()), peak)
        return max(1024.0, peak * 1.2)  # rate auto-scale
