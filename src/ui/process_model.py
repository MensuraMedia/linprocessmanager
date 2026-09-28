"""Process-table model layer (docs/modules/process-table.md).

Owns the flat :class:`Gtk.ListStore`, the diff-in-place engine, the
:class:`Gtk.TreeModelFilter` wrapper, sort with unknowns-last, the row budget,
and selection identity by ``(pid, starttime)``. It is the ONLY place the
sampler's ``None`` no-data becomes the ``(-1 sentinel, has_data=False)`` pair
the typed store needs (``None`` in a float column is a PyGObject marshaling
hazard; NaN breaks numeric sort). Cell rendering and the TreeView live in
``src/pages/page_processes.py``; this file builds no widgets.

Diff order (flat list — the tree view and its reparent "move" op are a later
phase): update changed rows in place, insert new pids, remove gone pids —
keyed by ``(pid, starttime)`` → :class:`Gtk.TreeRowReference` (raw
``Gtk.TreeIter`` are invalidated by removals and are never cached across a
batch). Sorting is blocked around the whole batch and the filter is suspended
(one refilter at the end) so neither runs per-row — the O(n^2) freeze that a
fork bomb would otherwise trigger.
"""

import os
import pwd
import re

from ui.compat import Gtk, GObject

# --- Store column layout ----------------------------------------------------
# Identity + display columns, then each nullable numeric as a (value, has_data)
# pair so unknowns render "—" and sort to the extreme low end (see _num_sort).
COL_PID = 0
COL_STARTTIME = 1
COL_NAME = 2
COL_USER = 3
COL_UNIT = 4
COL_STATE = 5
COL_CPU = 6
COL_CPU_HAS = 7
COL_MEM = 8
COL_MEM_HAS = 9
COL_SWAP = 10
COL_SWAP_HAS = 11
COL_DISK_R = 12
COL_DISK_R_HAS = 13
COL_DISK_W = 14
COL_DISK_W_HAS = 15
COL_NICE = 16
COL_NICE_HAS = 17
COL_IS_KTHREAD = 18
COL_IS_DEFUNCT = 19
COL_NAME_SORT = 20   # r067: clean casefolded name — stable sort key for the
                     # Process column (markup changes must not reorder rows)
# r093 (task 010) extended columns — appended AFTER the original layout so every
# pre-existing COL_* index (and the model's tests that use them) is untouched.
# Nullable numerics keep the (value, has_data) pair (unknowns render "—" and
# sort last); string columns store "" for absent.
COL_CMDLINE = 21
COL_AFFINITY = 22          # pre-formatted display string ("" when unknown)
COL_THREADS = 23
COL_THREADS_HAS = 24
COL_CPU_TIME = 25          # seconds
COL_CPU_TIME_HAS = 26
COL_MEM_PCT = 27
COL_MEM_PCT_HAS = 28
COL_SHARED = 29            # bytes
COL_SHARED_HAS = 30
COL_PSS = 31               # bytes (selected row only, via rollup)
COL_PSS_HAS = 32
COL_DISK_R_TOT = 33        # bytes (cumulative)
COL_DISK_R_TOT_HAS = 34
COL_DISK_W_TOT = 35        # bytes (cumulative)
COL_DISK_W_TOT_HAS = 36
COL_NET_RX = 37            # bytes/s (attribution)
COL_NET_RX_HAS = 38
COL_NET_TX = 39            # bytes/s (attribution)
COL_NET_TX_HAS = 40
COL_OOM = 41
COL_OOM_HAS = 42
COL_STARTED = 43           # epoch seconds
COL_STARTED_HAS = 44
COL_PPID = 45
COL_PPID_HAS = 46
N_COLUMNS = 47

STORE_TYPES = [
    int,                    # COL_PID
    GObject.TYPE_INT64,     # COL_STARTTIME (jiffies-since-boot can exceed int32)
    str,                    # COL_NAME
    str,                    # COL_USER
    str,                    # COL_UNIT
    str,                    # COL_STATE
    float, bool,            # CPU
    GObject.TYPE_INT64, bool,   # MEM (bytes)
    GObject.TYPE_INT64, bool,   # SWAP (bytes)
    float, bool,            # DISK_R (bytes/s)
    float, bool,            # DISK_W (bytes/s)
    int, bool,              # NICE
    bool,                   # IS_KTHREAD
    bool,                   # IS_DEFUNCT
    str,                    # NAME_SORT (hidden stable key)
    # --- r093 extended columns ---
    str,                        # CMDLINE
    str,                        # AFFINITY (display)
    int, bool,                  # THREADS
    float, bool,                # CPU_TIME (seconds)
    float, bool,                # MEM_PCT
    GObject.TYPE_INT64, bool,   # SHARED (bytes)
    GObject.TYPE_INT64, bool,   # PSS (bytes)
    GObject.TYPE_INT64, bool,   # DISK_R_TOT (bytes)
    GObject.TYPE_INT64, bool,   # DISK_W_TOT (bytes)
    float, bool,                # NET_RX (bytes/s)
    float, bool,                # NET_TX (bytes/s)
    int, bool,                  # OOM
    GObject.TYPE_DOUBLE, bool,  # STARTED (epoch seconds — needs double)
    int, bool,                  # PPID
]

# Logical (persisted) sort-key -> the (value_col, has_col) it maps to. Columns
# always present (pid) carry has_col=None. r084: disk reads/writes are
# separate columns and sort on their own field.
SORT_COLUMNS = {
    "cpu": (COL_CPU, COL_CPU_HAS),
    "memory": (COL_MEM, COL_MEM_HAS),
    "swap": (COL_SWAP, COL_SWAP_HAS),
    "disk_read": (COL_DISK_R, COL_DISK_R_HAS),
    "disk_write": (COL_DISK_W, COL_DISK_W_HAS),
    "nice": (COL_NICE, COL_NICE_HAS),
    "pid": (COL_PID, None),
    "process": (COL_NAME, None),
    "user": (COL_USER, None),
    "state": (COL_STATE, None),
    # r093 extended numeric columns (string columns are not numerically sorted).
    "cpu_time": (COL_CPU_TIME, COL_CPU_TIME_HAS),
    "threads": (COL_THREADS, COL_THREADS_HAS),
    "mem_pct": (COL_MEM_PCT, COL_MEM_PCT_HAS),
    "shared": (COL_SHARED, COL_SHARED_HAS),
    "pss": (COL_PSS, COL_PSS_HAS),
    "disk_read_total": (COL_DISK_R_TOT, COL_DISK_R_TOT_HAS),
    "disk_write_total": (COL_DISK_W_TOT, COL_DISK_W_TOT_HAS),
    "net_rx": (COL_NET_RX, COL_NET_RX_HAS),
    "net_tx": (COL_NET_TX, COL_NET_TX_HAS),
    "oom_score": (COL_OOM, COL_OOM_HAS),
    "started": (COL_STARTED, COL_STARTED_HAS),
    "ppid": (COL_PPID, COL_PPID_HAS),
}

# Record field a logical sort-key reads for the Python-side budget pre-sort.
_SORT_RECORD_FIELD = {
    "cpu": "cpu_pct", "memory": "mem_rss", "swap": "mem_swap",
    "nice": "nice", "pid": "pid", "process": "name", "user": "user",
    "state": "state", "disk_read": "io_read_rate", "disk_write":
    "io_write_rate",
    "cpu_time": "cpu_time", "threads": "threads", "mem_pct": "mem_pct",
    "shared": "mem_shared", "disk_read_total": "io_read_total",
    "disk_write_total": "io_write_total", "net_rx": "net_rx_rate",
    "net_tx": "net_tx_rate", "oom_score": "oom_score", "started": "started",
    "ppid": "ppid",
    # "pss" rides the selected-only rollup, not a flat field -> no pre-sort key.
}

DEFAULT_ROW_BUDGET = 5000

# "No sorting" sentinel for set_sort_column_id (GTK #define, value -2). Looked
# up defensively so a binding that omits the constant still works.
_UNSORTED = getattr(Gtk, "TREE_SORTABLE_UNSORTED_SORT_COLUMN_ID", -2)


def _me():
    """Current login name (for the "My processes" scope)."""
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except (KeyError, OSError):
        return os.environ.get("USER") or ""


def format_affinity(affinity):
    """Compact CPU-set display: ``(0,1,2,3)`` -> ``"0-3"``, ``(0,2,3)`` ->
    ``"0,2-3"``; ``None``/empty -> ``""`` (blanked "—" in the cell)."""
    if not affinity:
        return ""
    cpus = sorted(set(affinity))
    ranges = []
    start = prev = cpus[0]
    for cpu in cpus[1:]:
        if cpu == prev + 1:
            prev = cpu
            continue
        ranges.append((start, prev))
        start = prev = cpu
    ranges.append((start, prev))
    return ",".join("%d" % a if a == b else "%d-%d" % (a, b)
                    for a, b in ranges)


def record_to_row(rec):
    """Translate one sampler record dict into a typed store row.

    THE boundary: every ``None`` becomes ``(-1 sentinel, has_data=False)``. A
    ``-1`` sentinel sorts below any real value (cpu/mem/rates are >= 0), so
    unknowns land last under the default descending sort with no NaN in sight.
    """
    def num(value):
        return (value is not None, value if value is not None else -1)

    cpu_has, cpu = num(rec.get("cpu_pct"))
    mem_has, mem = num(rec.get("mem_rss"))
    swap_has, swap = num(rec.get("mem_swap"))
    dr_has, dr = num(rec.get("io_read_rate"))
    dw_has, dw = num(rec.get("io_write_rate"))
    nice_has, nice = num(rec.get("nice"))

    # r093 extended fields (all None-tolerant; missing key -> unknown).
    ct_has, ct = num(rec.get("cpu_time"))
    thr_has, thr = num(rec.get("threads"))
    mp_has, mp = num(rec.get("mem_pct"))
    sh_has, sh = num(rec.get("mem_shared"))
    rollup = rec.get("rollup")
    pss_has, pss = num(rollup.get("pss_bytes") if isinstance(rollup, dict)
                       else None)
    drt_has, drt = num(rec.get("io_read_total"))
    dwt_has, dwt = num(rec.get("io_write_total"))
    nrx_has, nrx = num(rec.get("net_rx_rate"))
    ntx_has, ntx = num(rec.get("net_tx_rate"))
    oom_has, oom = num(rec.get("oom_score"))
    st_has, st = num(rec.get("started"))
    ppid_has, ppid = num(rec.get("ppid"))

    unit = rec.get("unit")
    unit_disp = unit if (unit and unit != "—") else ""

    return [
        int(rec.get("pid") or -1),
        int(rec.get("starttime") or 0),
        rec.get("name") or "?",
        rec.get("user") or "?",
        unit_disp,
        rec.get("state") or "?",
        float(cpu) if cpu_has else -1.0, cpu_has,
        int(mem) if mem_has else -1, mem_has,
        int(swap) if swap_has else -1, swap_has,
        float(dr) if dr_has else -1.0, dr_has,
        float(dw) if dw_has else -1.0, dw_has,
        int(nice) if nice_has else -1, nice_has,
        bool(rec.get("is_kthread")),
        bool(rec.get("is_defunct")),
        (rec.get("name") or "?").casefold(),
        # --- r093 extended columns ---
        rec.get("cmdline") or "",
        format_affinity(rec.get("affinity")),
        int(thr) if thr_has else -1, thr_has,
        float(ct) if ct_has else -1.0, ct_has,
        float(mp) if mp_has else -1.0, mp_has,
        int(sh) if sh_has else -1, sh_has,
        int(pss) if pss_has else -1, pss_has,
        int(drt) if drt_has else -1, drt_has,
        int(dwt) if dwt_has else -1, dwt_has,
        float(nrx) if nrx_has else -1.0, nrx_has,
        float(ntx) if ntx_has else -1.0, ntx_has,
        int(oom) if oom_has else -1, oom_has,
        float(st) if st_has else -1.0, st_has,
        int(ppid) if ppid_has else -1, ppid_has,
    ]


class ProcessTableModel:
    """Flat store + filter + diff engine keyed by ``(pid, starttime)``."""

    def __init__(self, row_budget=DEFAULT_ROW_BUDGET):
        self.store = Gtk.ListStore(*STORE_TYPES)
        self._refs = {}  # (pid, starttime) -> Gtk.TreeRowReference
        self._budget = row_budget
        self._batching = False

        # Filter state (re-pointed on change, never rebuilt per keystroke).
        self._query = ""
        self._regex = False
        self._regex_pat = None
        self._scope = "all"
        self._show_kthreads = False
        self._me = _me()

        # Sort state (mirrors the persisted key/direction).
        self._sort_key = "cpu"
        self._sort_desc = True

        # Last-snapshot counters for the statusbar.
        self.last_total = 0
        self.last_shown = 0
        self.last_kthreads_hidden = 0

        self._install_sort_funcs()
        self.filter = self.store.filter_new()
        self.filter.set_visible_func(self._visible_func)
        self.apply_sort()

    # -- sort -------------------------------------------------------------

    def _install_sort_funcs(self):
        """Numeric columns get an unknowns-last comparator; strings default."""
        for value_col, has_col in (
            (COL_CPU, COL_CPU_HAS), (COL_MEM, COL_MEM_HAS),
            (COL_SWAP, COL_SWAP_HAS), (COL_NICE, COL_NICE_HAS),
            (COL_DISK_R, COL_DISK_R_HAS), (COL_DISK_W, COL_DISK_W_HAS),
            # r093 extended numeric columns.
            (COL_CPU_TIME, COL_CPU_TIME_HAS), (COL_THREADS, COL_THREADS_HAS),
            (COL_MEM_PCT, COL_MEM_PCT_HAS), (COL_SHARED, COL_SHARED_HAS),
            (COL_PSS, COL_PSS_HAS),
            (COL_DISK_R_TOT, COL_DISK_R_TOT_HAS),
            (COL_DISK_W_TOT, COL_DISK_W_TOT_HAS),
            (COL_NET_RX, COL_NET_RX_HAS), (COL_NET_TX, COL_NET_TX_HAS),
            (COL_OOM, COL_OOM_HAS), (COL_STARTED, COL_STARTED_HAS),
            (COL_PPID, COL_PPID_HAS),
        ):
            self.store.set_sort_func(
                value_col, self._num_sort, (value_col, has_col))
        # r067: the visible Process cell holds Pango MARKUP (badges, state
        # styling) that changes every tick — sorting on it reshuffled rows
        # whose names never changed. Sort on the clean stable key instead.
        self.store.set_sort_func(COL_NAME_SORT, self._name_sort, None)

    def _num_sort(self, model, a, b, data):
        value_col, has_col = data
        if has_col is not None:
            ha = model.get_value(a, has_col)
            hb = model.get_value(b, has_col)
            if not ha and not hb:
                pass  # both unknown -> fall through to value compare (both -1)
            elif not ha or not hb:
                # unknowns land VISUALLY LAST regardless of direction: GTK
                # negates the comparator under DESC, so the sign flips there.
                asc = not self._sort_desc
                if not ha:
                    return 1 if asc else -1
                return -1 if asc else 1
        va = self._sort_value(model, a, value_col)
        vb = self._sort_value(model, b, value_col)
        return (va > vb) - (va < vb)

    @staticmethod
    def _sort_value(model, it, value_col):
        # r084: reads/writes sort on their own field — the read+write
        # combined comparator went with the combined column.
        return model.get_value(it, value_col)

    def _name_sort(self, model, a, b, _data):
        va = model.get_value(a, COL_NAME_SORT)
        vb = model.get_value(b, COL_NAME_SORT)
        return (va > vb) - (va < vb)

    def set_sort(self, key, descending):
        """Adopt a logical sort key + direction (persisted by the page)."""
        if key == "process":
            key = "name"  # r067: the Process header sorts on the stable name
        if key not in SORT_COLUMNS and key != "name":
            key = "cpu"
        self._sort_key = key
        self._sort_desc = bool(descending)
        self.apply_sort()

    def apply_sort(self):
        if self._sort_key in ("name", "process"):
            order = Gtk.SortType.DESCENDING if self._sort_desc else Gtk.SortType.ASCENDING
            self.store.set_sort_column_id(COL_NAME_SORT, order)
            return
        value_col, _has = SORT_COLUMNS[self._sort_key]
        order = Gtk.SortType.DESCENDING if self._sort_desc else Gtk.SortType.ASCENDING
        self.store.set_sort_column_id(value_col, order)

    def sort_key_for_column(self, value_col):
        """Reverse-map a store value column to its logical sort key (or None)."""
        if value_col == COL_NAME_SORT:
            return "name"
        for key, (col, _has) in SORT_COLUMNS.items():
            if col == value_col:
                return key
        return None

    # -- filter -----------------------------------------------------------

    def visible_count(self):
        """Rows passing the current scope+filter (r058 close-review P2-6 —
        the strip must reflect what the operator actually sees)."""
        it = self.filter.iter_children(None)
        n = 0
        while it is not None:
            n += 1
            it = self.filter.iter_next(it)
        return n


    def set_query(self, text, regex=False):
        self._query = text or ""
        self._regex = bool(regex)
        self._regex_pat = None
        if self._regex and self._query:
            try:
                self._regex_pat = re.compile(self._query, re.IGNORECASE)
            except re.error:
                self._regex_pat = None  # invalid regex -> match nothing typed
        self.filter.refilter()

    def set_scope(self, scope):
        self._scope = scope if scope in ("all", "mine", "system", "active") else "all"
        self.filter.refilter()

    def set_show_kernel_threads(self, show):
        self._show_kthreads = bool(show)
        self.filter.refilter()

    def _visible_func(self, model, it, _data):
        if self._batching:
            return True  # cheap during a diff batch; one real refilter at end
        if not self._show_kthreads and model.get_value(it, COL_IS_KTHREAD):
            return False

        scope = self._scope
        if scope == "mine":
            if model.get_value(it, COL_USER) != self._me:
                return False
        elif scope == "system":
            if model.get_value(it, COL_USER) != "root":
                return False
        elif scope == "active":
            if not (model.get_value(it, COL_CPU_HAS)
                    and model.get_value(it, COL_CPU) > 0.0):
                return False

        if self._query:
            name = model.get_value(it, COL_NAME) or ""
            if self._regex:
                if self._regex_pat is None or not self._regex_pat.search(name):
                    return False
            elif self._query.lower() not in name.lower():
                return False
        return True

    # -- diff -------------------------------------------------------------

    def _budget_trim(self, items):
        """Return the top-``budget`` ``(key, record)`` items under the sort."""
        field = _SORT_RECORD_FIELD.get(self._sort_key)

        def key_func(item):
            rec = item[1]
            value = rec.get(field)
            # Unknowns to the extreme end so a trimmed set keeps real rows.
            return (value is not None, value if value is not None else -1)

        ordered = sorted(items, key=key_func, reverse=self._sort_desc)
        return ordered[:self._budget]

    def apply_snapshot(self, procs):
        """Apply one snapshot's ``procs`` (``{(pid,starttime): record}``).

        Diff-in-place: update/insert/remove, sort blocked and filter suspended
        around the batch, then one sort restore + one refilter.
        """
        items = list(procs.items())
        self.last_total = len(items)
        if not self._show_kthreads:
            self.last_kthreads_hidden = sum(
                1 for _key, rec in items if rec.get("is_kthread"))
        else:
            self.last_kthreads_hidden = 0

        if len(items) > self._budget:
            items = self._budget_trim(items)
        self.last_shown = len(items)

        rows = {key: record_to_row(rec) for key, rec in items}

        # Suspend sort + filter around the batch (one re-sort + one refilter at
        # the end) so neither runs per-row. The sort is restored from our own
        # tracked (key, direction) — never read back from the store, whose
        # get_sort_column_id() arity is not stable across PyGObject versions.
        self._batching = True
        self.store.set_sort_column_id(_UNSORTED, Gtk.SortType.ASCENDING)
        try:
            self._diff(rows)
        finally:
            self._batching = False
            self.apply_sort()
            self.filter.refilter()

    def _diff(self, rows):
        # Update existing rows in place; append genuinely new pids.
        for key, row in rows.items():
            # store-side identity uses the COERCED starttime (None->0) that
            # row-8 holds, so key_at_child_path round-trips exactly (r058 P2-8)
            store_key = (key[0], key[1] if key[1] is not None else 0)
            ref = self._refs.get(store_key)
            if ref is not None and ref.valid():
                self._update_row(self.store.get_iter(ref.get_path()), row)
            else:
                it = self.store.append(row)
                self._refs[store_key] = Gtk.TreeRowReference.new(
                    self.store, self.store.get_path(it))

        # Remove pids gone this snapshot. Re-fetch the iter from the row
        # reference immediately before each removal — never cache iters across
        # removals (they invalidate; TreeRowReference tracks the shift).
        gone = [key for key in self._refs if key not in rows]
        for key in gone:
            ref = self._refs.pop(key)
            if ref is not None and ref.valid():
                self.store.remove(self.store.get_iter(ref.get_path()))

    def _update_row(self, it, row):
        """Write only the changed cells (no full row rewrite = no flicker)."""
        for col in range(N_COLUMNS):
            if self.store.get_value(it, col) != row[col]:
                self.store.set_value(it, col, row[col])

    # -- selection identity ----------------------------------------------

    def key_at_child_path(self, child_path):
        """``(pid, starttime)`` for a store (child-model) path."""
        it = self.store.get_iter(child_path)
        return (self.store.get_value(it, COL_PID),
                self.store.get_value(it, COL_STARTTIME))

    def child_path_for_key(self, key):
        """Store path for an identity, or ``None`` if it is gone this snapshot."""
        ref = self._refs.get(key)
        if ref is not None and ref.valid():
            return ref.get_path()
        return None
