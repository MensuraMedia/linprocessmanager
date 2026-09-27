"""Band + Basics wiring tests (metric-band-basics.md acceptance).

The pure ranking/reading math lives in test_manager_rank.py. Here we cover the
pieces that touch the GTK model/page modules:

- band layout: the six Variant-2 gauges, in order, and the honest states
  (Network empty-state, Load "—" until a reader lands);
- the click -> select round-trip: a key produced by the ranking model resolves
  to a live, selectable row in the process table model.

The process-table model (ListStore/TreeModelFilter) are non-widget GObjects, so
NO display is needed; the suite skips if the bindings are unavailable.
"""

import pytest

pytest.importorskip("gi")

try:
    from ui import process_model as pm
    from pages import page_processes as pp
    from pages import page_basics as pb
except (ImportError, ValueError) as exc:  # missing typelib etc.
    pytest.skip("GTK bindings unavailable: %s" % exc, allow_module_level=True)

from modules import manager_rank as mr


def rec(pid, starttime=111, name="proc", user="alice", state="S", unit=None,
        cpu=0.0, mem=1024, swap=0, rd=0.0, wr=0.0, nice=0,
        kthread=False, defunct=False, ppid=1):
    return {
        "pid": pid, "starttime": starttime, "name": name, "user": user,
        "state": state, "ppid": ppid, "unit": unit, "cpu_pct": cpu,
        "mem_rss": mem, "mem_vsize": mem, "mem_shared": 0, "mem_swap": swap,
        "io_read_rate": rd, "io_write_rate": wr, "nice": nice, "threads": 1,
        "is_kthread": kthread, "is_defunct": defunct, "from_backoff": False,
        "rollup": None,
    }


def procs(*records):
    return {(r["pid"], r["starttime"]): r for r in records}


# --- band layout ------------------------------------------------------------

def test_band_has_six_variant2_gauges_in_order():
    metrics = [m for m, _label in pp._BAND_GAUGES]
    assert metrics == ["cpu", "memory", "swap", "disk", "network", "load"]
    # Both the band and the Basics page expose the same six, same order.
    assert [m for m, _l in pb._GAUGES] == metrics


def test_network_empty_state_is_honest_and_shared():
    assert pp._NET_EMPTY == pb._NET_EMPTY
    assert "per-process network not available from /proc" in pp._NET_EMPTY
    assert "interface totals on Resources" in pp._NET_EMPTY


def test_zone_rgb_covers_every_zone():
    for zone in (mr.ZONE_NOMINAL, mr.ZONE_MEDIUM, mr.ZONE_NEAR):
        assert zone in pp._ZONE_RGB
        assert zone in pb._ZONE_RGB


# --- click -> select round-trip ---------------------------------------------

def test_top_contributor_key_resolves_to_a_selectable_row():
    model = pm.ProcessTableModel()
    snap = procs(rec(1, cpu=5.0), rec(2, cpu=90.0), rec(3, cpu=50.0))
    model.apply_snapshot(snap)

    top = mr.rank_processes(snap, "cpu", limit=1)[0]
    assert top["pid"] == 2                       # the popover's first row

    # The page encodes the row target as (pid, starttime) and the select handler
    # coerces starttime the same way the store does; that key must resolve.
    key = top["key"]
    store_key = (key[0], key[1] if key[1] is not None else 0)
    child = model.child_path_for_key(store_key)
    assert child is not None
    path = model.filter.convert_child_path_to_path(child)
    assert path is not None
    assert model.key_at_child_path(child) == (2, 111)


def test_filtered_out_contributor_has_no_visible_path():
    # A kernel thread is hidden by default: its key still resolves in the store
    # but not through the filter -> the page reports "filtered out", never crash.
    model = pm.ProcessTableModel()
    snap = procs(rec(1, cpu=1.0), rec(7, cpu=99.0, kthread=True))
    model.apply_snapshot(snap)
    child = model.child_path_for_key((7, 111))
    assert child is not None
    assert model.filter.convert_child_path_to_path(child) is None
