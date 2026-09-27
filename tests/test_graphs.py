"""Pure-logic tests for the Graphs feature ring store (Phase 5).

Covers :mod:`modules.manager_history` — the shared ``(ts, value)`` ring store and
its snapshot->series projection + window statistics — entirely without a display
(no GTK). The widget-touching hub/detail constants live in test_graphs_ui.py.

Ring law (resource-graphs.md): (ts, value) tuples, backoff excluded at insert,
gaps as gaps, sized for ~5 min; window selector 1 m / 5 m only.
"""

from types import SimpleNamespace

import manager_history as mh


# ---------------------------------------------------------------------------
# Ring: insert / slice / last / backoff exclusion / eviction.
# ---------------------------------------------------------------------------

def test_insert_and_last_returns_ts_value_tuple():
    h = mh.History()
    h.insert("cpu", 10.0, 42.0)
    assert h.last("cpu") == (10.0, 42.0)


def test_last_of_empty_series_is_none():
    assert mh.History().last("cpu") is None


def test_backoff_samples_are_excluded_at_insert():
    h = mh.History()
    h.insert("cpu", 1.0, 10.0)
    h.insert("cpu", 2.0, 99.0, from_backoff=True)   # a gap, not a point
    assert h.last("cpu") == (1.0, 10.0)
    assert h.slice("cpu", 100.0) == [(1.0, 10.0)]


def test_none_values_are_stored_as_gaps():
    # A no-data instant is a real (ts, None) point (renderers break the line).
    h = mh.History()
    h.insert("cpu", 1.0, None)
    h.insert("cpu", 2.0, 5.0)
    assert h.slice("cpu", 100.0) == [(1.0, None), (2.0, 5.0)]


def test_maxlen_evicts_oldest():
    h = mh.History(maxlen=3, retention_s=1e9)
    for ts in range(5):
        h.insert("cpu", float(ts), float(ts))
    pts = h.slice("cpu", 1e9)
    assert [t for t, _v in pts] == [2.0, 3.0, 4.0]   # oldest two dropped


def test_retention_trims_old_points_on_insert():
    h = mh.History(maxlen=1000, retention_s=50.0)
    h.insert("cpu", 0.0, 1.0)
    h.insert("cpu", 40.0, 2.0)
    h.insert("cpu", 100.0, 3.0)   # cutoff = 50 -> ts 0 and 40 evicted
    assert h.slice("cpu", 1e9) == [(100.0, 3.0)]


def test_slice_window_is_anchored_on_newest():
    h = mh.History(retention_s=1e9)
    for ts in (100.0, 130.0, 150.0, 160.0):
        h.insert("cpu", ts, ts)
    # window 40 s from newest (160) -> cutoff 120 -> 130,150,160.
    pts = h.slice("cpu", 40.0)
    assert [t for t, _v in pts] == [130.0, 150.0, 160.0]


def test_slice_empty_series_is_empty_list():
    assert mh.History().slice("cpu", 60.0) == []


# ---------------------------------------------------------------------------
# series_values: snapshot.system -> the nine series scalars.
# ---------------------------------------------------------------------------

def _system():
    return {
        "cpu": {"pct": 40.0, "per_core": {0: 30.0, 1: 50.0}, "ncpu": 2},
        "mem": {"total": 100, "used": 60, "available": 40,
                "swap_total": 10, "swap_free": 4},
        "disks": {"sda": {"util": 20.0, "read_rate": 100, "write_rate": 50}},
        "net": {"eth0": {"rx_rate": 1000.0, "tx_rate": 500.0}},
        "psi": {"cpu": {"some": {"avg10": 1.5}},
                "memory": {"some": {"avg10": 2.5}},
                "io": {"some": {"avg10": 3.5}}},
        "load": {"load1": 0.7, "load5": 0.6, "load15": 0.5,
                 "runnable": 1, "total": 100},
    }


def test_series_values_projects_every_series():
    v = mh.series_values(_system())
    assert set(v) == set(mh.SERIES)
    assert v["cpu"] == 40.0
    assert v["memory"] == 60.0             # 100 * 60/100
    assert v["swap"] == 60.0               # used 6 of 10
    assert v["disk"] == 20.0               # busiest util
    assert v["network"] == 1500.0          # rx + tx
    assert v["load"] == 0.7
    assert v["psi_cpu"] == 1.5
    assert v["psi_mem"] == 2.5
    assert v["psi_io"] == 3.5


def test_series_values_degrade_to_none_on_absent_sections():
    v = mh.series_values({})
    assert v["cpu"] is None
    assert v["network"] is None
    assert v["load"] is None
    assert v["psi_cpu"] is None


# ---------------------------------------------------------------------------
# record: writes every series, excludes backoff snapshots.
# ---------------------------------------------------------------------------

def test_record_writes_all_series_from_snapshot():
    h = mh.History()
    snap = SimpleNamespace(ts=5.0, from_backoff=False, system=_system())
    mh.record(h, snap)
    assert h.last("cpu") == (5.0, 40.0)
    assert h.last("load") == (5.0, 0.7)
    assert h.last("psi_io") == (5.0, 3.5)


def test_record_of_backoff_snapshot_inserts_nothing():
    h = mh.History()
    snap = SimpleNamespace(ts=5.0, from_backoff=True, system=_system())
    mh.record(h, snap)
    assert h.last("cpu") is None


# ---------------------------------------------------------------------------
# window_stats: current / min / avg / max over a slice, ignoring gaps.
# ---------------------------------------------------------------------------

def test_window_stats_ignores_none_and_computes_bounds():
    pts = [(1.0, 10.0), (2.0, None), (3.0, 20.0), (4.0, 30.0)]
    s = mh.window_stats(pts)
    assert s["current"] == 30.0
    assert s["min"] == 10.0
    assert s["max"] == 30.0
    assert s["avg"] == 20.0            # (10+20+30)/3


def test_window_stats_all_none_is_all_none():
    s = mh.window_stats([(1.0, None), (2.0, None)])
    assert s == {"current": None, "min": None, "avg": None, "max": None}


def test_window_stats_empty_is_all_none():
    assert mh.window_stats([]) == {
        "current": None, "min": None, "avg": None, "max": None}
