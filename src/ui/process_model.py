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
N_COLUMNS = 20

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
]

# Logical (persisted) sort-key -> the (value_col, has_col) it maps to. Columns
# always present (pid) carry has_col=None. "disk_rw" sorts on read+write.
SORT_COLUMNS = {
    "cpu": (COL_CPU, COL_CPU_HAS),
    "memory": (COL_MEM, COL_MEM_HAS),
    "swap": (COL_SWAP, COL_SWAP_HAS),
    "disk_rw": (COL_DISK_R, COL_DISK_R_HAS),   # secondary handled in _num_sort
    "nice": (COL_NICE, COL_NICE_HAS),
    "pid": (COL_PID, None),
    "process": (COL_NAME, None),
    "user": (COL_USER, None),
    "state": (COL_STATE, None),
}

# Record field a logical sort-key reads for the Python-side budget pre-sort.
_SORT_RECORD_FIELD = {
    "cpu": "cpu_pct", "memory": "mem_rss", "swap": "mem_swap",
    "nice": "nice", "pid": "pid", "process": "name", "user": "user",
    "state": "state",
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
            (COL_DISK_R, COL_DISK_R_HAS),
        ):
            self.store.set_sort_func(
                value_col, self._num_sort, (value_col, has_col))

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
        if value_col == COL_DISK_R:  # "Disk r/w" sorts on read+write combined
            r = model.get_value(it, COL_DISK_R)
            w = model.get_value(it, COL_DISK_W)
            return (r if r >= 0 else 0) + (w if w >= 0 else 0)
        return model.get_value(it, value_col)

    def set_sort(self, key, descending):
        """Adopt a logical sort key + direction (persisted by the page)."""
        if key not in SORT_COLUMNS:
            key = "cpu"
        self._sort_key = key
        self._sort_desc = bool(descending)
        self.apply_sort()

    def apply_sort(self):
        value_col, _has = SORT_COLUMNS[self._sort_key]
        order = Gtk.SortType.DESCENDING if self._sort_desc else Gtk.SortType.ASCENDING
        self.store.set_sort_column_id(value_col, order)

    def sort_key_for_column(self, value_col):
        """Reverse-map a store value column to its logical sort key (or None)."""
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
            if self._sort_key == "disk_rw":
                r = rec.get("io_read_rate") or 0
                w = rec.get("io_write_rate") or 0
                return (True, r + w)
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
