"""Processes page — the live, sortable, filterable process table (Phase 2c).

The first user-visible functionality: a typed :class:`Gtk.TreeView` fed by the
sampler through ONE GLib timeout source this page installs (r046 ruling — the
table layer owns the drain). Snapshots are consumed only via
``Sampler.drain_latest`` and applied with the diff-in-place engine in
``ui.process_model``; this page never reads ``/proc`` (boundary law) and every
toolkit call routes through ``ui.compat`` (raw-import + banned-API gates).

Spec: docs/modules/process-table.md + persistence-config.md. Details pane,
tree view, and actions are later phases (Enter just selects here).
"""

import os
import signal
import time
from collections import deque

from ui.compat import (Gtk, Gdk, GdkPixbuf, GLib, Gio, Pango, GTK_MAJOR,
                       icons, css, events, layout, menu, dialogs, charts)

from pages.page_base import BasePage
from config.app_settings import AppSettings, COLUMN_KEYS
from ui import process_model as pm
from modules import manager_actions as ma
from modules import manager_rank as mr
from log import get_logger, log_exception

log = get_logger("processes")

# The six band gauges in Variant-2 order (Load replaces the plain Processes
# tile). Labels shown; ranking/reading keyed by the metric.
_BAND_GAUGES = [
    ("cpu", "CPU"),
    ("memory", "Memory"),
    ("disk", "Disk I/O"),
    ("network", "Network"),
]  # r060: Swap and Load moved to the Graphs feature (sidebar)

# Cairo fill colors per capacity zone (mirror the page's _cap_zone hexes).
_ZONE_RGB = {
    mr.ZONE_NOMINAL: (0x7f / 255.0, 0xd0 / 255.0, 0xa0 / 255.0),
    mr.ZONE_MEDIUM: (0xe8 / 255.0, 0xc2 / 255.0, 0x68 / 255.0),
    mr.ZONE_NEAR: (0xe0 / 255.0, 0x4c / 255.0, 0x4c / 255.0),
}
_TROUGH_RGB = (0x3a / 255.0, 0x3a / 255.0, 0x3a / 255.0)

# ~5 min of net-rate history for the auto-scale ceiling (2x trailing max).
_NET_HISTORY_MAX = 600

# The honest, permanent per-process-network empty-state (spec §2). The cross-ref
# repoints at the Network hub card (Graphs) now that Resources is retired (r061).
_NET_EMPTY = ("per-process network not available from /proc — "
              "interface totals on the Network graph")

# Custom-signal picker presets (name shown; number is the action target).
_SIGNAL_PICKER = [
    ("SIGHUP", signal.SIGHUP), ("SIGINT", signal.SIGINT),
    ("SIGQUIT", signal.SIGQUIT), ("SIGUSR1", signal.SIGUSR1),
    ("SIGUSR2", signal.SIGUSR2), ("SIGTERM", signal.SIGTERM),
    ("SIGKILL", signal.SIGKILL),
]

# Renice presets — absolute niceness targets (unprivileged users may only
# increase niceness; the dialog states the rule before attempting).
_RENICE_PRESETS = [
    (1, "Niceness 1 (slightly lower priority)"),
    (5, "Niceness 5 (background)"),
    (10, "Niceness 10 (low priority)"),
    (19, "Niceness 19 (lowest priority)"),
]

# Phosphor subset (resources/icons/manifest.txt); loaded via the compat helper.
_ICON_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "resources", "icons")

# Drain poll cadence (ms). Independent of the sampler period: drain_latest
# returns None between samples, so we apply a snapshot only when a fresh one
# has arrived. One source, per r046.
_DRAIN_POLL_MS = 250

# Interval selector choices (label -> seconds), 0.5–5 s per the sampler bounds.
_INTERVAL_CHOICES = [("0.5s", 0.5), ("1s", 1.0), ("2s", 2.0),
                     ("3s", 3.0), ("5s", 5.0)]

_SCOPE_CHIPS = [("all", "All"), ("mine", "My processes"),
                ("system", "System"), ("active", "Active")]

_STATE_DESC = {
    "R": "Running", "S": "Sleeping", "D": "Disk sleep", "Z": "Zombie",
    "T": "Stopped", "t": "Traced", "I": "Idle", "X": "Dead", "K": "Wakekill",
}


def _load_icon_image(name, fill=False, size=16):
    """SVG → pixbuf → ``Gtk.Image`` via the compat helper, or ``None``.

    Never raises: a missing loader (no librsvg) or missing file degrades to a
    text-label button so the app always launches (acceptance #3).
    """
    subdir = "fill" if fill else "regular"
    filename = ("%s-fill.svg" % name) if fill else ("%s.svg" % name)
    path = os.path.join(_ICON_DIR, subdir, filename)
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, True)
    except Exception:  # noqa: BLE001 - any loader failure -> text fallback
        return None
    return icons.image_from_pixbuf(pixbuf)


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


class ProcessesPage(BasePage):
    """Live process table page."""

    def build_content(self):
        self.settings = AppSettings.load()
        self.sampler = None
        self._app = None
        self._drain_source_id = None
        self._width_save_id = None
        self._confirm_on_yes = None
        self._paused = False
        self._built = False
        self._action_msg_until = 0.0
        self._row_popover = None
        self._dialog = None
        self._menu_gesture = None

        # Metric band state (Variant 2). The band replaces the text strip; the
        # strip survives as a compact fallback behind basics.compact_strip.
        self._compact_strip = bool(self.settings.get("basics.compact_strip", False))
        self._gauges = {}          # metric -> widget refs
        self._gauge_state = {}     # metric -> {"fraction", "zone"}
        self._gauge_prev = {}      # metric -> previous scalar (delta arrows)
        self._net_history = deque(maxlen=_NET_HISTORY_MAX)
        self._last_procs = {}      # last snapshot procs (drives the popovers)
        self._last_system = {}
        # Observers fed each snapshot via the ONE drain source (r046) — the
        # Basics page subscribes here rather than draining the sampler itself.
        self._snapshot_observers = []

        self._sort_key = self.settings.get("sort", {}).get("column", "cpu")
        self._sort_desc = self.settings.get("sort", {}).get("direction") != "asc"

        self.model = pm.ProcessTableModel()
        self.model.set_sort(self._sort_key, self._sort_desc)
        self.model.set_scope(self.settings.get("scope_chip", "all"))
        self.model.set_show_kernel_threads(
            self.settings.get("show_kernel_threads", False))

        self.add_title("Processes")
        if not self._compact_strip:
            self._build_band()    # sits between title and filter row (mockup K v2)
        self._build_toolbar()
        if self._compact_strip:
            self._build_statusbar()   # r055 fallback: strip below the filter
        self._build_confirm_bar() # r065: inline confirm (no floating modal)
        self._fit_source_id = None
        self._fit_pending = False
        self._build_notice()
        self._build_table()
        self._build_row_actions()
        self._built = True

    # -- snapshot observers (single-drain law, r046) ----------------------

    def add_snapshot_observer(self, callback):
        """Register ``callback(snapshot)``, invoked on every applied snapshot.

        The Processes page owns the single GLib drain source; other pages
        (Basics) receive snapshots through here instead of draining the sampler
        a second time — no new sampling, no extra threads."""
        self._snapshot_observers.append(callback)

    # -- toolbar ----------------------------------------------------------

    def _build_toolbar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Filter by name  (Ctrl+F)")
        layout.box_add(bar, self.search_entry, True, True, 0)

        self.regex_toggle = Gtk.ToggleButton(label=".*")
        self.regex_toggle.set_tooltip_text("Treat the filter as a regular expression")
        layout.box_add(bar, self.regex_toggle, False, False, 0)

        # Scope chips (linked toggle group; radio-like, managed by hand).
        chip_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        css.add_css_class(chip_box, "linked")
        self._scope_buttons = {}
        active_scope = self.settings.get("scope_chip", "all")
        for scope, label in _SCOPE_CHIPS:
            btn = Gtk.ToggleButton(label=label)
            btn.set_active(scope == active_scope)
            layout.box_add(chip_box, btn, False, False, 0)
            self._scope_buttons[scope] = btn
        layout.box_add(bar, chip_box, False, False, 0)

        self.pause_button = Gtk.ToggleButton()
        self._set_pause_label()
        self.pause_button.set_tooltip_text("Pause / resume live updates  (F5)")
        layout.box_add(bar, self.pause_button, False, False, 0)

        self.refresh_button = self._icon_button(
            "arrow-clockwise", "Refresh", "Refresh now  (Ctrl+R)")
        layout.box_add(bar, self.refresh_button, False, False, 0)

        interval_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        clock_img = _load_icon_image("clock")
        if clock_img is not None:
            layout.box_add(interval_box, clock_img, False, False, 0)
        self.interval_combo = Gtk.ComboBoxText()
        current = self.settings.get("refresh_interval_s", 2.0)
        active_idx = 2
        for idx, (label, seconds) in enumerate(_INTERVAL_CHOICES):
            self.interval_combo.append_text(label)
            if abs(seconds - current) < 1e-6:
                active_idx = idx
        self.interval_combo.set_active(active_idx)
        self.interval_combo.set_tooltip_text("Refresh interval")
        layout.box_add(interval_box, self.interval_combo, False, False, 0)
        layout.box_add(bar, interval_box, False, False, 0)

        self.kthread_check = Gtk.CheckButton(label="Kernel threads")
        self.kthread_check.set_active(
            self.settings.get("show_kernel_threads", False))
        self.kthread_check.set_tooltip_text("Show kernel threads")
        layout.box_add(bar, self.kthread_check, False, False, 0)

        # Wire signals after initial values are set (no _loading guard needed).
        self.search_entry.connect("search-changed", self._on_search)
        self.regex_toggle.connect("toggled", self._on_search)
        for scope, btn in self._scope_buttons.items():
            btn.connect("toggled", self._on_scope_toggled, scope)
        self.pause_button.connect("toggled", self._on_pause_toggled)
        self.refresh_button.connect("clicked", self._on_refresh_clicked)
        self.interval_combo.connect("changed", self._on_interval_changed)
        self.kthread_check.connect("toggled", self._on_kthread_toggled)

        layout.box_add(self, bar, False, False, 0)

    def _icon_button(self, icon_name, fallback, tooltip, fill=False):
        button = Gtk.Button()
        button.set_tooltip_text(tooltip)
        image = _load_icon_image(icon_name, fill=fill)
        if image is not None:
            layout.set_child(button, image)
        else:
            button.set_label(fallback)
        return button

    def _set_pause_label(self):
        self.pause_button.set_label("Resume" if self._paused else "Pause")

    # -- notice bar (row budget) -----------------------------------------

    # -- inline confirm bar (r065 hang fix) --------------------------------

    def _build_confirm_bar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.confirm_bar = bar
        css.add_css_class(bar, "confirm-bar")
        self.confirm_label = Gtk.Label()
        self.confirm_label.set_xalign(0)
        self.confirm_label.set_hexpand(True)
        self.confirm_label.set_ellipsize(Pango.EllipsizeMode.END)
        layout.box_add(bar, self.confirm_label, True, True, 0)

        self.confirm_yes = Gtk.Button(label="Confirm")
        self.confirm_yes.connect("clicked", self._on_confirm_yes)
        layout.box_add(bar, self.confirm_yes, False, False, 0)

        self.confirm_no = Gtk.Button(label="Cancel")
        self.confirm_no.connect("clicked", self._on_confirm_no)
        layout.box_add(bar, self.confirm_no, False, False, 0)

        bar.set_no_show_all(True)
        bar.set_visible(False)
        layout.box_add(self, bar, False, False, 0)

    def _on_confirm_yes(self, _btn):
        was_visible = self.confirm_bar.get_visible()
        self.confirm_bar.set_visible(False)
        if was_visible and self._confirm_on_yes is not None:
            log.info("confirm accepted")
            callback, self._confirm_on_yes = self._confirm_on_yes, None
            callback()

    def _on_confirm_no(self, _btn):
        log.info("confirm cancelled")
        self.confirm_bar.set_visible(False)
        self._confirm_on_yes = None

    def _build_notice(self):
        self.notice_label = Gtk.Label()
        self.notice_label.set_xalign(0)
        css.add_css_class(self.notice_label, "warning")
        self.notice_label.set_no_show_all(True)  # visibility is ours to drive
        self.notice_label.set_visible(False)
        layout.box_add(self, self.notice_label, False, False, 0)

    # -- table ------------------------------------------------------------

    def _build_table(self):
        self.treeview = Gtk.TreeView(model=self.model.filter)
        self.treeview.set_enable_search(False)     # Ctrl+F drives our filter
        selection = self.treeview.get_selection()
        selection.set_mode(Gtk.SelectionMode.MULTIPLE)
        self.treeview.connect("row-activated", self._on_row_activated)

        widths = self.settings.get("columns", {}).get("widths", {})
        visible = self.settings.get("columns", {}).get("visible", list(COLUMN_KEYS))
        self._columns = {}
        for key in COLUMN_KEYS:
            column = self._make_column(key)
            column.set_visible(key in visible)
            if key in widths:
                column.set_fixed_width(int(widths[key]))
            column.connect("notify::fixed-width", self._on_column_width, key)
            self.treeview.append_column(column)
            self._columns[key] = column
        # All columns are FIXED-sized, so uniform-height mode is safe and keeps
        # the view responsive at the row budget (thousands of rows).
        self.treeview.set_fixed_height_mode(True)
        self._update_sort_indicators()

        # store re-sorts (header clicks) keep row references valid; nothing to
        # persist here because our header handler owns the sort setting.
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(360)
        layout.set_child(scrolled, self.treeview)
        layout.box_add(self, scrolled, True, True, 0)

    _COLUMN_TITLES = {
        "process": "Process", "user": "User", "cpu": "CPU %", "memory": "Memory",
        "swap": "Swap", "disk_read": "Reads", "disk_write": "Writes",
        "nice": "Nice", "pid": "PID", "state": "State",
    }
    _COLUMN_MINW = {
        "process": 200, "user": 90, "cpu": 70, "memory": 100, "swap": 90,
        "disk_read": 90, "disk_write": 90, "nice": 55, "pid": 75,
        "state": 80,
    }

    def _make_column(self, key):
        renderer = Gtk.CellRendererText()
        # Right-align the numeric columns.
        if key in ("cpu", "memory", "swap", "disk_read", "disk_write",
                   "nice", "pid"):
            renderer.set_property("xalign", 1.0)
        column = Gtk.TreeViewColumn(self._COLUMN_TITLES[key], renderer)
        column.set_resizable(True)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column.set_fixed_width(self._COLUMN_MINW[key])
        column.set_min_width(self._COLUMN_MINW[key])
        column.set_clickable(True)
        column.connect("clicked", self._on_header_clicked, key)
        column.set_cell_data_func(renderer, self._cell_data, key)
        return column

    def _cell_data(self, _column, cell, model, it, key):
        if key == "process":
            name = _escape(model.get_value(it, pm.COL_NAME))
            unit = model.get_value(it, pm.COL_UNIT)
            markup = name
            if model.get_value(it, pm.COL_IS_DEFUNCT):
                markup += " <span foreground='#c0392b'>(defunct)</span>"
            if unit:
                markup += " <span size='small' foreground='#888888'>%s</span>" % _escape(unit)
            if model.get_value(it, pm.COL_IS_KTHREAD):
                markup = "<span foreground='#888888' style='italic'>%s</span>" % markup
            cell.set_property("markup", markup)
            return
        if key == "state":
            state = model.get_value(it, pm.COL_STATE)
            text = _STATE_DESC.get(state, state)
            if state == "D":
                cell.set_property(
                    "markup", "<span foreground='#c0392b' weight='bold'>%s</span>" % _escape(text))
            elif state == "Z":
                cell.set_property(
                    "markup", "<span foreground='#888888'>%s</span>" % _escape(text))
            else:
                cell.set_property("markup", _escape(text))
            return
        if key == "user":
            cell.set_property("text", model.get_value(it, pm.COL_USER))
        elif key == "pid":
            cell.set_property("text", str(model.get_value(it, pm.COL_PID)))
        elif key == "cpu":
            has = model.get_value(it, pm.COL_CPU_HAS)
            cell.set_property(
                "text", "%.1f%%" % model.get_value(it, pm.COL_CPU) if has else "—")
        elif key == "memory":
            has = model.get_value(it, pm.COL_MEM_HAS)
            cell.set_property(
                "text", _fmt_bytes(model.get_value(it, pm.COL_MEM)) if has else "—")
        elif key == "swap":
            has = model.get_value(it, pm.COL_SWAP_HAS)
            cell.set_property(
                "text", _fmt_bytes(model.get_value(it, pm.COL_SWAP)) if has else "—")
        elif key == "disk_read":
            has = model.get_value(it, pm.COL_DISK_R_HAS)
            cell.set_property(
                "text", _fmt_rate(model.get_value(it, pm.COL_DISK_R))
                if has else "—")
        elif key == "disk_write":
            has = model.get_value(it, pm.COL_DISK_W_HAS)
            cell.set_property(
                "text", _fmt_rate(model.get_value(it, pm.COL_DISK_W))
                if has else "—")
        elif key == "nice":
            has = model.get_value(it, pm.COL_NICE_HAS)
            cell.set_property(
                "text", str(model.get_value(it, pm.COL_NICE)) if has else "—")


    # -- strip formatting (r055: color-coded metrics) ---------------------

    _UP, _DOWN, _FLAT = "▲", "▼", "·"

    @staticmethod
    def _span(text, color):
        return "<span foreground='%s'>%s</span>" % (color, text)

    _thresholds = None  # set via set_thresholds (r071); None = fixed defaults

    @classmethod
    def set_thresholds(cls, thresholds):
        cls._thresholds = thresholds

    @classmethod
    def _cap_zone(cls, pct, metric="cpu"):
        """Capacity threshold zones (r057, all stats): <60 nominal green,
        60-84 medium amber, >=85 near-capacity red."""
        if pct is None:
            return None
        if cls._thresholds is not None:
            zone = cls._thresholds.zone(metric, pct)
            return {"nominal": "#7fd0a0", "amber": "#e8c268",
                    "critical": "#e04c4c"}.get(zone, "#d0d0d0")
        if pct >= 85:
            return "#e04c4c"
        if pct >= 60:
            return "#e8c268"
        return "#7fd0a0"

    def _fmt_cpu(self, cpu, _prev=None):
        """CPU: threshold-colored value only (r070: delta arrows removed —
        advanced charts carry the trend)."""
        if cpu is None:
            return self._span("CPU —", "#888888")
        return self._span("CPU %d%%" % round(cpu),
                          self._cap_zone(cpu) or "#d0d0d0")

    # -- statusbar --------------------------------------------------------

    def _build_statusbar(self):
        self.status_label = Gtk.Label()
        self.status_label.set_xalign(0.5)
        self.status_label.set_hexpand(True)
        css.add_css_class(self.status_label, "page-subtitle")
        css.add_css_class(self.status_label, "status-strip")
        self.status_label.set_text("Starting sampler…")
        layout.box_add(self, self.status_label, False, False, 0)

    # -- metric band (r058/r059, Variant 2) -------------------------------

    def _build_band(self):
        """Six continuous-bar gauges below the title, each a cairo ChartArea fed
        by the snapshot stream. Clicking a gauge opens its top-10 popover."""
        band = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        css.add_css_class(band, "metric-band")

        gauges_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        gauges_row.set_homogeneous(True)   # equal-width gauges
        for metric, label in _BAND_GAUGES:
            gauges_row_child = self._build_gauge(metric, label)
            layout.box_add(gauges_row, gauges_row_child, True, True, 0)
        layout.box_add(band, gauges_row, False, True, 0)

        # Process counts + freshness (the strip's r058 visible_count semantics
        # now live here, below the gauges).
        self.band_meta = Gtk.Label()
        self.band_meta.set_xalign(0)
        css.add_css_class(self.band_meta, "band-meta")
        layout.box_add(band, self.band_meta, False, False, 0)

        # A thin line for transient action results (SIGTERM sent, etc.) — the
        # gauges keep updating independently of this message.
        self.status_label = Gtk.Label()
        self.status_label.set_xalign(0)
        css.add_css_class(self.status_label, "status-strip")
        layout.box_add(band, self.status_label, False, False, 0)

        layout.box_add(self, band, False, False, 0)

    def _build_gauge(self, metric, label):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        css.add_css_class(box, "band-gauge")

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        name = Gtk.Label(label=label)
        name.set_xalign(0)
        css.add_css_class(name, "gauge-k")
        value = Gtk.Label()
        value.set_xalign(1)
        value.set_hexpand(True)
        value.set_halign(Gtk.Align.END)
        css.add_css_class(value, "gauge-v")
        value.set_markup(self._span("—", "#888888"))
        # r060 defect fix: variable-width value text changed the gauge's
        # minimum requisition, so cards expanded/contracted with the bar.
        # Pin the text width (ellipsis) — cards stay fixed; only the bar moves.
        value.set_width_chars(11)        # r086: fixed requisition (§5b)
        value.set_max_width_chars(11)    # r079 cap kept
        value.set_ellipsize(Pango.EllipsizeMode.END)
        layout.box_add(head, name, False, False, 0)
        layout.box_add(head, value, True, True, 0)
        layout.box_add(box, head, False, False, 0)

        area = charts.ChartArea(
            draw_func=lambda a, cr, w, h, m=metric: self._draw_gauge(cr, w, h, m))
        area.set_size_request(-1, 10)
        area.set_hexpand(True)
        area.set_tooltip_text(
            _NET_EMPTY if metric == "network" else "Double-click for Basics")
        layout.box_add(box, area, False, True, 0)

        caption = Gtk.Label()
        caption.set_xalign(0)
        caption.set_width_chars(26)      # r086: fixed requisition (§5b)
        caption.set_max_width_chars(26)
        caption.set_ellipsize(Pango.EllipsizeMode.END)
        layout.box_add(box, caption, False, False, 0)

        # r090 (operator): DOUBLE-click opens Basics — a single click on a
        # gauge is too easy to fire while scanning the table.
        gesture = events.click_gesture(
            area, lambda g, n, x, y, m=metric: self._on_gauge_pressed(m),
            button=1, min_press=2)

        self._gauge_state[metric] = {"fraction": None, "zone": None}
        self._gauges[metric] = {
            "value": value, "caption": caption, "area": area, "gesture": gesture,
        }
        return box

    def _draw_gauge(self, cr, width, height, metric):
        cr.set_source_rgb(*_TROUGH_RGB)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.14)   # threshold ticks at 60/85 (Variant 2)
        for tick in (0.60, 0.85):
            cr.rectangle(tick * width, 0, 1, height)
            cr.fill()
        state = self._gauge_state.get(metric) or {}
        frac = state.get("fraction")
        if frac is None:
            return
        rgb = _ZONE_RGB.get(state.get("zone"), _ZONE_RGB[mr.ZONE_NOMINAL])
        cr.set_source_rgb(*rgb)
        cr.rectangle(0, 0, max(0.0, min(1.0, frac)) * width, height)
        cr.fill()

    def _update_band(self, snapshot):
        system = snapshot.system or {}
        self._last_procs = snapshot.procs or {}
        self._last_system = system

        net = mr.net_reading(system)
        if not snapshot.from_backoff and net["total"] is not None:
            self._net_history.append(net["total"])
        ceiling = mr.network_ceiling(
            max(self._net_history) if self._net_history else None)

        for metric, _label in _BAND_GAUGES:
            frac, zone, value_markup, caption, scalar = self._read_gauge(
                metric, system, ceiling, net)
            refs = self._gauges[metric]
            refs["value"].set_markup(value_markup)
            refs["caption"].set_text(caption)
            self._gauge_state[metric] = {"fraction": frac, "zone": zone}
            refs["area"].queue_draw()
            self._gauge_prev[metric] = scalar

        self._update_band_meta(snapshot)

    def _update_band_meta(self, snapshot):
        model = self.model
        visible = model.visible_count()
        if model.last_total > model.last_shown:
            head = "%d of %d processes" % (model.last_shown, model.last_total)
        elif visible < model.last_total:
            head = "%d of %d processes shown" % (visible, model.last_total)
        else:
            head = "%d processes" % model.last_total
        parts = [head]
        if model.last_kthreads_hidden:
            parts.append("%d kernel threads hidden" % model.last_kthreads_hidden)
        if snapshot.from_backoff:
            parts.append("backoff")
        parts.append("updated " + time.strftime("%H:%M:%S"))
        self.band_meta.set_markup(
            self._span("  ·  ".join(_escape(p) for p in parts), "#888888"))

    # -- band gauge readings + formatting ---------------------------------

    def _zone_hex(self, zone):
        rgb = _ZONE_RGB.get(zone)
        if rgb is None:
            return "#d0d0d0"
        return "#%02x%02x%02x" % tuple(int(c * 255) for c in rgb)

    def _pct_gauge(self, metric, pct, fmt, caption, threshold):
        # r070: delta arrows removed — the threshold-colored value + the live
        # bar carry the trend (operator note).
        frac = None if pct is None else max(0.0, min(1.0, pct / 100.0))
        zone = self._cap_zone(pct)
        if pct is None:
            value = self._span("—", "#888888")
        else:
            value = self._span(fmt % pct, self._zone_hex(zone))
        return frac, zone, value, caption, pct

    def _read_gauge(self, metric, system, ceiling, net):
        """Return ``(fraction, zone, value_markup, caption, scalar)`` for a
        gauge from the frozen ``system`` schema."""
        if metric == "cpu":
            pct = mr.cpu_reading(system)["pct"]
            return self._pct_gauge("cpu", pct, "%d%%", "0 · 60 · 85 · 100", 1.0)
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
            cap = "util · busiest: %s" % (r["busiest"] or "—")
            return self._pct_gauge("disk", r["pct"], "%.1f%%", cap, 1.0)
        if metric == "network":
            total = net["total"]
            frac = mr.fraction(total, ceiling)
            zone = (mr.capacity_zone((frac or 0.0) * 100.0)
                    if total is not None else None)
            markup = self._span(_fmt_rate(total), self._zone_hex(zone))
            cap = "↓%s ↑%s · ceiling %s" % (
                _fmt_rate(net["rx"]), _fmt_rate(net["tx"]), _fmt_rate(ceiling))
            return frac, zone, markup, cap, total
        # load — probe-first "—" until /proc/loadavg joins the readers.
        ncpu = mr.load_reading(system)["ncpu"] or 0
        return None, None, self._span("—", "#888888"), "1 min · cores: %d" % ncpu, None

    # -- band click-through (r081) ----------------------------------------

    def _on_gauge_pressed(self, metric):
        # r081/r092 (operator): a band-chart DOUBLE-click opens the Graphs
        # hub, whose TOP section now hosts the Basics cards (the standalone
        # Basics page and the sidebar submenu were retired in r092).
        if self._app is not None:
            self._app.navigation_manager.navigate_to("graphs")

    def select_process(self, key):
        """Public entry (Basics jump): select ``key`` ((pid, starttime)) in the
        table and scroll it into view."""
        self._select_and_scroll(key)

    def _select_and_scroll(self, key):
        store_key = (key[0], key[1] if key[1] is not None else 0)
        child = self.model.child_path_for_key(store_key)
        if child is None:
            self._render_action("That process is no longer running", True)
            return
        path = self.model.filter.convert_child_path_to_path(child)
        if path is None:
            self._render_action(
                "That process is filtered out of the current view", True)
            return
        selection = self.treeview.get_selection()
        selection.unselect_all()
        selection.select_path(path)
        self.treeview.scroll_to_cell(path, None, True, 0.5, 0.0)
        self.treeview.grab_focus()

    # -- sampler wiring (called by DashboardWindow after construction) ----

    def attach_sampler(self, sampler, app=None):
        """Bind the sampler + application, install the single drain source."""
        self.sampler = sampler
        self._app = app
        sampler.set_interval(self.settings.get("refresh_interval_s", 2.0))
        toplevel = self.get_toplevel()
        if toplevel is not self:
            toplevel.connect("check-resize", self._on_toplevel_resize)
        self._register_actions(app)
        if self._drain_source_id is None:
            self._drain_source_id = GLib.timeout_add(
                _DRAIN_POLL_MS, self._on_drain_tick)

    def _register_actions(self, app):
        if app is None:
            return
        specs = [
            ("filter-focus", self._action_filter_focus, ["<Primary>f"]),
            ("refresh-now", self._action_refresh, ["<Primary>r"]),
            ("toggle-pause", self._action_toggle_pause, ["F5"]),
        ]
        for name, callback, accels in specs:
            if app.lookup_action(name) is None:
                action = events.make_action(name, callback)
                app.add_action(action)
                events.set_accels(app, "app.%s" % name, accels)

    # -- the one idle/timeout drain source -------------------------------

    def _on_drain_tick(self):
        if self.sampler is None:
            return True
        snapshot = self.sampler.drain_latest()
        if snapshot is None:
            return True
        selected = self._capture_selection()
        self.model.apply_snapshot(snapshot.procs)
        self._restore_selection(selected)
        if self._compact_strip:
            self._update_status(snapshot)
        else:
            self._update_band(snapshot)
        self._update_notice()
        # Fan the snapshot out to observers (Basics) through the single drain.
        for observer in self._snapshot_observers:
            try:
                observer(snapshot)
            except Exception:  # noqa: BLE001 - one page must not break another
                pass
        return True  # keep the source alive

    # -- selection identity ----------------------------------------------

    def _capture_selection(self):
        selection = self.treeview.get_selection()
        _model, paths = selection.get_selected_rows()
        keys = []
        for path in paths:
            child = self.model.filter.convert_path_to_child_path(path)
            if child is not None:
                keys.append(self.model.key_at_child_path(child))
        return keys

    def _restore_selection(self, keys):
        selection = self.treeview.get_selection()
        selection.unselect_all()
        for key in keys:
            child = self.model.child_path_for_key(key)
            if child is None:
                continue
            path = self.model.filter.convert_child_path_to_path(child)
            if path is not None:
                selection.select_path(path)

    # -- status + notice --------------------------------------------------

    def _update_status(self, snapshot):
        # Hold a just-rendered action result on the strip for a few seconds so
        # it is not immediately overwritten by the next snapshot (r039 wording
        # must be readable — and screenshot-able during live verification).
        if time.monotonic() < self._action_msg_until:
            return
        model = self.model
        visible = model.visible_count()  # r058 P2-6: reflect scope+filter
        parts = [self._span("%d of %d processes shown" % (visible, model.last_total)
                            if visible < model.last_total else
                            "%d processes" % model.last_total, "#d0d0d0")]
        if model.last_total > model.last_shown:
            parts[0] = "%d of %d processes" % (model.last_shown, model.last_total)
        cpu = (snapshot.system or {}).get("cpu", {}).get("pct")
        parts.append(self._fmt_cpu(cpu))
        if model.last_kthreads_hidden:
            parts.append(self._span("%d kernel threads hidden" % model.last_kthreads_hidden, "#888888"))
        if snapshot.from_backoff:
            parts.append("backoff")
        parts.append(self._span("updated " + time.strftime("%H:%M:%S"), "#888888"))
        mem = (snapshot.system or {}).get("mem") or {}
        total, avail = mem.get("total"), mem.get("available")
        if total and avail:
            used_pct = 100.0 * (total - avail) / total
            parts.insert(1, self._span("Mem %d%%" % round(used_pct),
                                       self._cap_zone(used_pct) or "#d0d0d0"))
        self.status_label.set_markup("  ·  ".join(parts))

    def _update_notice(self):
        model = self.model
        if model.last_total > model.last_shown:
            self.notice_label.set_text(
                "Showing %d of %d — refine the filter or coarsen the interval "
                "to see more." % (model.last_shown, model.last_total))
            self.notice_label.set_visible(True)
        else:
            self.notice_label.set_visible(False)

    # -- signal handlers --------------------------------------------------

    def _on_search(self, *_args):
        self.model.set_query(
            self.search_entry.get_text(), regex=self.regex_toggle.get_active())

    def _on_scope_toggled(self, button, scope):
        if not button.get_active():
            # Keep at least one chip active (radio semantics).
            if not any(b.get_active() for b in self._scope_buttons.values()):
                button.set_active(True)
            return
        for other_scope, other in self._scope_buttons.items():
            if other_scope != scope and other.get_active():
                other.set_active(False)
        self.model.set_scope(scope)
        self.settings.set_scope(scope)
        self.settings.save()

    def _on_pause_toggled(self, button):
        self._set_paused(button.get_active())

    def _set_paused(self, paused):
        self._paused = paused
        self._set_pause_label()
        if self.pause_button.get_active() != paused:
            self.pause_button.set_active(paused)
        if self.sampler is None:
            return
        if paused:
            self.sampler.stop(timeout=1.0)  # r058 P2-4: never block the UI thread
        else:
            self.sampler.start()

    def _on_refresh_clicked(self, _button):
        self._on_drain_tick()

    def _on_interval_changed(self, combo):
        idx = combo.get_active()
        if idx < 0:
            return
        seconds = _INTERVAL_CHOICES[idx][1]
        if self.sampler is not None:
            self.sampler.set_interval(seconds)
        self.settings.set_interval(seconds)
        self.settings.save()

    def _on_kthread_toggled(self, check):
        show = check.get_active()
        self.model.set_show_kernel_threads(show)
        self.settings.set_show_kernel_threads(show)
        self.settings.save()

    def _on_header_clicked(self, _column, key):
        if self._sort_key == key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key = key
            self._sort_desc = True
        self.model.set_sort(key, self._sort_desc)
        self._update_sort_indicators()
        self.settings.set_sort(key, "desc" if self._sort_desc else "asc")
        self.settings.save()

    def _update_sort_indicators(self):
        order = Gtk.SortType.DESCENDING if self._sort_desc else Gtk.SortType.ASCENDING
        for key, column in self._columns.items():
            active = key == self._sort_key
            column.set_sort_indicator(active)
            if active:
                column.set_sort_order(order)

    def _on_toplevel_allocate(self, toplevel, allocation):
        """r077: proportional column-fit — when the window is narrower than
        the persisted column widths, scale them down (never below 60px) so
        the table always fits the window width. Runs debounced."""
        if self._built:
            self._fit_columns_to_width()

    def _fit_columns_to_width(self):
        tv_width = max(120, self.treeview.get_allocated_width() - 20)
        visible = [c for k, c in self._columns.items() if c.get_visible()]
        if not visible:
            return
        current = sum(c.get_width() or c.get_fixed_width() or 100
                      for c in visible)
        if current <= tv_width:
            return  # fits — leave persisted widths alone
        scale = tv_width / current
        for c in visible:
            w = c.get_width() or 100
            c.set_fixed_width(max(60, int(w * scale)))

    def _on_toplevel_resize(self, _toplevel):
        # r077: debounce proportional column fit
        if self._fit_source_id is not None:
            GLib.source_remove(self._fit_source_id)
        self._fit_source_id = GLib.timeout_add(250, self._fit_columns_to_width)
        return False

    def _on_column_width(self, column, _pspec, key):
        if not self._built:
            return
        width = column.get_fixed_width()
        if width <= 0:
            return
        self.settings.set_column_width(key, width)
        # r058 close-review P1: notify::fixed-width fires continuously during
        # a drag — debounce to one atomic save after motion settles.
        if self._width_save_id is not None:
            GLib.source_remove(self._width_save_id)
        self._width_save_id = GLib.timeout_add(500, self._flush_width_save)

    def _flush_width_save(self):
        self._width_save_id = None
        self.settings.save()
        return False

    def _on_row_activated(self, _treeview, _path, _column):
        # Details pane is Phase 4; Enter just selects (the activation already
        # moved/kept selection here).
        pass

    # -- context menu + action surface (Phase 3) --------------------------

    def _build_row_actions(self):
        """Stand up the row action group, the Gio.Menu model, and the
        right-click gesture. Every action acts on the current (multi-)selection
        via ``(pid, starttime)`` keys; destructive ones confirm per
        actions-permissions.md. All wiring is model + adapter (compat seams)."""
        group = Gio.SimpleActionGroup()
        self._proc_actions = group

        # Plain signal actions.
        for name, handler in (
            ("stop", lambda a, p: self._do_signal("stop")),
            ("continue", lambda a, p: self._do_signal("continue")),
            ("end", lambda a, p: self._do_signal("end")),
            ("kill", lambda a, p: self._do_signal("kill")),
            ("hangup", lambda a, p: self._do_signal("hangup")),
            ("end-group", lambda a, p: self._do_group("end")),
            ("kill-group", lambda a, p: self._do_group("kill")),
            ("copy-pid", lambda a, p: self._act_copy_pid()),
            ("copy-cmdline", lambda a, p: self._act_copy_cmdline()),
        ):
            group.add_action(events.make_action(name, handler))

        # Parameterised actions (menu items carry the target value).
        int_t = GLib.VariantType.new("i")
        str_t = GLib.VariantType.new("s")
        group.add_action(events.make_action(
            "signal", lambda a, p: self._do_signal("signal", signum=p.get_int32()),
            int_t))
        group.add_action(events.make_action(
            "renice", lambda a, p: self._act_renice(p.get_int32()), int_t))
        group.add_action(events.make_action(
            "affinity", lambda a, p: self._act_affinity(p.get_string()), str_t))

        # Phase-4 placeholders: present but always disabled (grayed) so the
        # menu shows the full surface without pretending to wire it yet.
        for name in ("tree", "frequency", "journal", "open-location"):
            action = events.make_action(name, lambda a, p: None)
            action.set_enabled(False)
            group.add_action(action)

        self.treeview.insert_action_group("proc", group)
        self._row_menu_model = self._build_row_menu_model()
        self._menu_gesture = events.click_gesture(
            self.treeview, self._on_row_menu, button=3)

    def _build_row_menu_model(self):
        model = Gio.Menu()

        nav = Gio.Menu()
        nav.append("Show in tree (Phase 4)", "proc.tree")
        nav.append("Copy PID", "proc.copy-pid")
        nav.append("Copy command line", "proc.copy-cmdline")
        model.append_section(None, nav)

        signals = Gio.Menu()
        signals.append("Stop (SIGSTOP)", "proc.stop")
        signals.append("Continue (SIGCONT)", "proc.continue")
        signals.append("End (SIGTERM)", "proc.end")
        signals.append("Kill (SIGKILL)", "proc.kill")
        signals.append("Hang up (SIGHUP)", "proc.hangup")

        groups = Gio.Menu()
        groups.append("End group — children too", "proc.end-group")
        groups.append("Kill group — children too", "proc.kill-group")
        model.append_section(None, groups)
        picker = Gio.Menu()
        for label, num in _SIGNAL_PICKER:
            picker.append("%s (%d)" % (label, int(num)),
                          "proc.signal(%d)" % int(num))
        signals.append_submenu("Send signal…", picker)
        model.append_section(None, signals)

        tuning = Gio.Menu()
        renice = Gio.Menu()
        for value, label in _RENICE_PRESETS:
            renice.append(label, "proc.renice(%d)" % value)
        tuning.append_submenu("Change priority (renice)…", renice)
        affinity = Gio.Menu()
        affinity.append("All CPUs", "proc.affinity('all')")
        affinity.append("First CPU only", "proc.affinity('first')")
        tuning.append_submenu("Set CPU affinity…", affinity)
        model.append_section(None, tuning)

        later = Gio.Menu()
        later.append("Frequency… (Phase 4)", "proc.frequency")
        later.append("View journal for unit… (Phase 4)", "proc.journal")
        later.append("Open executable location… (Phase 4)", "proc.open-location")
        model.append_section(None, later)
        return model

    def _open_column_chooser(self, x, y):
        """Right-click on the column headers: add/remove columns (r075)."""
        popover = Gtk.Popover()
        popover.set_relative_to(self.treeview)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(10); box.set_margin_bottom(10)
        box.set_margin_start(12); box.set_margin_end(12)
        head = Gtk.Label(label="Visible columns")
        head.set_xalign(0)
        css.add_css_class(head, "gauge-k")
        layout.box_add(box, head, False, False, 0)
        for key in COLUMN_KEYS:
            column = self._columns.get(key)
            if column is None:
                continue
            check = Gtk.CheckButton(label=self._COLUMN_TITLES[key])
            check.set_active(column.get_visible())
            check.connect("toggled", self._on_column_toggled, key)
            layout.box_add(box, check, False, False, 0)
        layout.set_child(popover, box)  # GTK3 add / GTK4 set_child
        rectangle = Gdk.Rectangle()
        rectangle.x, rectangle.y = int(x), int(y)
        popover.set_pointing_to(rectangle)
        popover.popup()
        self._column_popover = popover  # keep alive

    def _on_column_toggled(self, check, key):
        column = self._columns.get(key)
        if column is None:
            return
        column.set_visible(check.get_active())
        visible = [k for k, col in self._columns.items() if col.get_visible()]
        self.settings.set("columns", {
            "visible": visible,
            "widths": self.settings.get("columns", {}).get("widths", {})})
        self.settings.save()

    def _on_row_menu(self, _gesture, _n_press, x, y):
        # r075: a right-click over the COLUMN HEADER opens the column
        # chooser; only right-clicks on data rows open the process menu.
        # r081 fix (operator report): the header test used WIDGET coords,
        # but GTK3's get_path_at_pos expects BIN-WINDOW coords — a header
        # click slid into the first data row, returned a path, and the
        # header opened the PROCESS menu instead of the chooser. _path_at
        # does the conversion; None now reliably means "no row" (header
        # band, or the empty margin beside the last column).
        path = self._path_at(x, y)
        if path is None:
            self._open_column_chooser(x, y)
            return
        # Right-click selects the row under the pointer unless it is already
        # part of a multi-selection (then the menu acts on the whole set).
        selection = self.treeview.get_selection()
        if path is not None and not selection.path_is_selected(path):
            selection.unselect_all()
            selection.select_path(path)
        targets = self._selected_targets()
        self._update_menu_sensitivity(targets)
        self._popup_menu(x, y)

    def _path_at(self, x, y):
        try:
            if GTK_MAJOR >= 4:
                res = self.treeview.get_path_at_pos(int(x), int(y))
            else:
                bx, by = self.treeview.convert_widget_to_bin_window_coords(
                    int(x), int(y))
                res = self.treeview.get_path_at_pos(bx, by)
        except Exception:  # noqa: BLE001 - a miss just means no row was hit
            return None
        return res[0] if res else None

    def _popup_menu(self, x, y):
        popover = menu.model_popover(self._row_menu_model, relative_to=self.treeview)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        self._row_popover = popover  # keep a reference alive
        popover.popup()

    def _update_menu_sensitivity(self, targets):
        def enable(name, on):
            action = self._proc_actions.lookup_action(name)
            if action is not None:
                action.set_enabled(on)

        if not targets:
            for name in ("stop", "continue", "end", "kill", "hangup", "signal",
                         "end-group", "kill-group",
                         "renice", "affinity", "copy-pid", "copy-cmdline"):
                enable(name, False)
            return
        # Signal feasibility is uniform across the signal items (a zombie or a
        # departed PID disables them all); "end" stands in as a signal action.
        sig_ok, _ = ma.feasibility_many("end", targets)
        for name in ("stop", "continue", "end", "kill", "hangup", "signal",
                     "end-group", "kill-group"):
            enable(name, sig_ok)
        enable("renice", ma.feasibility_many("renice", targets)[0])
        enable("affinity", ma.feasibility_many("affinity", targets)[0])
        enable("copy-pid", True)
        enable("copy-cmdline", True)

    # -- action execution -------------------------------------------------

    def _selected_keys(self):
        return self._capture_selection()

    def _selected_targets(self):
        # Fresh /proc/<pid>/stat read per key at click time (the recycle guard).
        return [ma.probe(key) for key in self._selected_keys()]

    def _do_signal(self, action, signum=None):
        try:
            self._do_signal_inner(action, signum)
        except Exception as e:
            get_logger("actions").error(
                "%s", log_exception("action %s" % action, e))

    def _do_signal_inner(self, action, signum=None):
        targets = self._selected_targets()
        if not targets:
            return

        def run():
            results = ma.signal_results(action, targets, signum=signum)
            self._render_action(
                ma.render_signal(action, results, signum),
                ma.has_failure(results))

        need = ma.needs_confirm(action, targets, self.settings)
        message = ma.confirm_message(action, targets)
        label = action.capitalize()
        if action == "signal":
            # The picker can send SIGKILL/SIGTERM — confirm those like the
            # dedicated Kill/End actions do.
            label = "Send"
            message = "Send %s to the selected process(es)?" % ma.signame(signum)
            if signum in (signal.SIGKILL, signal.SIGTERM):
                need = True
        if need:
            self._confirm(message, run, confirm_label=label)
        else:
            run()

    def _act_renice(self, value):
        targets = self._selected_targets()
        if not targets:
            return
        target = targets[0]  # renice is single-target (spec: renice(key, value))

        def run():
            result = ma.renice(target, value)
            self._render_action(
                ma.render_renice(result, value), ma.has_failure(result))

        # Always dialog first — it states the permission rule before attempting.
        self._confirm(ma.renice_message(target, value), run, confirm_label="Set")

    def _act_affinity(self, which):
        targets = self._selected_targets()
        if not targets:
            return
        target = targets[0]
        ncpu = os.cpu_count() or 1
        cpus = list(range(ncpu)) if which == "all" else [0]

        def run():
            result = ma.set_affinity(target, cpus)
            self._render_action(
                ma.render_affinity(result, cpus), ma.has_failure(result))

        self._confirm(ma.affinity_message(target, cpus), run, confirm_label="Pin")

    def _act_copy_pid(self):
        keys = self._selected_keys()
        if not keys:
            return
        self._copy_text(" ".join(str(key[0]) for key in keys))
        self._render_action(
            "Copied PID%s to clipboard" % ("s" if len(keys) > 1 else ""), False)

    def _act_copy_cmdline(self):
        keys = self._selected_keys()
        if not keys:
            return
        text = ma.command_line(keys[0])  # kernel read stays in the actions layer
        if not text:
            self._render_action("No command line (kernel thread or restricted)",
                                True)
            return
        self._copy_text(text)
        self._render_action("Copied command line to clipboard", False)

    def _copy_text(self, text):
        if GTK_MAJOR >= 4:
            self.treeview.get_clipboard().set(text)
        else:
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(text, -1)

    def _confirm(self, message, on_confirm, confirm_label="Confirm"):
        """Inline confirmation bar (r065 hang fix).

        The floating modal window mapped behind the active window on this
        desktop while holding a modal grab — the app looked hung. An in-page
        bar cannot be hidden by window stacking and cannot block input.
        The text strip below the table renders the same message as backup."""
        log.info("confirm requested: %s", message)
        self._confirm_on_yes = on_confirm
        self.confirm_label.set_markup(
            self._span(_escape(message), "#e8c268"))
        self.confirm_bar.set_visible(True)
        self.confirm_yes.set_label(confirm_label)

    def _toplevel_window(self):
        try:
            if GTK_MAJOR >= 4:
                root = self.get_root()
            else:
                root = self.get_toplevel()
        except Exception:  # noqa: BLE001 - fall back to an untethered window
            return None
        return root if isinstance(root, Gtk.Window) else None

    def _render_action(self, message, failed):
        color = "#e8c268" if failed else "#7fd0a0"
        icon = self._span("⚠", "#e8c268") + " " if failed else ""
        self.status_label.set_markup(icon + self._span(_escape(message), color))
        self._action_msg_until = time.monotonic() + 6.0

    # -- group termination (r074) -----------------------------------------

    def _do_group(self, action):
        """End/Kill the selected process plus its whole descendant tree.

        Runs in a background thread: collection from the newest snapshot,
        TERM -> liveness verify (grace polls) -> SIGKILL escalation ->
        final verify. The UI thread only renders the result (r074)."""
        try:
            targets = self._selected_targets()
            if not targets:
                return
            root = targets[0]
            root_key = (root.pid, root.key_starttime)
            # fresh collection behind the actions API — never a cached
            # snapshot, never procfs in the page (boundary law)
            count, names = ma.group_overview(root_key)
            message = ("%s the selected process tree — %d processes incl. "
                       "children of %s? Processes that ignore SIGTERM are "
                       "escalated to SIGKILL after the grace period."
                       % ("End" if action == "end" else "Kill",
                          count, root.name))
            self._confirm(message, lambda: self._run_group(action, root_key,
                                                           root.name),
                          confirm_label="End tree" if action == "end"
                          else "Kill tree")
        except Exception as e:
            from log import get_logger
            get_logger("actions").error(
                "%s", log_exception("group %s" % action, e))

    def _run_group(self, action, root_key, root_name):
        """Background-thread worker: verify-and-escalate loop."""
        import threading as _threading

        def work():
            summary = ma.group_terminate(
                "end-group" if action == "end" else "kill-group",
                root_key, root_name, None, signum=15 if action == "end" else 9,
                grace_attempts=6,
                poll=lambda: time.sleep(0.5),
                probe_func=lambda key: ma.probe(key),
                kill_func=os.kill)
            GLib.idle_add(self._render_group_result, summary)

        _threading.Thread(target=work, daemon=True).start()

    def _render_group_result(self, summary):
        text = ma.group_summary_text(summary)
        failed = bool(summary["survivors"])
        color = "#e8c268" if failed else "#7fd0a0"
        self.status_label.set_markup(
            self._span(_escape(text), color))
        self._action_msg_until = time.monotonic() + 8.0
        return False

    # -- keyboard actions -------------------------------------------------

    def _action_filter_focus(self, _action, _param):
        self.search_entry.grab_focus()

    def _action_refresh(self, _action, _param):
        self._on_drain_tick()

    def _action_toggle_pause(self, _action, _param):
        self.pause_button.set_active(not self.pause_button.get_active())
