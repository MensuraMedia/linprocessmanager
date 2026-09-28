"""Network page (r113) — processes actively using the network, live.

One row per process with socket-owner attribution (r053 model — a labelled
proportional estimate, never kernel accounting; restricted pids under Yama
render lock + "—"). Every column is sortable (header click toggles
direction; unknowns sort last in both directions per the process-table
convention). Rows update in place from the shared snapshot stream — the
Processes page owns the single drain and forwards snapshots here.

Boundary law: consumes snapshot records + the sampler's public
``open_sockets()`` summary; never reads /proc directly.
"""

import time

from ui.compat import (Gtk, GLib, Gdk, GdkPixbuf, Gio, Pango, css, layout,
                       charts, events, menu)

from pages.page_base import BasePage
from modules import manager_netwatch

_ACCENT = (0x00 / 255.0, 0x78 / 255.0, 0xD7 / 255.0)
_TROUGH = (0x1b / 255.0, 0x1b / 255.0, 0x1b / 255.0)

_COLS = [
    # (store col, title, kind)  kind: text | rate | int | bar
    (0, "Process", "text"),
    (1, "User", "text"),
    (2, "Conns", "int"),
    (3, "↓ Rx/s", "rate"),
    (4, "↑ Tx/s", "rate"),
    (8, "Tx ← → Rx", "bar"),      # r129: the packet-tick bar, in front of Total
    (5, "Total/s", "rate"),
]
_COL_BAR = 6                    # store column holding the rendered bar pixbuf
_COL_KEY_PID = 7
_COL_KEY_START = 8
_BAR_W, _BAR_H = 160, 12       # Disks geometry (r129 unification)
_TICK = 5                      # px per packet tick (3px tick + 2px gap)
_TICKS_PER_HALF = _BAR_W // 2 // _TICK   # 16 packets per half
_TICK_START_BYTES = 64.0       # r134: the first tick measures 64 B/s


def _byte_ticks(value, half_ticks=_TICKS_PER_HALF):
    """Packet-tick count for a byte-rate, in Bytes/KB increments.

    Each tick is a fixed byte step (64 B/s, 128 B/s, 256 B/s … doubling)
    chosen so the busiest side fits ``half_ticks`` — ticks literally count
    byte increments (the digital packet representation). Nonzero rates
    render at least one tick.
    """
    if value is None or value <= 0:
        return 0
    quantum = _TICK_START_BYTES
    while value / quantum > half_ticks and quantum < 2.0 ** 40:
        quantum *= 2.0
    return max(1, min(half_ticks, int(round(value / quantum))))


def _fmt_rate(value):
    if value is None or value < 0:
        return "—"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            if unit == "B":
                return "%d B/s" % int(size)
            return "%.1f %s/s" % (size, unit)
        size /= 1024.0
    return "%.1f TB/s" % size


def _escape(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _span(text, color):
    return "<span foreground='%s'>%s</span>" % (color, text)


_bar_cache = {}


def _bar_pixbuf(tx_ticks, rx_ticks):
    """The Tx←→Rx packet-tick bar as a 160×12 pixbuf (mockup R, confirmed).

    Rendering lives in the charts seam (`charts.txrx_bar_surface`) — the ONE
    implementation every network feature shares. Cached by tick counts:
    only 17×17 possible bars exist.
    """
    key = (tx_ticks, rx_ticks)
    if key not in _bar_cache:
        surf = charts.txrx_bar_surface(_BAR_W, _BAR_H, tx_ticks, rx_ticks)
        _bar_cache[key] = GdkPixbuf.Pixbuf.new_from_data(
            bytes(surf.get_data()), GdkPixbuf.Colorspace.RGB, True, 8,
            _BAR_W, _BAR_H, surf.get_stride())
    return _bar_cache[key]


class NetworkPage(BasePage):
    """Live per-process network activity, sortable on every column."""

    def __init__(self):
        self.sampler = None
        self._rows = {}          # (pid, starttime) -> row iter
        self._band = {}          # summary card value labels
        # r133: marks + tracking + pattern classes (manager_netwatch).
        self.netwatch = manager_netwatch.NetWatch()
        self._selected_key = None
        self._menu_key = None
        super().__init__(spacing=12, margin=24)

    # -- construction -----------------------------------------------------

    def set_sampler(self, sampler):
        """Inject the sampler (r113) — the page reads its public
        ``open_sockets()`` summary; the sampler keeps attribution ownership."""
        self.sampler = sampler

    def build_content(self):
        self.add_title("Network")
        self.add_markup_label(
            "<span foreground='#909090'>Processes actively sending or "
            "receiving on any network location. Socket-owner attribution "
            "(proportional) — not kernel accounting. Click a column header "
            "to sort.</span>", wrap=True, spacing_after=6)

        self._build_band()
        self._build_table()

    def _build_band(self):
        band = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        for key, label in (("rx", "↓ Total received"),
                           ("tx", "↑ Total sent"),
                           ("apps", "Active apps"),
                           ("busiest", "Busiest")):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            card.set_size_request(200, 74)
            css.add_css_class(card, "basics-card")
            head = Gtk.Label(label=label)
            head.set_xalign(0)
            css.add_css_class(head, "basics-gauge-k")
            value = Gtk.Label(label="—")
            value.set_xalign(0)
            css.add_css_class(value, "basics-gauge-v")
            layout.box_add(card, head, False, False, 0)
            layout.box_add(card, value, False, False, 0)
            layout.box_add(band, card, True, True, 0)
            self._band[key] = value
        layout.box_add(self, band, False, False, 0)

    def _build_table(self):
        types = (str, str, int, float, float, float,
                 GdkPixbuf.Pixbuf, int, int)   # + bar pixbuf, key pid/start
        self.store = Gtk.ListStore(*types)
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_headers_clickable(True)
        # r133: rows are SELECTABLE — the properties sidebar tracks the
        # selection, and the right-click menu marks importance / tracks.
        self.view.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        self.view.get_selection().connect("changed",
                                          self._on_selection_changed)
        self._menu_gesture = events.click_gesture(
            self.view, self._on_row_menu, button=3)

        # r113: page-owned sort state — deterministic and testable (GTK's
        # get_sort_column_id indirection made the unknowns-last sign flaky).
        self._sort_state = {"col": 5, "desc": True}   # default: busiest first

        for col_id, title, kind in _COLS:
            if kind == "bar":
                # r129: the Tx←→Rx packet-tick bar (pixbuf column, in front
                # of Total/s). Not sortable — it visualizes rx+tx together.
                renderer = Gtk.CellRendererPixbuf()
                column = Gtk.TreeViewColumn(title, renderer)
                column.add_attribute(renderer, "pixbuf", _COL_BAR)
                column.set_min_width(_BAR_W + 12)
                self.view.append_column(column)
                continue
            renderer = Gtk.CellRendererText()
            if kind in ("rate", "int"):
                renderer.set_property("xalign", 1.0)
            column = Gtk.TreeViewColumn(title, renderer)
            column.set_resizable(True)
            column.set_min_width(90 if kind == "rate" else 70)
            column.set_clickable(True)
            column.connect("clicked", self._on_header_clicked, col_id)
            self._set_sorter(col_id, kind)
            if kind == "rate":
                column.set_cell_data_func(
                    renderer, self._cell_rate, col_id)
            elif col_id == 0:
                # r133: importance badge rides the Process cell (markup).
                column.set_cell_data_func(renderer, self._cell_name)
                column.add_attribute(renderer, "text", col_id)
            else:
                # r113: text/int renderers need an explicit store binding —
                # a bare TreeViewColumn renders blank cells (found live).
                column.add_attribute(renderer, "text", col_id)
            self.view.append_column(column)
        self._apply_sort()
        self._register_net_actions()

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(360)
        layout.set_child(scrolled, self.view)

        # r133: properties sidebar (right, fold-out per selection) — the
        # no_show_all + per-widget reveal idiom (the r098 lesson: window
        # show_all must not force it open).
        self.props_pane = self._build_props_pane()
        self.props_pane.set_no_show_all(True)
        split = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        layout.box_add(split, scrolled, True, True, 0)
        layout.box_add(split, self.props_pane, False, False, 0)
        layout.box_add(self, split, True, True, 0)

    def _set_sorter(self, col_id, kind):
        """Unknowns-last numeric/text comparators (process-table convention).

        Direction comes from the page-owned sort state, not GTK: under DESC
        GTK negates the comparator, and the unknown's sign flips to match —
        unknowns land last in BOTH directions.
        """
        store = self.store

        def num_sort(model, a, b, data):
            col = data
            va, vb = model.get_value(a, col), model.get_value(b, col)
            unknown_a = va is None or va < 0
            unknown_b = vb is None or vb < 0
            asc = not (self._sort_state["col"] == col
                       and self._sort_state["desc"])
            if unknown_a or unknown_b:
                if unknown_a and unknown_b:
                    return 0
                if unknown_a:
                    return 1 if asc else -1
                return -1 if asc else 1
            return (va > vb) - (va < vb)

        def text_sort(model, a, b, data):
            col = data
            va = (model.get_value(a, col) or "").casefold()
            vb = (model.get_value(b, col) or "").casefold()
            return (va > vb) - (va < vb)

        store.set_sort_func(col_id, num_sort if kind != "text" else text_sort,
                            col_id)

    def _on_header_clicked(self, column, col_id):
        state = self._sort_state
        if state["col"] == col_id:
            state["desc"] = not state["desc"]
        else:
            state.update(col=col_id, desc=True)
        self._apply_sort()

    def _apply_sort(self):
        col = self._sort_state["col"]
        order = (Gtk.SortType.DESCENDING if self._sort_state["desc"]
                 else Gtk.SortType.ASCENDING)
        self.store.set_sort_column_id(col, order)

    def _cell_name(self, column, cell, model, it, _data=None):
        name = model.get_value(it, 0) or ""
        level = self.netwatch.mark_for(name)
        if level:
            badge = {"high": "#e06c6c", "medium": "#e8c268",
                     "low": "#9a9a9a"}.get(level, "#9a9a9a")
            cell.set_property("markup", "%s  %s" % (
                _span("●", badge), _escape(name)))
        else:
            cell.set_property("text", name)

    def _register_net_actions(self):
        group = Gio.SimpleActionGroup()
        # r134: callbacks receive (action, parameter) — the zero-arg lambdas
        # raised TypeError on every menu activation (the operator's
        # "some of the options are not fully functional").
        for name, callback in (
                ("mark-high", lambda a, p: self._set_importance("high")),
                ("mark-medium", lambda a, p: self._set_importance("medium")),
                ("mark-low", lambda a, p: self._set_importance("low")),
                ("mark-clear", lambda a, p: self._set_importance(None)),
                ("track-toggle", lambda a, p: self._toggle_track())):
            group.add_action(events.make_action(name, callback))
        self.view.insert_action_group("net", group)
        self._net_actions = group

    def _cell_rate(self, column, cell, model, it, col_id):
        value = model.get_value(it, col_id)
        if value is None or value < 0:
            cell.set_property("text", "—")
        else:
            cell.set_property("text", _fmt_rate(value))

    # -- selection, marks, tracking, properties sidebar (r133) ------------

    _BADGE = {"high": "#e06c6c", "medium": "#e8c268", "low": "#9a9a9a"}

    def _on_selection_changed(self, selection):
        model, it = selection.get_selected()
        if it is None:
            self._selected_key = None
            self.props_pane.set_visible(False)
            return
        key = (model.get_value(it, _COL_KEY_PID),
               model.get_value(it, _COL_KEY_START))
        self._selected_key = key
        self.props_pane.set_visible(True)
        self._update_props_pane()
        self._sync_menu_sensitivity()

    def _selected_name(self):
        model, it = self.view.get_selection().get_selected()
        return model.get_value(it, 0) if it is not None else None

    def _selected_importance(self):
        name = self._selected_name()
        return self.netwatch.mark_for(name) if name else None

    def _set_importance(self, level):
        name = self._selected_name()
        if name:
            self.netwatch.mark(name, level)
        self._sync_menu_sensitivity()

    def _toggle_track(self):
        key = self._selected_key
        if key is None:
            return
        name = self._selected_name() or ""
        if self.netwatch.is_tracked(key):
            self.netwatch.untrack(key)
        else:
            self.netwatch.track(key, name)
        self._update_props_pane()

    def _sync_menu_sensitivity(self):
        """Enable/disable the row-menu actions for the current selection."""
        for name in ("mark-low", "mark-medium", "mark-high", "mark-clear",
                     "track-toggle"):
            action = self._net_actions.lookup_action(name)
            if action is not None:
                action.set_enabled(self._selected_key is not None)

    def _on_row_menu(self, _gesture, _n, x, y):
        try:
            bx, by = self.view.convert_widget_to_bin_window_coords(
                int(x), int(y))
        except Exception:  # noqa: BLE001 - conversion exists on GTK3
            bx, by = int(x), int(y)
        res = self.view.get_path_at_pos(bx, by)
        if res is None:
            return
        self.view.get_selection().select_path(res[0])
        model, it = self.view.get_selection().get_selected()
        if it is None:
            return
        self._menu_key = (model.get_value(it, _COL_KEY_PID),
                          model.get_value(it, _COL_KEY_START))
        self._selected_key = self._menu_key
        name = model.get_value(it, 0)
        tracked = self.netwatch.is_tracked(self._menu_key)
        level = self.netwatch.mark_for(name)

        model_menu = Gio.Menu()
        imp = Gio.Menu()
        for lvl, label in (("high", "Mark importance: High"),
                           ("medium", "Mark importance: Medium"),
                           ("low", "Mark importance: Low"),
                           (None, "Clear importance mark")):
            mark = "✓ " if level == lvl else ""
            imp.append(mark + label, "net.mark-%s" % ("clear" if lvl is None
                                                      else lvl))
        model_menu.append_section(None, imp)
        track = Gio.Menu()
        track.append("Stop tracking" if tracked else "Track network activity",
                     "net.track-toggle")
        model_menu.append_section(None, track)
        self._menu_key = self._menu_key
        popover = menu.model_popover(model_menu, relative_to=self.view)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        self._row_popover = popover
        popover.popup()

    def _register_net_actions(self):
        group = Gio.SimpleActionGroup()
        # r134: callbacks receive (action, parameter) — the zero-arg lambdas
        # raised TypeError on every menu activation (the operator's
        # "some of the options are not fully functional").
        for name, callback in (
                ("mark-high", lambda a, p: self._set_importance("high")),
                ("mark-medium", lambda a, p: self._set_importance("medium")),
                ("mark-low", lambda a, p: self._set_importance("low")),
                ("mark-clear", lambda a, p: self._set_importance(None)),
                ("track-toggle", lambda a, p: self._toggle_track())):
            group.add_action(events.make_action(name, callback))
        self.view.insert_action_group("net", group)
        self._net_actions = group

    def _build_props_pane(self):
        pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        pane.set_size_request(300, -1)
        css.add_css_class(pane, "basics-card")
        self._p_name = Gtk.Label()
        self._p_name.set_xalign(0)
        self._p_name.set_use_markup(True)
        self._p_name.set_ellipsize(Pango.EllipsizeMode.END)
        css.add_css_class(self._p_name, "basics-gauge-k")
        layout.box_add(pane, self._p_name, False, False, 0)

        self._p_rows = {}
        for key in ("Importance", "Tracking", "Conns", "↓ Rx/s", "↑ Tx/s",
                    "Pattern"):
            head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            k = Gtk.Label(label=key)
            k.set_xalign(0)
            css.add_css_class(k, "basics-gauge-k")
            v = Gtk.Label()
            v.set_xalign(1)
            v.set_hexpand(True)
            v.set_halign(Gtk.Align.END)
            v.set_width_chars(16)
            v.set_max_width_chars(16)
            v.set_ellipsize(Pango.EllipsizeMode.END)
            layout.box_add(head, k, False, False, 0)
            layout.box_add(head, v, True, True, 0)
            layout.box_add(pane, head, False, False, 0)
            self._p_rows[key] = v

        self._p_chart_title = Gtk.Label(label="CONNECTION FREQUENCY")
        self._p_chart_title.set_xalign(0)
        css.add_css_class(self._p_chart_title, "basics-contrib-title")
        layout.box_add(pane, self._p_chart_title, False, False, 0)
        self._p_chart = charts.ChartArea(
            draw_func=lambda a, cr, w, h: self._draw_freq(cr, w, h))
        self._p_chart.set_size_request(-1, 40)
        layout.box_add(pane, self._p_chart, False, False, 0)

        self._p_verdict = Gtk.Label()
        self._p_verdict.set_xalign(0)
        self._p_verdict.set_line_wrap(True)
        self._p_verdict.set_width_chars(34)
        self._p_verdict.set_max_width_chars(34)
        self._p_verdict.set_ellipsize(Pango.EllipsizeMode.END)
        css.add_css_class(self._p_verdict, "basics-gauge-sub")
        layout.box_add(pane, self._p_verdict, False, False, 0)

        note = Gtk.Label()
        note.set_xalign(0)
        note.set_line_wrap(True)
        note.set_markup(_span(
            "Heuristic pattern from the tracked window — not proof. "
            "Attribution is proportional, not kernel accounting.",
            "#7a7a7a"))
        note.get_style_context().add_class("basics-gauge-sub")
        layout.box_add(pane, note, False, False, 0)
        return pane

    def _draw_freq(self, cr, width, height):
        cr.set_source_rgb(*_TROUGH)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        key = self._selected_key
        ring = self.netwatch.rings.get(key)
        if not ring:
            return
        volumes = [max(0.0, rx + tx) for _ts, rx, tx, _c in ring]
        peak = max(volumes) or 1.0
        slot = width / max(len(volumes), 1)
        bar_w = max(1.0, slot * 0.6)
        for i, vol in enumerate(volumes):
            if vol <= 0:
                continue
            h = max(2.0, (vol / peak) * (height - 2))
            cr.set_source_rgb(*_FREQ_RGB)
            cr.rectangle(i * slot, height - h, bar_w, h)
            cr.fill()

    def _update_props_pane(self):
        key = self._selected_key
        if key is None:
            return
        rec = (self._last_snapshot_procs or {}).get(key)
        name = self._selected_name()
        level = self.netwatch.mark_for(name) if name else None
        self._p_name.set_markup("%s%s" % (
            _escape(name or "—"),
            "  " + _span({"high": "● HIGH", "medium": "● MEDIUM",
                          "low": "● low"}.get(level, ""),
                         self._BADGE.get(level, "#666666")) if level else ""))
        tracked = self.netwatch.is_tracked(key)
        ring = self.netwatch.rings.get(key)
        conns = None
        if self.sampler is not None:
            conns = self.sampler.open_sockets().get(key[0])
        rec2 = (self._last_snapshot_procs or {}).get(key)
        rx = rec2.get("net_rx_rate") if rec2 else None
        tx = rec2.get("net_tx_rate") if rec2 else None
        values = {
            "Importance": (level or "none").capitalize(),
            "Tracking": "tracking (%d samples)" % len(ring)
            if tracked else "not tracked",
            "Conns": str(conns) if conns is not None else "—",
            "↓ Rx/s": _fmt_rate(rx) if rx is not None else "—",
            "↑ Tx/s": _fmt_rate(tx) if tx is not None else "—",
        }
        for k, v in values.items():
            self._p_rows[k].set_text(v)
        self._p_chart.queue_draw()
        if tracked:
            verdict = self.netwatch.classify(key)
            self._p_verdict.set_markup(_span(
                "%s — %s" % (verdict["category"], verdict["evidence"]),
                "#c9c9c9"))
        else:
            self._p_verdict.set_markup(_span(
                "Right-click the row → Track network activity to begin "
                "pattern analysis.", "#7a7a7a"))

    # -- live updates (snapshot observer) ---------------------------------

    def on_snapshot(self, snapshot):
        """Apply one snapshot — rows for processes with live attribution."""
        procs = snapshot.procs or {}
        self._last_snapshot_procs = procs
        sockets = {}
        if self.sampler is not None:
            sockets = self.sampler.open_sockets()
        ts = time.time()
        for key in self.netwatch.tracked():
            rec = procs.get(key)
            if rec is not None:
                conns = sockets.get(key[0])
                self.netwatch.sample(key, ts, rec.get("net_rx_rate"),
                                     rec.get("net_tx_rate"), conns)

        active = {}
        for key, rec in procs.items():
            rx = rec.get("net_rx_rate")
            tx = rec.get("net_tx_rate")
            conns = sockets.get(key[0])
            total = (rx or 0) + (tx or 0)
            if rx is None and tx is None and not conns:
                continue            # no attribution and no sockets: skip
            if total <= 0 and not conns:
                continue            # attributed but idle: not "actively" using
            active[key] = {
                "name": rec["name"], "user": rec["user"],
                "unit": rec.get("unit"), "rx": rx, "tx": tx,
                "total": total, "conns": conns,
            }

        for key in list(self._rows):
            if key not in active:
                self.store.remove(self._rows.pop(key))
        for key, info in active.items():
            # r134: the packet-tick bar measures in Bytes/KB increments —
            # each tick is a fixed byte step (64 B/s doubling), so the ticks
            # read as digital packet counts, not a relative share.
            tx_ticks = _byte_ticks(info["tx"])
            rx_ticks = _byte_ticks(info["rx"])
            pixbuf = _bar_pixbuf(tx_ticks, rx_ticks)
            values = (info["name"], info["user"],
                      info["conns"] if info["conns"] is not None else -1,
                      info["rx"] if info["rx"] is not None else -1,
                      info["tx"] if info["tx"] is not None else -1,
                      info["total"], pixbuf, key[0], key[1])
            if key in self._rows:
                it = self._rows[key]
                for col, val in enumerate(values):
                    if self.store.get_value(it, col) != val:
                        self.store.set_value(it, col, val)
            else:
                self._rows[key] = self.store.append(values)

        self._update_band(active)
        if self._selected_key is not None:
            self._update_props_pane()

    def _update_band(self, active):
        total_rx = sum((i["rx"] or 0) for i in active.values())
        total_tx = sum((i["tx"] or 0) for i in active.values())
        self._band["rx"].set_text(_fmt_rate(total_rx) if active else "—")
        self._band["tx"].set_text(_fmt_rate(total_tx) if active else "—")
        self._band["apps"].set_text(str(len(active)) if active else "—")
        busiest = max(
            active.items(), key=lambda kv: kv[1]["total"], default=None)
        if busiest and busiest[1]["total"] > 0:
            self._band["busiest"].set_text(_escape(busiest[1]["name"]))
        else:
            self._band["busiest"].set_text("—")
