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

from ui.compat import Gtk, GLib, Pango, css, layout, charts

from pages.page_base import BasePage

_ACCENT = (0x00 / 255.0, 0x78 / 255.0, 0xD7 / 255.0)
_TROUGH = (0x1b / 255.0, 0x1b / 255.0, 0x1b / 255.0)

_COLS = [
    # (store col, title, kind)  kind: text | rate | int
    (0, "Process", "text"),
    (1, "User", "text"),
    (2, "Conns", "int"),
    (3, "↓ Rx/s", "rate"),
    (4, "↑ Tx/s", "rate"),
    (5, "Total/s", "rate"),
]
_COL_KEY_PID = 6
_COL_KEY_START = 7


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


class NetworkPage(BasePage):
    """Live per-process network activity, sortable on every column."""

    def __init__(self):
        self.sampler = None
        self._rows = {}          # (pid, starttime) -> row iter
        self._band = {}          # summary card value labels
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
                 int, int)               # + key pid/start (hidden)
        self.store = Gtk.ListStore(*types)
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_headers_clickable(True)
        self.view.get_selection().set_mode(Gtk.SelectionMode.NONE)

        # r113: page-owned sort state — deterministic and testable (GTK's
        # get_sort_column_id indirection made the unknowns-last sign flaky).
        self._sort_state = {"col": 5, "desc": True}   # default: busiest first

        for col_id, title, kind in _COLS:
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
            else:
                # r113: text/int renderers need an explicit store binding —
                # a bare TreeViewColumn renders blank cells (found live).
                column.add_attribute(renderer, "text", col_id)
            self.view.append_column(column)
        self._apply_sort()

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(360)
        layout.set_child(scrolled, self.view)
        layout.box_add(self, scrolled, True, True, 0)

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

    def _cell_rate(self, column, cell, model, it, col_id):
        value = model.get_value(it, col_id)
        if value is None or value < 0:
            cell.set_property("text", "—")
        else:
            cell.set_property("text", _fmt_rate(value))

    # -- live updates (snapshot observer) ---------------------------------

    def on_snapshot(self, snapshot):
        """Apply one snapshot — rows for processes with live attribution."""
        procs = snapshot.procs or {}
        sockets = {}
        if self.sampler is not None:
            sockets = self.sampler.open_sockets()

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
            values = (info["name"], info["user"],
                      info["conns"] if info["conns"] is not None else -1,
                      info["rx"] if info["rx"] is not None else -1,
                      info["tx"] if info["tx"] is not None else -1,
                      info["total"], key[0], key[1])
            if key in self._rows:
                it = self._rows[key]
                for col, val in enumerate(values):
                    if self.store.get_value(it, col) != val:
                        self.store.set_value(it, col, val)
            else:
                self._rows[key] = self.store.append(values)

        self._update_band(active)

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
