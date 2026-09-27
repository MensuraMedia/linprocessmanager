"""Graphs hub/detail wiring tests (graphs-hub.md acceptance).

The pure ring/stat math lives in test_graphs.py. Here we cover the pieces that
touch GTK-importing page/UI modules — module-level constants and the pure helpers
that back the hub grid, the detail skeleton, and the Resources retirement.

Following the suite convention, nothing instantiates a page widget (that needs a
display); we assert on module constants + pure functions and resolve a
contributor key through the non-widget process-table model. Skips if the GTK
bindings are unavailable.
"""

import pytest

pytest.importorskip("gi")

try:
    from ui import process_model as pm
    from ui import sidebar
    import pages
    from pages import page_graphs as pg
    from pages import graph_details as gd
    from pages import page_processes as pp
    from pages import page_basics as pb
except (ImportError, ValueError) as exc:  # missing typelib etc.
    pytest.skip("GTK bindings unavailable: %s" % exc, allow_module_level=True)

from modules import manager_rank as mr


# --- Resources retirement / Graphs arrival ----------------------------------

def test_sidebar_retires_resources_and_adds_graphs():
    ids = [page_id for _label, page_id, _top in sidebar.NAV_ITEMS]
    assert "resources" not in ids          # retired (r061)
    assert "graphs" in ids                  # the hub takes its place
    # Graphs sits between Processes and Disks.
    assert ids.index("processes") < ids.index("graphs") < ids.index("disks")


def test_pages_package_exports_graphs_not_resources():
    assert hasattr(pages, "GraphsHubPage")
    assert hasattr(pages, "GraphDetailPage")
    assert not hasattr(pages, "ResourcesPage")


# --- Hub grid: seven charts, click-through targets ---------------------------

def test_hub_has_seven_charts_in_order():
    series = [spec.series for spec in pg.HUB_CHARTS]
    assert series == ["cpu", "memory", "swap", "disk", "network",
                      "psi_cpu", "load"]
    assert len(pg.HUB_CHARTS) == 7


def test_every_hub_card_clicks_through_to_a_detail_page():
    detail_ids = {spec.page_id for spec in gd.DETAIL_SPECS}
    for spec in pg.HUB_CHARTS:
        assert spec.page_id in detail_ids   # the card's click target exists


# --- Detail pages inventory + honest states ---------------------------------

def test_detail_page_inventory():
    ids = [spec.page_id for spec in gd.DETAIL_SPECS]
    assert ids == ["graphs_cpu", "graphs_memory", "graphs_swap", "graphs_disk",
                   "graphs_network", "graphs_pressure", "graphs_load"]


def test_network_detail_has_no_per_process_contributors():
    net = next(s for s in gd.DETAIL_SPECS if s.page_id == "graphs_network")
    assert net.mr_metric is None            # honest empty-state, no drill
    assert "per-process network not available from /proc" in gd._NET_EMPTY


def test_load_detail_ships_with_real_data_ranked_by_cpu():
    load = next(s for s in gd.DETAIL_SPECS if s.page_id == "graphs_load")
    assert load.series == "load"            # the loadavg ring lands this task
    assert load.mr_metric == "load"         # contributors ranked by CPU


def test_pressure_detail_draws_the_psi_triple():
    psi = next(s for s in gd.DETAIL_SPECS if s.page_id == "graphs_pressure")
    assert psi.series == "psi_cpu"
    assert psi.extra_series == ("psi_mem", "psi_io")


# --- Breakdown rows (pure helper) -------------------------------------------

def test_breakdown_cores_rows_match_snapshot_and_show_dash_for_none():
    system = {"cpu": {"per_core": {0: 30.0, 1: None}}}
    rows = gd.breakdown_rows("cores", system)
    assert rows == ["Core 0: 30%", "Core 1: —"]


def test_breakdown_devices_and_ifaces():
    system = {
        "disks": {"sda": {"util": 20.0, "read_rate": 1024, "write_rate": None}},
        "net": {"eth0": {"rx_rate": 2048, "tx_rate": 1024}},
    }
    assert gd.breakdown_rows("devices", system)[0].startswith("sda: 20% util")
    assert gd.breakdown_rows("ifaces", system) == ["eth0: ↓2.0 KB/s ↑1.0 KB/s"]


def test_breakdown_none_kind_is_empty():
    assert gd.breakdown_rows(None, {"cpu": {"per_core": {0: 1.0}}}) == []


# --- Network empty-state repointed off the retired Resources page -----------

def test_net_empty_repointed_to_network_graph_and_shared():
    assert pp._NET_EMPTY == pb._NET_EMPTY
    assert "per-process network not available from /proc" in pp._NET_EMPTY
    assert "Resources" not in pp._NET_EMPTY           # no dead nav reference
    assert "Network graph" in pp._NET_EMPTY


# --- Click-through: a contributor key resolves to a selectable row -----------

def _rec(pid, starttime=111, cpu=0.0):
    return {"pid": pid, "starttime": starttime, "name": "p", "user": "u",
            "state": "S", "ppid": 1, "unit": None, "cpu_pct": cpu,
            "mem_rss": 1, "mem_vsize": 1, "mem_shared": 0, "mem_swap": 0,
            "io_read_rate": 0.0, "io_write_rate": 0.0, "nice": 0, "threads": 1,
            "is_kthread": False, "is_defunct": False, "from_backoff": False,
            "rollup": None}


def test_cpu_contributor_key_resolves_in_process_model():
    procs = {(r["pid"], r["starttime"]): r
             for r in (_rec(1, cpu=5.0), _rec(2, cpu=90.0))}
    model = pm.ProcessTableModel()
    model.apply_snapshot(procs)
    top = mr.rank(procs, "cpu", mode="by_process", limit=1)[0]
    assert top["pid"] == 2
    key = top["key"]
    store_key = (key[0], key[1] if key[1] is not None else 0)
    assert model.child_path_for_key(store_key) is not None
