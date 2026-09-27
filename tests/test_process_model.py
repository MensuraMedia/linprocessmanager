"""Tests for src/ui/process_model.py (process-table.md acceptance).

Diff-in-place (update/insert/remove preserves row identity + selection key),
the None -> (-1, has_data=False) boundary translation, unknown-value sort
placement, filter (kernel-thread hide / scope / query substring + regex), and
the row-budget top-N trim. GTK is required (ListStore/TreeModelFilter are
non-widget GObjects, so NO display is needed); the suite skips if the bindings
are unavailable.
"""

import pytest

pytest.importorskip("gi")

try:
    from ui import process_model as pm
except (ImportError, ValueError) as exc:  # missing typelib etc.
    pytest.skip("GTK bindings unavailable: %s" % exc, allow_module_level=True)


def rec(pid, starttime=111, name="proc", user="alice", state="S", unit=None,
        cpu=0.0, mem=1024, swap=0, rd=0.0, wr=0.0, nice=0,
        kthread=False, defunct=False):
    return {
        "pid": pid, "starttime": starttime, "name": name, "user": user,
        "state": state, "ppid": 1, "unit": unit, "cpu_pct": cpu,
        "mem_rss": mem, "mem_vsize": mem, "mem_shared": 0, "mem_swap": swap,
        "io_read_rate": rd, "io_write_rate": wr, "nice": nice, "threads": 1,
        "is_kthread": kthread, "is_defunct": defunct, "from_backoff": False,
        "rollup": None,
    }


def procs(*records):
    return {(r["pid"], r["starttime"]): r for r in records}


def store_rows(model):
    rows = []
    it = model.store.get_iter_first()
    while it is not None:
        rows.append(tuple(model.store[it]))
        it = model.store.iter_next(it)
    return rows


def visible_pids(model):
    pids = []
    it = model.filter.get_iter_first()
    while it is not None:
        pids.append(model.filter.get_value(it, pm.COL_PID))
        it = model.filter.iter_next(it)
    return pids


# --- boundary translation ---------------------------------------------------

def test_record_to_row_none_becomes_sentinel_plus_has_flag():
    row = pm.record_to_row(rec(10, cpu=None, mem=None, rd=None, nice=None))
    assert row[pm.COL_CPU] == -1.0 and row[pm.COL_CPU_HAS] is False
    assert row[pm.COL_MEM] == -1 and row[pm.COL_MEM_HAS] is False
    assert row[pm.COL_DISK_R] == -1.0 and row[pm.COL_DISK_R_HAS] is False
    assert row[pm.COL_NICE] == -1 and row[pm.COL_NICE_HAS] is False


def test_record_to_row_present_values_keep_has_true():
    row = pm.record_to_row(rec(10, cpu=12.5, mem=2048, unit="—"))
    assert row[pm.COL_CPU] == 12.5 and row[pm.COL_CPU_HAS] is True
    assert row[pm.COL_MEM] == 2048 and row[pm.COL_MEM_HAS] is True
    assert row[pm.COL_UNIT] == ""  # the sampler's "—" placeholder is blanked


# --- diff-in-place -----------------------------------------------------------

def test_diff_insert_update_remove_counts():
    model = pm.ProcessTableModel()
    model.apply_snapshot(procs(rec(1), rec(2), rec(3)))
    assert len(store_rows(model)) == 3

    # 2 stays, 3 gone, 4 new.
    model.apply_snapshot(procs(rec(1), rec(2), rec(4)))
    pids = sorted(r[pm.COL_PID] for r in store_rows(model))
    assert pids == [1, 2, 4]


def test_surviving_row_keeps_its_reference_object():
    model = pm.ProcessTableModel()
    model.apply_snapshot(procs(rec(1), rec(2)))
    ref = model._refs[(1, 111)]
    model.apply_snapshot(procs(rec(1, cpu=50.0), rec(2)))  # 1 updated in place
    assert model._refs[(1, 111)] is ref            # not rebuilt (no flicker)
    assert model.child_path_for_key((1, 111)) is not None


def test_selection_key_survives_refresh():
    model = pm.ProcessTableModel()
    model.apply_snapshot(procs(rec(5, cpu=1.0), rec(6)))
    path_before = model.child_path_for_key((5, 111))
    key = model.key_at_child_path(path_before)
    assert key == (5, 111)
    model.apply_snapshot(procs(rec(5, cpu=90.0), rec(6), rec(7)))
    # Identity still resolves to a live row after the refresh.
    assert model.child_path_for_key((5, 111)) is not None


def test_recycled_pid_is_a_distinct_row():
    model = pm.ProcessTableModel()
    model.apply_snapshot(procs(rec(9, starttime=100)))
    model.apply_snapshot(procs(rec(9, starttime=200)))  # same pid, recycled
    assert model.child_path_for_key((9, 100)) is None
    assert model.child_path_for_key((9, 200)) is not None


# --- sort: unknowns last -----------------------------------------------------

def test_unknown_values_sort_last_under_desc():
    model = pm.ProcessTableModel()
    model.set_sort("cpu", descending=True)
    model.apply_snapshot(procs(
        rec(1, cpu=5.0), rec(2, cpu=None), rec(3, cpu=50.0), rec(4, cpu=None)))
    has_flags = [r[pm.COL_CPU_HAS] for r in store_rows(model)]
    # every known (True) precedes every unknown (False)
    assert has_flags == sorted(has_flags, reverse=True)
    knowns = [r[pm.COL_CPU] for r in store_rows(model) if r[pm.COL_CPU_HAS]]
    assert knowns == sorted(knowns, reverse=True)

def test_unknown_values_sort_last_under_asc():
    """r058 close-review P1: under ASCENDING the GTK comparator flips, so the
    pre-fix code floated unknowns to the TOP. They must land last here too."""
    model = pm.ProcessTableModel()
    model.set_sort("cpu", descending=False)
    model.apply_snapshot(procs(
        rec(1, cpu=5.0), rec(2, cpu=None), rec(3, cpu=50.0), rec(4, cpu=None)))
    has_flags = [r[pm.COL_CPU_HAS] for r in store_rows(model)]
    assert has_flags == sorted(has_flags, reverse=True)  # unknowns last
    knowns = [r[pm.COL_CPU] for r in store_rows(model) if r[pm.COL_CPU_HAS]]
    assert knowns == sorted(knowns)


# --- filter ------------------------------------------------------------------

def test_kernel_threads_hidden_by_default():
    model = pm.ProcessTableModel()
    model.apply_snapshot(procs(rec(1, kthread=False), rec(2, kthread=True)))
    assert visible_pids(model) == [1]
    assert model.last_kthreads_hidden == 1
    model.set_show_kernel_threads(True)
    assert sorted(visible_pids(model)) == [1, 2]


def test_scope_mine_and_system_and_active():
    model = pm.ProcessTableModel()
    model._me = "alice"  # deterministic "my processes"
    model.apply_snapshot(procs(
        rec(1, user="alice", cpu=0.0),
        rec(2, user="root", cpu=3.0),
        rec(3, user="bob", cpu=0.0)))
    model.set_scope("mine")
    assert visible_pids(model) == [1]
    model.set_scope("system")
    assert visible_pids(model) == [2]
    model.set_scope("active")
    assert visible_pids(model) == [2]  # only cpu > 0
    model.set_scope("all")
    assert sorted(visible_pids(model)) == [1, 2, 3]


def test_query_substring_and_regex():
    model = pm.ProcessTableModel()
    model.apply_snapshot(procs(
        rec(1, name="firefox"), rec(2, name="bash"), rec(3, name="fish")))
    model.set_query("fi")
    assert sorted(visible_pids(model)) == [1, 3]
    model.set_query(r"^fish$", regex=True)
    assert visible_pids(model) == [3]
    model.set_query("[", regex=True)  # invalid regex -> matches nothing
    assert visible_pids(model) == []
    model.set_query("")               # cleared -> all visible
    assert sorted(visible_pids(model)) == [1, 2, 3]


# --- row budget --------------------------------------------------------------

def test_row_budget_trims_to_top_n_under_sort():
    model = pm.ProcessTableModel(row_budget=3)
    model.set_sort("cpu", descending=True)
    model.apply_snapshot(procs(
        rec(1, cpu=1.0), rec(2, cpu=2.0), rec(3, cpu=3.0),
        rec(4, cpu=4.0), rec(5, cpu=5.0)))
    assert model.last_total == 5
    assert model.last_shown == 3
    assert len(store_rows(model)) == 3
    kept = sorted(r[pm.COL_PID] for r in store_rows(model))
    assert kept == [3, 4, 5]  # top-3 by cpu


def test_name_sort_stable_across_value_churn():
    """r067 operator bug: clicking the Process header silently sorted by CPU
    (unknown-key fallback), so rows reshuffled every tick. Sorting by name
    must use the stable clean-name key and hold order while values churn."""
    model = pm.ProcessTableModel()
    model.set_sort("process", descending=False)   # header key is "process"
    # alphabetical insert: alpha, beta, gamma
    model.apply_snapshot(procs(
        rec(1, name="beta", cpu=30.0, state="S"),
        rec(2, name="alpha", cpu=10.0, state="R"),
        rec(3, name="gamma", cpu=20.0, state="S"),
    ))
    names = [r[pm.COL_NAME] for r in store_rows(model)]
    assert names == ["alpha", "beta", "gamma"]

    # next tick: CPU values churn hard, states/unit badges change, one gains
    # swap — names unchanged, so the ALPHA-BETICAL ORDER MUST NOT MOVE
    # (pre-fix, the header fell back to a live CPU sort and reshuffled).
    model.apply_snapshot(procs(
        rec(1, name="beta", cpu=90.0, state="R"),
        rec(2, name="alpha", cpu=1.0, state="S"),
        rec(3, name="gamma", cpu=55.0, state="D"),
    ))
    names = [r[pm.COL_NAME] for r in store_rows(model)]
    assert names == ["alpha", "beta", "gamma"]


def test_disk_read_write_split_sort_and_columns(r025_unused=None):
    """r084: the combined disk_rw column split into Reads/Writes — each is
    its own logical column, sorts on its own field, and unknowns stay
    unknowns. The legacy persisted key migrates on load."""
    model = pm.ProcessTableModel()
    model.apply_snapshot(procs(
        rec(1, rd=100.0, wr=5.0),
        rec(2, rd=10.0, wr=900.0),
        rec(3, rd=0.0, wr=0.0),
    ))
    assert "disk_read" in pm.SORT_COLUMNS and "disk_write" in pm.SORT_COLUMNS

    model.set_sort("disk_read", descending=True)
    assert [r[pm.COL_PID] for r in store_rows(model)][0] == 1
    model.set_sort("disk_write", descending=True)
    assert [r[pm.COL_PID] for r in store_rows(model)][0] == 2

    from config.app_settings import AppSettings
    migrated = AppSettings({
        "columns": {"visible": ["process", "disk_rw"],
                    "widths": {"disk_rw": 140}},
        "sort": {"column": "disk_rw", "direction": "desc"},
    }).as_dict()
    assert migrated["columns"]["visible"] == ["process", "disk_read",
                                              "disk_write"]
    assert migrated["columns"]["widths"]["disk_read"] == 140
    assert migrated["sort"]["column"] == "disk_read"
