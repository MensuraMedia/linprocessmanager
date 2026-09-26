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
import time

from ui.compat import Gtk, GdkPixbuf, GLib, icons, css, events, layout

from pages.page_base import BasePage
from config.app_settings import AppSettings, COLUMN_KEYS
from ui import process_model as pm

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
        self._paused = False
        self._built = False

        self._sort_key = self.settings.get("sort", {}).get("column", "cpu")
        self._sort_desc = self.settings.get("sort", {}).get("direction") != "asc"

        self.model = pm.ProcessTableModel()
        self.model.set_sort(self._sort_key, self._sort_desc)
        self.model.set_scope(self.settings.get("scope_chip", "all"))
        self.model.set_show_kernel_threads(
            self.settings.get("show_kernel_threads", False))

        self.add_title("Processes")
        self._build_toolbar()
        self._build_statusbar()   # r055: info strip sits below the filter, above the header row
        self._build_notice()
        self._build_table()
        self._built = True

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
        "swap": "Swap", "disk_rw": "Disk r/w", "nice": "Nice", "pid": "PID",
        "state": "State",
    }
    _COLUMN_MINW = {
        "process": 200, "user": 90, "cpu": 70, "memory": 100, "swap": 90,
        "disk_rw": 120, "nice": 55, "pid": 75, "state": 80,
    }

    def _make_column(self, key):
        renderer = Gtk.CellRendererText()
        # Right-align the numeric columns.
        if key in ("cpu", "memory", "swap", "disk_rw", "nice", "pid"):
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
        elif key == "disk_rw":
            rh = model.get_value(it, pm.COL_DISK_R_HAS)
            wh = model.get_value(it, pm.COL_DISK_W_HAS)
            r = _fmt_rate(model.get_value(it, pm.COL_DISK_R)) if rh else "—"
            w = _fmt_rate(model.get_value(it, pm.COL_DISK_W)) if wh else "—"
            cell.set_property("text", "↓%s  ↑%s" % (r, w))
        elif key == "nice":
            has = model.get_value(it, pm.COL_NICE_HAS)
            cell.set_property(
                "text", str(model.get_value(it, pm.COL_NICE)) if has else "—")


    # -- strip formatting (r055: color-coded metrics) ---------------------

    _UP, _DOWN, _FLAT = "▲", "▼", "·"

    @staticmethod
    def _span(text, color):
        return "<span foreground='%s'>%s</span>" % (color, text)

    def _fmt_cpu(self, cpu, prev):
        """CPU: value + delta arrow. Rise green (more work), fall red (less) —
        standard increasing/decreasing convention per operator r055."""
        if cpu is None:
            return self._span("CPU —", "#888888")
        body = "CPU %d%%" % round(cpu)
        if prev is None or abs(cpu - prev) < 1.0:
            return self._span(body + " " + self._FLAT, "#d0d0d0")
        if cpu > prev:
            return self._span(body + " " + self._UP, "#7fd0a0")
        return self._span(body + " " + self._DOWN, "#e88a8a")

    @staticmethod
    def _mem_zone(pct_used):
        if pct_used is None:
            return None
        if pct_used >= 85:
            return "#e88a8a"   # high
        if pct_used >= 60:
            return "#e8c268"   # medium
        return "#7fd0a0"       # low

    # -- statusbar --------------------------------------------------------

    def _build_statusbar(self):
        self.status_label = Gtk.Label()
        self.status_label.set_xalign(0.5)
        self.status_label.set_hexpand(True)
        css.add_css_class(self.status_label, "page-subtitle")
        css.add_css_class(self.status_label, "status-strip")
        self.status_label.set_text("Starting sampler…")
        layout.box_add(self, self.status_label, False, False, 0)

    # -- sampler wiring (called by DashboardWindow after construction) ----

    def attach_sampler(self, sampler, app=None):
        """Bind the sampler + application, install the single drain source."""
        self.sampler = sampler
        self._app = app
        sampler.set_interval(self.settings.get("refresh_interval_s", 2.0))
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
        self._update_status(snapshot)
        self._update_notice()
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
        model = self.model
        parts = [self._span("%d processes" % model.last_shown, "#d0d0d0")]
        if model.last_total > model.last_shown:
            parts[0] = "%d of %d processes" % (model.last_shown, model.last_total)
        cpu = (snapshot.system or {}).get("cpu", {}).get("pct")
        prev_cpu = getattr(self, "_last_strip_cpu", None)
        self._last_strip_cpu = cpu
        parts.append(self._fmt_cpu(cpu, prev_cpu))
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
                                       self._mem_zone(used_pct) or "#d0d0d0"))
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
            self.sampler.stop()
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

    def _on_column_width(self, column, _pspec, key):
        if not self._built:
            return
        width = column.get_fixed_width()
        if width <= 0:
            return
        self.settings.set_column_width(key, width)
        self.settings.save()

    def _on_row_activated(self, _treeview, _path, _column):
        # Details pane is Phase 4; Enter just selects (the activation already
        # moved/kept selection here).
        pass

    # -- keyboard actions -------------------------------------------------

    def _action_filter_focus(self, _action, _param):
        self.search_entry.grab_focus()

    def _action_refresh(self, _action, _param):
        self._on_drain_tick()

    def _action_toggle_pause(self, _action, _param):
        self.pause_button.set_active(not self.pause_button.get_active())
