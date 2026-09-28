"""Basics page — the read-only "am I OK?" system summary (Phase 4.5).

Spec: docs/modules/metric-band-basics.md §3 + graphs-hub.md §3 (r068, mockup M).
The calm, glanceable counterpart to the Processes page: the same six gauges as
**split cards** — a fixed gauge block on the LEFT (title + big bar + zone
caption) and the top contributing processes on the RIGHT (rank, name, mini-bar
proportional to the leader, value; click a row to select it on Processes). This
supersedes the earlier gauge-plus-sparkline layout — history now lives on the
Graphs surfaces. No editing, no actions — power features stay on Processes.

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

from ui.compat import Gtk, Pango, css, layout, charts

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
    mr.ZONE_NOMINAL: (0x22 / 255.0, 0xc5 / 255.0, 0x5e / 255.0),
    mr.ZONE_MEDIUM: (0xfa / 255.0, 0xcc / 255.0, 0x15 / 255.0),
    mr.ZONE_NEAR: (0xef / 255.0, 0x44 / 255.0, 0x44 / 255.0),
}
_TROUGH_RGB = (0x3a / 255.0, 0x3a / 255.0, 0x3a / 255.0)

# Contributor mini-bar colour per metric (mockup M): cpu/disk/load ride the
# theme accent, the memory family a lighter blue. Network has no per-process
# contributors (honest empty-state), so no bar.
# r088: ONE color for every contributor mini-bar — the theme accent. The
# old per-metric table drew Memory/Swap in a lighter blue (#2ea6ff) than
# CPU/Disk/Load (#0078d7); the operator called the mix inconsistent.
_CONTRIB_BAR_RGB = (0x00 / 255.0, 0x78 / 255.0, 0xD7 / 255.0)
_CONTRIB_BAR_TROUGH = (0x1b / 255.0, 0x1b / 255.0, 0x1b / 255.0)

# r090: fixed Basics card height (bounding-box policy §5b): sized for the
# four contributor rows; content scrolls/clips inside, the box never moves.
BASICS_CARD_HEIGHT = 132

_NET_EMPTY = ("per-process network not available from /proc — "
              "interface totals on the Network graph")


def contrib_fractions(values):
    """Mini-bar fractions proportional to the leader (largest value).

    Pure + fixture-testable (mockup M: each contributor's bar is sized against
    the top row). ``None`` values and a non-positive leader yield ``0.0`` — an
    absent contribution is never a fabricated bar.
    """
    nums = [v for v in values if v is not None]
    leader = max(nums) if nums else 0.0
    if leader <= 0:
        return [0.0 for _ in values]
    return [(v / leader) if v is not None else 0.0 for v in values]


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
        self._jump = None
        self._history = None   # shared manager_history rings (injected)
        self._last_procs = {}
        self._last_system = {}
        self._net_history = deque(maxlen=_RING_MAX)
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
        # Split card (mockup M / spec §3): fixed gauge block on the LEFT (title +
        # big bar + zone caption), top contributing processes on the RIGHT.
        # r108 (operator): the card is a Gtk.Paned with the divider FORCED
        # to the midline on every size allocation — the left/right split is
        # exactly 50/50 at any width, immune to content requisition. (The
        # previous Box-based halves negotiated from unequal label naturals
        # and drifted per card.) Height stays pinned at BASICS_CARD_HEIGHT.
        card = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        css.add_css_class(card, "basics-card")
        card.set_size_request(-1, BASICS_CARD_HEIGHT)
        card.connect("size-allocate", self._on_card_allocate)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        css.add_css_class(left, "basics-left")
        # r106 (operator): the card splits 50/50 — BOTH halves expand, so
        # GTK divides the card width exactly in half. The halves' natural
        # widths are capped below (labels + contributor names), so nothing
        # can skew the split anymore.
        left.set_hexpand(True)
        left.set_size_request(300, -1)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name = Gtk.Label(label=label)
        name.set_xalign(0)
        css.add_css_class(name, "basics-gauge-k")
        value = Gtk.Label()
        value.set_xalign(1)
        value.set_hexpand(True)
        value.set_halign(Gtk.Align.END)
        css.add_css_class(value, "basics-gauge-v")
        # r071 bounding-box policy: dynamic text is pinned + ellipsized so the
        # card's natural width can never grow with the displayed value.
        value.set_width_chars(12)        # r086: fixed requisition (§5b)
        value.set_max_width_chars(12)
        value.set_ellipsize(Pango.EllipsizeMode.END)    # r079 cap kept
        value.set_ellipsize(Pango.EllipsizeMode.END)
        value.set_markup("<span foreground='#888888'>—</span>")
        layout.box_add(head, name, False, False, 0)
        layout.box_add(head, value, True, True, 0)
        layout.box_add(left, head, False, False, 0)

        bar = charts.ChartArea(
            draw_func=lambda a, cr, w, h, m=metric: self._draw_bar(cr, w, h, m))
        bar.set_size_request(-1, 14)
        bar.set_hexpand(True)
        layout.box_add(left, bar, False, True, 0)

        caption = Gtk.Label()
        caption.set_xalign(0)
        # r102: caption pinned at 26 chars — 34 chars at this font requested
        # ~340px, past the left block's 300px floor, so Swap/Disk captions
        # flexed the whole card (the operator's "uneven cards"). The ellipsis
        # is the honest truncation; the text below the bar stays single-line.
        caption.set_width_chars(26)      # r086: fixed requisition (§5b)
        caption.set_max_width_chars(26)
        caption.set_ellipsize(Pango.EllipsizeMode.END)
        css.add_css_class(caption, "basics-gauge-sub")
        layout.box_add(left, caption, False, False, 0)
        card.pack1(left, True, True)

        # Right: the processes driving this metric, mini-bar proportional to the
        # leader. Populated by _rebuild_contrib on every snapshot.
        contrib = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        css.add_css_class(contrib, "basics-right")
        card.pack2(contrib, True, True)

        layout.box_add(self, card, False, False, 0)
        self._state[metric] = {"fraction": None, "zone": None}
        self._gauges[metric] = {
            "value": value, "caption": caption, "bar": bar,
            "contrib": contrib, "rows": [],
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

            self._rebuild_contrib(metric)

    # -- readings + formatting -------------------------------------------

    @staticmethod
    def _span(text, color):
        return "<span foreground='%s'>%s</span>" % (color, text)

    def _zone_hex(self, zone):
        rgb = _ZONE_RGB.get(zone)
        if rgb is None:
            return "#d0d0d0"
        return "#%02x%02x%02x" % tuple(int(c * 255) for c in rgb)

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
            markup = self._span(value, self._zone_hex(zone))
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
        # r086: no delta suffix — r070 removed arrows from the band but the
        # Basics cards kept appending the flat marker "·", leaving every
        # value rendering as "14% ·". Zone color only, per r070.
        if pct is None:
            value = self._span("—", "#888888")
        else:
            value = self._span(fmt % pct, self._zone_hex(zone))
        return frac, zone, value, caption, pct

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

        rows = mr.rank(self._last_procs, metric, mode="by_process", limit=4)
        if not rows:
            self._add_note(refs, "No contributors (—)")
            return

        fractions = contrib_fractions([r["value"] for r in rows])
        note = " · ranks by CPU" if metric == "load" else ""
        for i, (row, frac) in enumerate(zip(rows, fractions), 1):
            self._add_row(refs, i, row, metric, frac, note if i == 1 else "")

    def _add_note(self, refs, text):
        label = Gtk.Label()
        label.set_xalign(0)
        label.set_line_wrap(True)
        label.set_markup(self._span(text, "#888888"))
        layout.box_add(refs["contrib"], label, False, False, 0)
        label.show()
        refs["rows"].append(label)

    def _on_card_allocate(self, paned, allocation):
        """r108: the divider sits at the exact midline, always."""
        if allocation.width > 60:
            paned.set_position(allocation.width / 2.0)

    def _add_row(self, refs, rank, row, metric, frac, extra):
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        css.add_css_class(button, "basics-contrib-row")
        # r102: every contributor row is the same fixed height — variable
        # row heights were the remaining source of uneven card interiors.
        button.set_size_request(-1, 26)

        line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        rank_lbl = Gtk.Label(label="%d." % rank)
        rank_lbl.set_xalign(0)
        css.add_css_class(rank_lbl, "basics-contrib-rank")
        layout.box_add(line, rank_lbl, False, False, 0)

        name = Gtk.Label()
        name.set_xalign(0)
        name.set_use_markup(True)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        # r106: cap the natural — a long unit string used to claim ~450px
        # of natural request and skewed the card's left/right split.
        name.set_width_chars(30)
        name.set_max_width_chars(30)
        unit = (" <span size='small' foreground='#888888'>%s</span>"
                % _escape(row["unit"])) if row["unit"] else ""
        name.set_markup("%s%s%s" % (
            _escape(row["name"]), unit, self._span(extra, "#666666")))
        layout.box_add(line, name, True, True, 0)

        # Mini-bar proportional to the leader (mockup M), drawn via the seam.
        bar = charts.ChartArea(
            draw_func=lambda a, cr, w, h, f=frac, m=metric:
            self._draw_contrib_bar(cr, w, h, f, m))
        bar.set_size_request(110, 8)
        bar.set_valign(Gtk.Align.CENTER)
        layout.box_add(line, bar, False, False, 0)

        value = Gtk.Label()
        value.set_xalign(1)
        value.set_use_markup(True)
        css.add_css_class(value, "basics-contrib-val")
        # r090: pinned width — "499.6 MB" vs "0 B" used to breathe the row.
        value.set_width_chars(9)
        value.set_max_width_chars(9)
        value.set_ellipsize(Pango.EllipsizeMode.END)
        value.set_markup(self._span(
            _escape(self._value_text(metric, row["value"])), "#dddddd"))
        layout.box_add(line, value, False, False, 0)

        layout.set_child(button, line)
        for widget in (rank_lbl, name, bar, value, line):
            widget.show()
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

    def _draw_contrib_bar(self, cr, width, height, frac, metric):
        cr.set_source_rgb(*_CONTRIB_BAR_TROUGH)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        if frac <= 0:
            return
        cr.set_source_rgb(*_CONTRIB_BAR_RGB)
        cr.rectangle(0, 0, max(0.0, min(1.0, frac)) * width, height)
        cr.fill()


def _escape(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
