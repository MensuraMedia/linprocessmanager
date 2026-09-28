"""Tests for the process preview pane (docs/modules/process-preview.md §2).

Following the suite convention, no page/pane widget is instantiated (that needs
a display); the pane's rendered content is computed by the PURE
``preview_model`` + ancestry/children/net helpers, which are exercised here
against plain snapshot dicts. GTK is required only because the module imports
the compat toolkit at top; the suite skips if the bindings are unavailable.
"""

import os

import pytest

pytest.importorskip("gi")

try:
    from ui import process_preview as pv
except (ImportError, ValueError) as exc:  # missing typelib etc.
    pytest.skip("GTK bindings unavailable: %s" % exc, allow_module_level=True)

import manager_actions as ma

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
PROC = os.path.join(FIX, "proc")


def _rec(pid, starttime=1, ppid=1, name=None, cpu=0.0, rss=1024,
         net_rx=0.0, net_tx=0.0, **extra):
    rec = {
        "pid": pid, "starttime": starttime, "ppid": ppid,
        "name": name or ("p%d" % pid), "state": "S", "unit": None,
        "cpu_pct": cpu, "mem_rss": rss, "mem_vsize": rss * 2, "mem_shared": 0,
        "mem_swap": 0, "threads": 1, "nice": 0, "oom_score": 0,
        "cpu_time": 0.0, "mem_pct": 0.0, "io_read_total": 0, "io_write_total": 0,
        "io_read_rate": 0.0, "io_write_rate": 0.0, "net_rx_rate": net_rx,
        "net_tx_rate": net_tx, "affinity": None, "cmdline": None,
        "started": None, "is_kthread": False, "is_defunct": False,
        "rollup": None,
    }
    rec.update(extra)
    return rec


def _procs(*recs):
    return {(r["pid"], r["starttime"]): r for r in recs}


# --- ancestry ordering ------------------------------------------------------

def test_ancestry_chain_is_root_to_selected():
    procs = _procs(
        _rec(1, ppid=0), _rec(10, ppid=1), _rec(100, ppid=10))
    chain = pv.ancestry_chain(procs, (100, 1))
    assert chain == [(1, 1), (10, 1), (100, 1)]   # root first, selected last


def test_ancestry_stops_at_unknown_parent():
    # ppid 999 is not in the snapshot (orphaned subtree) -> chain starts at 50.
    procs = _procs(_rec(50, ppid=999), _rec(60, ppid=50))
    assert pv.ancestry_chain(procs, (60, 1)) == [(50, 1), (60, 1)]


def test_ancestry_cycle_safe():
    # a ppid cycle must not loop forever.
    procs = _procs(_rec(1, ppid=2), _rec(2, ppid=1))
    chain = pv.ancestry_chain(procs, (1, 1))
    assert chain[-1] == (1, 1)
    assert len(chain) == len(set(chain))


def test_children_and_descendants():
    procs = _procs(
        _rec(1, ppid=0), _rec(10, ppid=1), _rec(11, ppid=1), _rec(100, ppid=10))
    assert pv.child_keys(procs, (1, 1)) == [(10, 1), (11, 1)]
    assert sorted(pv.descendant_keys(procs, (1, 1))) == [(10, 1), (11, 1),
                                                         (100, 1)]


# --- network attribution rows ----------------------------------------------

def test_net_summary_self_children_combined():
    procs = _procs(
        _rec(1, ppid=0, net_rx=100.0, net_tx=10.0),
        _rec(10, ppid=1, net_rx=50.0, net_tx=5.0),
        _rec(11, ppid=1, net_rx=25.0, net_tx=None))  # one child restricted tx
    net = pv.net_summary(procs, (1, 1))
    assert net["self"] == (100.0, 10.0)
    assert len(net["children"]) == 2
    # combined = self + descendants; the None tx is excluded, not summed as 0.
    assert net["combined"][0] == pytest.approx(175.0)
    assert net["combined"][1] == pytest.approx(15.0)


def test_net_summary_all_none_is_none_not_zero():
    procs = _procs(_rec(1, ppid=0, net_rx=None, net_tx=None))
    net = pv.net_summary(procs, (1, 1))
    assert net["self"] == (None, None)
    assert net["combined"] == (None, None)   # honest absence


def test_fmt_net_cell_locks_unknown():
    assert pv._fmt_net_cell(None) == "🔒 —"       # restricted -> lock + dash
    assert pv._fmt_net_cell(0.0) == "0 B/s"        # a real zero is shown
    assert pv._fmt_net_cell(2048.0) == "2.0 KB/s"


# --- preview_model bundle ---------------------------------------------------

def test_preview_model_sections_and_dependency_injection():
    procs = _procs(
        _rec(1, ppid=0), _rec(10, ppid=1, name="child"),
        _rec(100, ppid=10, name="app", cpu=12.5, rss=4096,
             cmdline="/usr/bin/app -x", affinity=(0, 1),
             rollup={"pss_bytes": 2048}))
    model = pv.preview_model(procs, {}, (100, 1),
                             dependencies=(["libc.so.6"], 5))
    assert model["identity"]["name"] == "app"
    assert model["identity"]["cmdline"] == "/usr/bin/app -x"
    assert model["kpi"]["cpu"] == 12.5
    assert model["resource"]["pss"] == 2048          # rides the rollup
    assert model["ancestry"] == [((1, 1), "p1"), ((10, 1), "child"),
                                 ((100, 1), "app")]
    assert model["dependencies"] == (["libc.so.6"], 5)


def test_preview_model_unknown_key_is_none():
    assert pv.preview_model({}, {}, (999, 1)) is None


# --- dependencies through the actions layer (boundary law) -------------------

def test_dependencies_reads_maps_via_actions_layer():
    names, count = ma.dependencies((100, 123456), proc_root=PROC)
    assert names[:2] == ["bash", "libc.so.6"]
    assert count == 3
