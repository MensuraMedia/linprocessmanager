"""Graphs ▸ X — per-metric detail pages (Phase 5).

Spec: docs/modules/graphs-hub.md §2 (THE SPEC) + resource-graphs.md (ring law).
One page per metric over a shared :class:`GraphDetailPage` skeleton: a large
zone-banded chart, a 1 m / 5 m window selector (per-session, never persisted —
the rings only hold ~5 min, so longer windows would be dishonest slices), a
current/min/avg/max stat strip, a "Top contributors" panel (the same ranking
model as the metric-band drill), and a per-core / per-device / per-iface
breakdown where the metric has one.

Boundary law: these pages consume snapshots + :mod:`manager_history` rings only;
they never read ``/proc``. Every toolkit call routes through ``ui.compat`` and
all cairo drawing goes through ``ui.compat.charts`` (the ``draw`` connection is
the charts adapter's alone — gate-enforced).
"""

from ui.compat import Gtk, css, layout, charts

from pages.page_base import BasePage
from modules import manager_rank as mr
from modules import manager_history as mh

# Window selector choices (label -> seconds). 1 m / 5 m ONLY (spec §2): the
# rings hold ~5 min, so a longer option would masquerade a short window as long
# history. A 15 m / session tier needs a designed downsampled long-ring first.
WINDOW_CHOICES = [("1 m", 60.0), ("5 m", 300.0)]
_DEFAULT_WINDOW_S = 300.0

# A time gap larger than this (seconds) between kept samples renders as a break
# in the line — a pause or backoff window, never a straight interpolation.
_GAP_S = 8.0

_ZONE_RGB = {
    mr.ZONE_NOMINAL: (0x7f / 255.0, 0xd0 / 255.0, 0xa0 / 255.0),
    mr.ZONE_MEDIUM: (0xe8 / 255.0, 0xc2 / 255.0, 0x68 / 255.0),
    mr.ZONE_NEAR: (0xe0 / 255.0, 0x4c / 255.0, 0x4c / 255.0),
}
_TRACE_RGB = (0x6c / 255.0, 0xb6 / 255.0, 0xe0 / 255.0)   # neutral chart accent
# Distinct traces for the PSI triple (cpu / mem / io).
_PSI_TRACE_RGB = [
    (0x6c / 255.0, 0xb6 / 255.0, 0xe0 / 255.0),
    (0xe8 / 255.0, 0xc2 / 255.0, 0x68 / 255.0),
    (0xc0 / 255.0, 0x8c / 255.0, 0xe0 / 255.0),
]
_GRID_RGBA = (1, 1, 1, 0.08)

# Honest per-process-network empty-state on the Network detail page — /proc
# exposes no per-PID bandwidth, so the ranking panel points at the interface
# breakdown on this same page instead of promising a drill (backlog I9).
_NET_EMPTY = ("per-process network not available from /proc — "
              "see interface totals below")


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


class DetailSpec:
    """The per-metric configuration a :class:`GraphDetailPage` renders from."""

    def __init__(self, page_id, title, kind, series, mr_metric=None,
                 extra_series=(), breakdown=None, note=None):
        self.page_id = page_id
        self.title = title
        self.kind = kind              # "pct" | "rate" | "load" | "pressure"
        self.series = series          # primary ring series (chart + stats)
        self.mr_metric = mr_metric    # manager_rank metric for contributors
        self.extra_series = tuple(extra_series)  # extra chart traces (pressure)
        self.breakdown = breakdown    # None | "cores" | "devices" | "ifaces"
        self.note = note              # caption under the chart


# Page inventory (hub order). CPU · Memory · Swap · Disk · Network · Pressure ·
# Load. Load ships with real data because the loadavg reader lands in this task.
DETAIL_SPECS = [
    DetailSpec("graphs_cpu", "CPU", "pct", "cpu", mr_metric="cpu",
               breakdown="cores", note="system busy — 100% = whole machine"),
    DetailSpec("graphs_memory", "Memory", "pct", "memory", mr_metric="memory",
               note="used / total"),
    DetailSpec("graphs_swap", "Swap", "pct", "swap", mr_metric="swap",
               note="swap used / total"),
    DetailSpec("graphs_disk", "Disk I/O", "pct", "disk", mr_metric="disk",
               breakdown="devices", note="busiest device utilisation"),
    DetailSpec("graphs_network", "Network", "rate", "network",
               breakdown="ifaces", note="rx + tx rate, auto-scaled"),
    DetailSpec("graphs_pressure", "Pressure", "pressure", "psi_cpu",
               extra_series=("psi_mem", "psi_io"),
               note="PSI some avg10 · cpu / mem / io"),
    DetailSpec("graphs_load", "Load", "load", "load", mr_metric="load",
               note="1-min load average vs core count"),
]

def breakdown_rows(kind, system):
    """Per-core / per-device / per-iface breakdown text rows for ``system``.

    Pure (no widgets) so the breakdown-row math is fixture-testable. Absent
    values render "—", never a fabricated 0 (r039 taxonomy). Rows are sorted for
    a stable order (core index, device name, interface name).
    """
    system = system or {}
    if kind == "cores":
        per_core = (system.get("cpu") or {}).get("per_core") or {}
        return ["Core %d: %s" % (
            index, "%.0f%%" % per_core[index] if per_core[index] is not None else "—")
            for index in sorted(per_core)]
    if kind == "devices":
        disks = system.get("disks") or {}
        out = []
        for dev in sorted(disks):
            vals = disks[dev]
            util = vals.get("util")
            out.append("%s: %s util · ↓%s ↑%s" % (
                dev, "%.0f%%" % util if util is not None else "—",
                _fmt_rate(vals.get("read_rate")), _fmt_rate(vals.get("write_rate"))))
        return out
    if kind == "ifaces":
        net = system.get("net") or {}
        return ["%s: ↓%s ↑%s" % (
            iface, _fmt_rate(net[iface].get("rx_rate")),
            _fmt_rate(net[iface].get("tx_rate")))
            for iface in sorted(net)]
    return []


class GraphDetailPage(BasePage):
    """One metric's detail page, driven by a :class:`DetailSpec`."""

    def __init__(self, spec):
        self.spec = spec
        self._history = None
        self._navigate = None
        self._jump = None
        self._last_procs = {}
        self._last_system = {}
        self._window_s = _DEFAULT_WINDOW_S
        self._window_buttons = {}
        self._contrib_rows = []
        self._breakdown_rows = []
        super().__init__()

    # -- external wiring --------------------------------------------------

    def set_history(self, history):
        self._history = history

    def set_navigate(self, callback):
        """``callback(page_id)`` — jump to another page (Back → hub)."""
        self._navigate = callback

    def set_jump_callback(self, callback):
        """``callback(key)`` — select ``(pid, starttime)`` on the Processes page."""
        self._jump = callback

    # -- construction -----------------------------------------------------

    def build_content(self):
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        back = Gtk.Button(label="◂ Back to Graphs")
        css.add_css_class(back, "graph-back")
        back.set_relief(Gtk.ReliefStyle.NONE)
        back.connect("clicked", lambda _b: self._go("graphs"))
        layout.box_add(header, back, False, False, 0)
        title = Gtk.Label(label="Graphs ▸ %s" % self.spec.title)
        title.set_xalign(0)
        css.add_css_class(title, "page-title")
        layout.box_add(header, title, True, True, 0)
        layout.box_add(self, header, False, False, 0)

        # Window selector (1 m / 5 m) — per-session only.
        sel = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        css.add_css_class(sel, "linked")
        for label, seconds in WINDOW_CHOICES:
            btn = Gtk.ToggleButton(label=label)
            btn.set_active(abs(seconds - self._window_s) < 1e-6)
            btn.connect("toggled", self._on_window_toggled, seconds)
            layout.box_add(sel, btn, False, False, 0)
            self._window_buttons[seconds] = btn
        layout.box_add(self, sel, False, False, 0)

        # Large chart (~40% of the page height, mockup L).
        self.chart = charts.ChartArea(
            draw_func=lambda a, cr, w, h: self._draw_chart(cr, w, h))
        self.chart.set_size_request(-1, 260)
        self.chart.set_hexpand(True)
        self.chart.set_vexpand(True)
        css.add_css_class(self.chart, "graph-detail-chart")
        layout.box_add(self, self.chart, True, True, 0)

        self.chart_note = Gtk.Label()
        self.chart_note.set_xalign(0)
        css.add_css_class(self.chart_note, "graph-caption")
        self.chart_note.set_markup(self._span(_escape(self.spec.note or ""), "#888888"))
        layout.box_add(self, self.chart_note, False, False, 0)

        # Stat strip: current / min / avg / max over the window.
        self.stat_label = Gtk.Label()
        self.stat_label.set_xalign(0)
        css.add_css_class(self.stat_label, "graph-stats")
        self.stat_label.set_markup(self._span("current — · min — · avg — · max —", "#888888"))
        layout.box_add(self, self.stat_label, False, False, 0)

        # Contributors panel.
        contrib_title = Gtk.Label(label="Top contributors")
        contrib_title.set_xalign(0)
        css.add_css_class(contrib_title, "graph-section")
        layout.box_add(self, contrib_title, False, False, 0)
        self.contrib_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        layout.box_add(self, self.contrib_box, False, False, 0)

        # Breakdown panel (per-core / per-device / per-iface) where applicable.
        if self.spec.breakdown is not None:
            bt = Gtk.Label(label=self._breakdown_title())
            bt.set_xalign(0)
            css.add_css_class(bt, "graph-section")
            layout.box_add(self, bt, False, False, 0)
            self.breakdown_box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL, spacing=0)
            layout.box_add(self, self.breakdown_box, False, False, 0)
        else:
            self.breakdown_box = None

    def _breakdown_title(self):
        return {"cores": "Per-core", "devices": "Per-device",
                "ifaces": "Per-interface"}.get(self.spec.breakdown, "Breakdown")

    # -- snapshot application (forwarded by the Processes page) -----------

    def on_snapshot(self, snapshot):
        self._last_procs = snapshot.procs or {}
        self._last_system = snapshot.system or {}
        self.chart.queue_draw()
        self._update_stats()
        self._rebuild_contrib()
        self._rebuild_breakdown()

    # -- window selector --------------------------------------------------

    def _on_window_toggled(self, button, seconds):
        if not button.get_active():
            # Keep exactly one window active (radio semantics).
            if not any(b.get_active() for b in self._window_buttons.values()):
                button.set_active(True)
            return
        for other_s, other in self._window_buttons.items():
            if abs(other_s - seconds) > 1e-6 and other.get_active():
                other.set_active(False)
        self._window_s = seconds
        self.chart.queue_draw()
        self._update_stats()

    # -- stats ------------------------------------------------------------

    def _points(self, series):
        if self._history is None:
            return []
        return self._history.slice(series, self._window_s)

    def _update_stats(self):
        stats = mh.window_stats(self._points(self.spec.series))
        parts = []
        for key in ("current", "min", "avg", "max"):
            parts.append("%s %s" % (key, self._fmt_value(stats[key])))
        self.stat_label.set_markup(self._span(" · ".join(parts), "#d0d0d0"))

    # -- contributors -----------------------------------------------------

    def _rebuild_contrib(self):
        box = self.contrib_box
        for child in self._contrib_rows:
            layout.box_remove(box, child)
        self._contrib_rows = []

        if self.spec.mr_metric is None:
            self._add_note(box, self._contrib_rows, _NET_EMPTY
                           if self.spec.series == "network"
                           else "System-wide metric — no per-process contributors")
            return

        rows = mr.rank(self._last_procs, self.spec.mr_metric,
                       mode="by_process", limit=10)
        if not rows:
            self._add_note(box, self._contrib_rows, "No contributors (—)")
            return
        note = " · ranks by CPU" if self.spec.mr_metric == "load" else ""
        for i, row in enumerate(rows, 1):
            self._add_contrib_row(i, row, note if i == 1 else "")

    def _add_contrib_row(self, rank, row, extra):
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
                _escape(self._contrib_value_text(row["value"])),
                self._span(extra, "#666666")))
        layout.set_child(button, label)
        label.show()
        key = row["key"]
        button.connect("clicked", lambda _b, k=key: self._on_row_clicked(k))
        layout.box_add(self.contrib_box, button, False, False, 0)
        button.show()
        self._contrib_rows.append(button)

    def _contrib_value_text(self, value):
        metric = self.spec.mr_metric
        if metric in ("cpu", "load"):
            return "%.1f%%" % value
        if metric == "disk":
            return _fmt_rate(value)
        return _fmt_bytes(value)

    def _on_row_clicked(self, key):
        if self._jump is not None:
            self._jump(key)

    # -- breakdown --------------------------------------------------------

    def _rebuild_breakdown(self):
        if self.breakdown_box is None:
            return
        for child in self._breakdown_rows:
            layout.box_remove(self.breakdown_box, child)
        self._breakdown_rows = []

        rows = self._breakdown_rows_text()
        if not rows:
            self._add_note(self.breakdown_box, self._breakdown_rows,
                           "No data (—)")
            return
        for text in rows:
            label = Gtk.Label()
            label.set_xalign(0)
            label.set_markup(self._span(_escape(text), "#c8c8c8"))
            layout.box_add(self.breakdown_box, label, False, False, 0)
            label.show()
            self._breakdown_rows.append(label)

    def _breakdown_rows_text(self):
        return breakdown_rows(self.spec.breakdown, self._last_system)

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _span(text, color):
        return "<span foreground='%s'>%s</span>" % (color, text)

    def _ncpu(self):
        return (self._last_system.get("cpu") or {}).get("ncpu") or 1

    def _fmt_value(self, value):
        if value is None:
            return "—"
        kind = self.spec.kind
        if kind == "pct" or kind == "pressure":
            return "%.1f%%" % value
        if kind == "rate":
            return _fmt_rate(value)
        if kind == "load":
            return "%.2f" % value
        return "%.1f" % value

    def _add_note(self, box, tracker, text):
        label = Gtk.Label()
        label.set_xalign(0)
        label.set_line_wrap(True)
        label.set_markup(self._span(_escape(text), "#888888"))
        layout.box_add(box, label, False, False, 0)
        label.show()
        tracker.append(label)

    def _go(self, page_id):
        if self._navigate is not None:
            self._navigate(page_id)

    # -- cairo drawing ----------------------------------------------------

    def _chart_max(self, all_points):
        kind = self.spec.kind
        if kind in ("pct", "pressure"):
            return 100.0
        if kind == "load":
            return max(float(self._ncpu()), self._series_peak(all_points))
        # rate: auto-scale to 1.2x the trailing peak, small floor.
        peak = self._series_peak(all_points)
        return max(1024.0, peak * 1.2)

    @staticmethod
    def _series_peak(all_points):
        peak = 0.0
        for pts in all_points:
            for _ts, value in pts:
                if value is not None and value > peak:
                    peak = value
        return peak

    def _draw_chart(self, cr, width, height):
        series_list = [self.spec.series] + list(self.spec.extra_series)
        all_points = [self._points(s) for s in series_list]

        # Zone-tinted background bands for bounded (percentage) charts.
        if self.spec.kind in ("pct", "pressure", "load"):
            self._draw_zone_bands(cr, width, height)
        self._draw_gridlines(cr, width, height)

        vmax = self._chart_max(all_points)
        if vmax <= 0:
            return

        # A shared time axis across all traces so the triple lines up.
        t0 = t1 = None
        for pts in all_points:
            if pts:
                t0 = pts[0][0] if t0 is None else min(t0, pts[0][0])
                t1 = pts[-1][0] if t1 is None else max(t1, pts[-1][0])
        if t0 is None:
            return
        span = max(1e-6, (t1 - t0))

        for idx, pts in enumerate(all_points):
            rgb = (_PSI_TRACE_RGB[idx % len(_PSI_TRACE_RGB)]
                   if self.spec.kind == "pressure" else _TRACE_RGB)
            self._draw_trace(cr, width, height, pts, t0, span, vmax, rgb)

    def _draw_zone_bands(self, cr, width, height):
        # Green 0-60, amber 60-85, red 85-100 (fraction of the chart height).
        bands = [
            (0.0, 0.60, _ZONE_RGB[mr.ZONE_NOMINAL]),
            (0.60, 0.85, _ZONE_RGB[mr.ZONE_MEDIUM]),
            (0.85, 1.0, _ZONE_RGB[mr.ZONE_NEAR]),
        ]
        for lo, hi, rgb in bands:
            cr.set_source_rgba(rgb[0], rgb[1], rgb[2], 0.08)
            y = height - hi * height
            cr.rectangle(0, y, width, (hi - lo) * height)
            cr.fill()

    def _draw_gridlines(self, cr, width, height):
        cr.set_source_rgba(*_GRID_RGBA)
        for frac in (0.25, 0.5, 0.75):
            y = height - frac * height
            cr.rectangle(0, y, width, 1)
            cr.fill()

    def _draw_trace(self, cr, width, height, pts, t0, span, vmax, rgb):
        if len(pts) < 2:
            return
        cr.set_source_rgb(*rgb)
        cr.set_line_width(1.6)
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
