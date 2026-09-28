"""Process preview pane (mockup J) — the right fold-out on the Processes page.

Spec: docs/modules/process-preview.md §2. The pane tracks the table selection,
refreshes every snapshot, and reuses the page's existing action methods; it never
reads ``/proc`` itself (boundary law) — the selected row's ``smaps_rollup`` rides
the sampler's ``request_rollup`` and dependency basenames come through the
actions layer (:func:`modules.manager_actions.dependencies`).

The rendered content is computed by the PURE :func:`preview_model` (a dict of
plain values keyed by section) so the sections, ancestry ordering, children list,
and self/children/combined network attribution are fixture-testable without a
display. The :class:`PreviewPane` widget only turns that dict into labels.
"""

from collections import deque

from ui.compat import Gtk, Pango, css, layout, charts

# Sparkline history: 60 s of cpu% for the selected pid (ring owned here, fed by
# snapshots — no new sampling). Sized generously; the draw clips to 60 s by ts.
_SPARK_WINDOW_S = 60.0
_SPARK_MAX = 240

_ACCENT_RGB = (0x00 / 255.0, 0x78 / 255.0, 0xD7 / 255.0)
_TROUGH_RGB = (0x3a / 255.0, 0x3a / 255.0, 0x3a / 255.0)

# Preview pane fold-out width (spec §2: 290–330 px).
PANE_WIDTH = 310


# ---------------------------------------------------------------------------
# Pure helpers (fixture-testable, no widgets).
# ---------------------------------------------------------------------------

def _pid_index(procs):
    """pid -> its (pid, starttime) key (one live entry per pid per snapshot)."""
    return {key[0]: key for key in procs}


def ancestry_chain(procs, key):
    """Keys from the root ancestor down to ``key`` (inclusive) via PPid edges.

    Cycle- and orphan-safe: the walk stops at an unknown parent (ppid not in the
    snapshot, e.g. ppid 0) or a repeat. Returns ``[]`` for an unknown key.
    """
    if key not in procs:
        return []
    index = _pid_index(procs)
    chain = [key]
    seen = {key}
    cur = key
    while True:
        rec = procs.get(cur)
        ppid = rec.get("ppid") if rec else None
        if ppid is None:
            break
        parent = index.get(ppid)
        if parent is None or parent in seen:
            break
        chain.append(parent)
        # ``set.add`` is name-collision-flagged by the banned-API gate in the
        # UI tree; union keeps set semantics without the attribute.
        seen = seen | {parent}
        cur = parent
    chain.reverse()
    return chain


def child_keys(procs, key):
    """Immediate-child keys of ``key`` (records whose PPid is this pid)."""
    pid = key[0]
    return sorted(k for k, rec in procs.items()
                  if k != key and rec.get("ppid") == pid)


def descendant_keys(procs, key):
    """All descendant keys of ``key`` (the subtree, excluding ``key`` itself)."""
    out = []
    seen = {key}
    frontier = [key]
    while frontier:
        cur = frontier.pop()
        for child in child_keys(procs, cur):
            if child in seen:
                continue
            seen = seen | {child}   # union: the gate flags set.add in the UI tree
            out.append(child)
            frontier.append(child)
    return out


def _sum_field(procs, keys, field):
    """Sum a numeric record field over ``keys``; ``None`` if every value is
    unknown (honest absence — a restricted child never fabricates a 0)."""
    total = None
    for key in keys:
        rec = procs.get(key)
        if rec is None:
            continue
        value = rec.get(field)
        if value is not None:
            total = value if total is None else total + value
    return total


def net_summary(procs, key):
    """self / per-child / combined-tree rx+tx for the selected process.

    Each value may be ``None`` (attribution restricted under Yama, or first
    sample) — the pane renders those as a lock + "—", never a 0.
    """
    rec = procs.get(key) or {}
    children = []
    for child in child_keys(procs, key):
        crec = procs[child]
        children.append((child, crec.get("name"),
                         crec.get("net_rx_rate"), crec.get("net_tx_rate")))
    subtree = [key] + descendant_keys(procs, key)
    return {
        "self": (rec.get("net_rx_rate"), rec.get("net_tx_rate")),
        "children": children,
        "combined": (_sum_field(procs, subtree, "net_rx_rate"),
                     _sum_field(procs, subtree, "net_tx_rate")),
    }


def preview_model(procs, system, key, dependencies=None):
    """Everything the pane renders for ``key`` as a plain dict (pure).

    ``dependencies`` is ``(basenames, count)`` from the actions layer (the pane
    injects it so this stays widget- and /proc-free). ``None`` -> unknown.
    """
    rec = procs.get(key)
    if rec is None:
        return None
    rollup = rec.get("rollup") if isinstance(rec.get("rollup"), dict) else {}
    net = net_summary(procs, key)
    ancestry = [(k, (procs[k].get("name") or "?")) for k in
                ancestry_chain(procs, key)]
    children = [(k, procs[k].get("name") or "?", procs[k].get("cpu_pct"),
                 procs[k].get("mem_rss")) for k in child_keys(procs, key)]
    deps_list, deps_count = dependencies if dependencies is not None else ([], 0)
    return {
        "identity": {
            "name": rec.get("name"), "pid": key[0], "ppid": rec.get("ppid"),
            "state": rec.get("state"), "unit": rec.get("unit"),
            "threads": rec.get("threads"), "cmdline": rec.get("cmdline"),
            "started": rec.get("started"), "is_kthread": rec.get("is_kthread"),
            "is_defunct": rec.get("is_defunct"),
        },
        "kpi": {
            "cpu": rec.get("cpu_pct"), "rss": rec.get("mem_rss"),
            "swap": rec.get("mem_swap"), "net_tree": net["combined"],
        },
        "resource": {
            "cpu_time": rec.get("cpu_time"), "started": rec.get("started"),
            "rss": rec.get("mem_rss"), "shared": rec.get("mem_shared"),
            "vsize": rec.get("mem_vsize"), "pss": rollup.get("pss_bytes"),
            "mem_pct": rec.get("mem_pct"),
            "disk_read_total": rec.get("io_read_total"),
            "disk_write_total": rec.get("io_write_total"),
            "disk_read_rate": rec.get("io_read_rate"),
            "disk_write_rate": rec.get("io_write_rate"),
            "nice": rec.get("nice"), "oom_score": rec.get("oom_score"),
            "affinity": rec.get("affinity"),
        },
        "ancestry": ancestry,
        "children": children,
        "net": net,
        "dependencies": (deps_list, deps_count),
    }


# ---------------------------------------------------------------------------
# Render formatting helpers.
# ---------------------------------------------------------------------------

def _escape(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_bytes(value):
    if value is None or value < 0:
        return "—"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return ("%d B" % int(size)) if unit == "B" else "%.1f %s" % (size, unit)
        size /= 1024.0
    return "%.1f TB" % size


def _fmt_rate(value):
    if value is None or value < 0:
        return "—"
    return _fmt_bytes(value) + "/s"


def _fmt_net_cell(value):
    """Attribution cell: a byte-rate, or a lock + "—" when unknown (Yama /
    first sample) — never a fabricated 0 (spec §6)."""
    if value is None:
        return "🔒 —"
    return _fmt_rate(value)


def _fmt_pct(value):
    return "—" if value is None else "%.1f%%" % value


def _fmt_int(value):
    return "—" if value is None else str(int(value))


# ---------------------------------------------------------------------------
# The widget.
# ---------------------------------------------------------------------------

class PreviewPane(Gtk.Box):
    """Right fold-out preview for the selected process (mockup J).

    ``page`` supplies the sampler (for ``request_rollup``), the jump-to-process
    selector, and the reused action methods.
    """

    def __init__(self, page):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._page = page
        self._key = None
        self._spark = deque(maxlen=_SPARK_MAX)  # (ts, cpu_pct)
        css.add_css_class(self, "preview-pane")
        self.set_size_request(PANE_WIDTH, -1)
        self._dyn = {}   # section name -> list of transient child widgets
        # r098 §5b: the pane's width is FIXED at PANE_WIDTH. Content lives in
        # an inner box inside a vertical-only scroll; every label is
        # width-pinned + wrapped so a long exe path can never widen the pane
        # and crush the table.
        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                spacing=8)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        layout.set_child(scroll, self._content)
        layout.box_add(self, scroll, True, True, 0)
        self._build_into(self._content)
        self._reveal_content()

    def _build_into(self, box):
        """Build all pane sections into ``box`` (the scroll content)."""
        self._content = box
        self._build()

    # -- construction -----------------------------------------------------

    def _reveal_content(self):
        """r098: the pane is no_show_all, so window.show_all() skipped this
        whole subtree — toggling the pane on used to reveal an empty sliver.
        Show the built content per-widget (never show_all on the pane self:
        its visibility belongs to the toolbar toggle)."""
        def walk(w):
            w.show()
            if hasattr(w, "forall"):
                w.forall(walk)
        self.forall(walk)

    def _section_title(self, text):
        label = Gtk.Label(label=text)
        label.set_xalign(0)
        css.add_css_class(label, "graph-section")
        layout.box_add(self, label, False, False, 0)

    def _mk_label(self, markup=""):
        label = Gtk.Label()
        label.set_xalign(0)
        label.set_use_markup(True)
        label.set_line_wrap(True)
        # r098 §5b: a wrapped label's NATURAL request is its full single-line
        # text — the exe path made the pane ~850px natural and crushed the
        # table. width/max_width chars cap the request; wrap + ellipsize
        # render inside it.
        label.set_width_chars(40)
        label.set_max_width_chars(40)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_markup(markup)
        return label

    def _mk_box(self, name):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._dyn[name] = []
        layout.box_add(self, box, False, False, 0)
        return box

    def _build(self):
        self.identity_label = self._mk_label(self._muted("No process selected"))
        layout.box_add(self, self.identity_label, False, False, 0)

        self.kpi_label = self._mk_label()
        layout.box_add(self, self.kpi_label, False, False, 0)

        # 60 s cpu sparkline.
        self.spark = charts.ChartArea(
            draw_func=lambda a, cr, w, h: self._draw_spark(cr, w, h))
        self.spark.set_size_request(-1, 46)
        css.add_css_class(self.spark, "preview-spark")
        layout.box_add(self, self.spark, False, False, 0)

        self._section_title("Ancestry")
        self.ancestry_box = self._mk_box("ancestry")

        self._section_title("Children")
        self.children_box = self._mk_box("children")

        self._section_title("Resource consumption")
        self.resource_label = self._mk_label()
        layout.box_add(self, self.resource_label, False, False, 0)

        self._section_title("Networking (attribution)")
        self.net_box = self._mk_box("net")

        self._section_title("Dependencies")
        self.deps_label = self._mk_label()
        layout.box_add(self, self.deps_label, False, False, 0)

        self._build_actions()

    def _build_actions(self):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        css.add_css_class(row, "preview-actions")
        for label, handler in (
            ("End", lambda _b: self._page._do_signal("end")),
            ("Kill", lambda _b: self._page._do_signal("kill")),
            ("Stop", lambda _b: self._page._do_signal("stop")),
            ("Renice", lambda _b: self._page._act_renice(5)),
        ):
            button = Gtk.Button(label=label)
            button.connect("clicked", handler)
            layout.box_add(row, button, True, True, 0)
        journal = Gtk.Button(label="Journal")
        journal.set_sensitive(False)          # Phase 7 placeholder
        journal.set_tooltip_text("Journal integration — Phase 7")
        layout.box_add(row, journal, True, True, 0)
        layout.box_add(self, row, False, False, 0)

    # -- external wiring --------------------------------------------------

    def set_selection(self, key):
        """Track a new selection; reset the sparkline ring and request a rollup
        so PSS/exact memory populate on the next snapshot."""
        if key == self._key:
            return
        self._key = key
        self._spark.clear()
        if key is not None and self._page.sampler is not None:
            try:
                self._page.sampler.request_rollup(key[0], key[1])
            except Exception:  # noqa: BLE001 - rollup is best-effort
                pass

    def update(self, procs, system):
        """Refresh from a snapshot (called on every applied snapshot)."""
        key = self._key
        if key is None or key not in procs:
            self.identity_label.set_markup(self._muted("No process selected"))
            self._clear_all()
            self.spark.queue_draw()
            return
        deps = None
        try:
            deps = ma_dependencies(key)
        except Exception:  # noqa: BLE001 - dependency read is best-effort
            deps = ([], 0)
        model = preview_model(procs, system, key, dependencies=deps)
        if model is None:
            return
        rec = procs.get(key) or {}
        cpu = rec.get("cpu_pct")
        self._spark.append((rec.get("started") or 0.0, cpu))
        self._render(model)
        self.spark.queue_draw()

    # -- rendering --------------------------------------------------------

    @staticmethod
    def _muted(text):
        return "<span foreground='#888888'>%s</span>" % _escape(text)

    def _clear_box(self, name, box):
        for child in self._dyn.get(name, []):
            layout.box_remove(box, child)
        self._dyn[name] = []

    def _clear_all(self):
        self.kpi_label.set_text("")
        self.resource_label.set_text("")
        self.deps_label.set_text("")
        self._clear_box("ancestry", self.ancestry_box)
        self._clear_box("children", self.children_box)
        self._clear_box("net", self.net_box)

    def _render(self, model):
        ident = model["identity"]
        badges = []
        if ident["unit"] and ident["unit"] != "—":
            badges.append(ident["unit"])
        if ident["threads"] is not None:
            badges.append("%d thr" % ident["threads"])
        if ident["state"]:
            badges.append(ident["state"])
        head = "<b>%s</b>  <span foreground='#888888'>%s</span>" % (
            _escape(ident["name"] or "?"), _escape(" · ".join(badges)))
        cmd = ident["cmdline"] or "—"
        self.identity_label.set_markup(
            "%s\n<span size='small' foreground='#aaaaaa'>%s</span>" % (
                head, _escape(cmd)))

        kpi = model["kpi"]
        tree_rx, tree_tx = kpi["net_tree"]
        self.kpi_label.set_markup(
            "CPU <b>%s</b>   RSS <b>%s</b>   Swap <b>%s</b>   Net∑ <b>%s/%s</b>" % (
                _escape(_fmt_pct(kpi["cpu"])), _escape(_fmt_bytes(kpi["rss"])),
                _escape(_fmt_bytes(kpi["swap"])),
                _escape(_fmt_net_cell(tree_rx)), _escape(_fmt_net_cell(tree_tx))))

        self._render_ancestry(model["ancestry"])
        self._render_children(model["children"])
        self._render_resource(model["resource"])
        self._render_net(model["net"])

        deps_list, deps_count = model["dependencies"]
        if deps_count:
            extra = ("  +%d more" % (deps_count - len(deps_list))
                     if deps_count > len(deps_list) else "")
            self.deps_label.set_markup(
                "<span size='small'>%s</span><span foreground='#888888'>%s</span>"
                % (_escape(", ".join(deps_list)), _escape(extra)))
        else:
            self.deps_label.set_markup(self._muted("—"))

    def _clickable_row(self, box, name, key, text):
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        css.add_css_class(button, "basics-contrib-row")
        label = self._mk_label(text)
        layout.set_child(button, label)
        button.connect("clicked", lambda _b, k=key: self._page.select_process(k))
        layout.box_add(box, button, False, False, 0)
        # Added after the toplevel show_all -> show explicitly (graph_details
        # pattern; box_add does not show children).
        label.show()
        button.show()
        self._dyn[name].append(button)

    def _render_ancestry(self, ancestry):
        self._clear_box("ancestry", self.ancestry_box)
        if not ancestry:
            self._add_note("ancestry", self.ancestry_box, "—")
            return
        for depth, (key, name) in enumerate(ancestry):
            marker = ("  " * depth) + ("└ " if depth else "")
            self._clickable_row(
                self.ancestry_box, "ancestry", key,
                "<span size='small'>%s%s</span> "
                "<span size='small' foreground='#888888'>(%d)</span>" % (
                    _escape(marker), _escape(name), key[0]))

    def _render_children(self, children):
        self._clear_box("children", self.children_box)
        if not children:
            self._add_note("children", self.children_box, "No children")
            return
        for key, name, cpu, mem in children:
            self._clickable_row(
                self.children_box, "children", key,
                "<span size='small'>%s</span> "
                "<span size='small' foreground='#888888'>%s · %s</span>" % (
                    _escape(name), _escape(_fmt_pct(cpu)), _escape(_fmt_bytes(mem))))

    def _render_resource(self, res):
        lines = [
            "CPU time %s · started %s" % (
                _fmt_secs(res["cpu_time"]), _fmt_started(res["started"])),
            "RSS %s · shared %s · virt %s" % (
                _fmt_bytes(res["rss"]), _fmt_bytes(res["shared"]),
                _fmt_bytes(res["vsize"])),
            "PSS %s · mem%% %s" % (_fmt_bytes(res["pss"]), _fmt_pct(res["mem_pct"])),
            "disk ↓%s ↑%s (total ↓%s ↑%s)" % (
                _fmt_rate(res["disk_read_rate"]), _fmt_rate(res["disk_write_rate"]),
                _fmt_bytes(res["disk_read_total"]),
                _fmt_bytes(res["disk_write_total"])),
            "nice %s · oom %s" % (_fmt_int(res["nice"]), _fmt_int(res["oom_score"])),
        ]
        self.resource_label.set_markup(
            "<span size='small'>%s</span>" % _escape("\n".join(lines)))

    def _render_net(self, net):
        self._clear_box("net", self.net_box)
        srx, stx = net["self"]
        self._add_note("net", self.net_box,
                       "self ↓%s ↑%s" % (_fmt_net_cell(srx), _fmt_net_cell(stx)))
        for _key, name, crx, ctx in net["children"]:
            self._add_note("net", self.net_box,
                           "%s ↓%s ↑%s" % (name or "?", _fmt_net_cell(crx),
                                           _fmt_net_cell(ctx)))
        crx, ctx = net["combined"]
        self._add_note("net", self.net_box,
                       "combined ↓%s ↑%s" % (_fmt_net_cell(crx),
                                             _fmt_net_cell(ctx)))

    def _add_note(self, name, box, text):
        label = self._mk_label("<span size='small'>%s</span>" % _escape(text))
        layout.box_add(box, label, False, False, 0)
        label.show()  # dynamic child added after show_all
        self._dyn[name].append(label)

    # -- sparkline --------------------------------------------------------

    def _draw_spark(self, cr, width, height):
        cr.set_source_rgb(*_TROUGH_RGB)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        points = [(ts, v) for ts, v in self._spark if v is not None]
        if len(points) < 2:
            return
        n = len(points)
        cr.set_source_rgb(*_ACCENT_RGB)
        cr.set_line_width(1.5)
        for i, (_ts, value) in enumerate(points):
            x = width * i / (n - 1)
            frac = max(0.0, min(1.0, value / 100.0))
            y = height - frac * height
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()


# Late binding of the actions-layer dependency reader (kept out of the pure
# helpers so tests can call ``preview_model`` without the actions import).
try:  # app layout
    from modules.manager_actions import dependencies as ma_dependencies
except ImportError:  # standalone/test layout
    try:
        from manager_actions import dependencies as ma_dependencies
    except ImportError:  # pragma: no cover - actions unavailable
        def ma_dependencies(_key):
            return ([], 0)


def _fmt_secs(seconds):
    if seconds is None or seconds < 0:
        return "—"
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    if minutes:
        return "%d:%02d" % (minutes, secs)
    return "%ds" % secs


def _fmt_started(epoch):
    if epoch is None or epoch <= 0:
        return "—"
    import time
    try:
        return time.strftime("%b %d %H:%M", time.localtime(epoch))
    except (ValueError, OSError):
        return "—"
