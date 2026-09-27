"""Tests for src/modules/manager_rank.py (metric-band-basics.md acceptance).

Pure model layer — no GTK, no display: ranking correctness + tie behavior,
ancestry roll-up (firefox tree collapse), unit roll-up, capacity zones, the
Network auto-scale ceiling math, and per-gauge system readings incl. the
degraded/empty states (Network total absent, Load unknown).
"""

# Import the pure module directly off src/modules (conftest puts it on the
# path) so the "modules" package __init__ — which pulls in GTK — is never
# triggered: this tier stays display-free.
import manager_rank as mr


def rec(pid, starttime=100, name=None, user="alice", ppid=1, cpu=None,
        rss=None, swap=None, rd=None, wr=None, unit=None):
    return {
        "pid": pid, "starttime": starttime, "name": name or ("p%d" % pid),
        "user": user, "ppid": ppid, "cpu_pct": cpu, "mem_rss": rss,
        "mem_swap": swap, "io_read_rate": rd, "io_write_rate": wr, "unit": unit,
    }


def procs(*records):
    return {(r["pid"], r["starttime"]): r for r in records}


# --- metric_value -----------------------------------------------------------

def test_metric_value_per_metric():
    r = rec(1, cpu=12.5, rss=2048, swap=64, rd=100.0, wr=50.0)
    assert mr.metric_value(r, "cpu") == 12.5
    assert mr.metric_value(r, "load") == 12.5          # load ranks by cpu
    assert mr.metric_value(r, "memory") == 2048
    assert mr.metric_value(r, "swap") == 64
    assert mr.metric_value(r, "disk") == 150.0         # read + write throughput
    assert mr.metric_value(r, "network") is None       # no per-process bandwidth


def test_metric_value_disk_partial_and_absent():
    assert mr.metric_value(rec(1, rd=None, wr=30.0), "disk") == 30.0
    assert mr.metric_value(rec(1, rd=None, wr=None), "disk") is None


def test_network_not_drillable():
    assert mr.is_drillable("cpu") is True
    assert mr.is_drillable("load") is True
    assert mr.is_drillable("network") is False


# --- rank_processes ---------------------------------------------------------

def test_rank_processes_top_n_and_excludes_unknown():
    rows = mr.rank_processes(procs(
        rec(1, cpu=5.0), rec(2, cpu=None), rec(3, cpu=50.0), rec(4, cpu=20.0)),
        "cpu", limit=2)
    assert [r["pid"] for r in rows] == [3, 4]     # top-2 by cpu, None dropped
    assert rows[0]["value"] == 50.0
    assert all(r["count"] == 1 for r in rows)


def test_rank_processes_tie_breaks_on_lower_pid():
    rows = mr.rank_processes(procs(rec(5, cpu=10.0), rec(3, cpu=10.0)), "cpu")
    assert [r["pid"] for r in rows] == [3, 5]      # equal value -> lower pid first


def test_rank_processes_empty():
    assert mr.rank_processes({}, "cpu") == []
    assert mr.rank_processes(procs(rec(1, cpu=None)), "cpu") == []


# --- ancestry roll-up (firefox tree collapse) -------------------------------

def test_rank_by_ancestry_collapses_subtree():
    p = procs(
        rec(1000, name="firefox", ppid=1, cpu=5.0),
        rec(1001, name="Web Content", ppid=1000, cpu=10.0),
        rec(1002, name="RDD", ppid=1001, cpu=3.0),
        rec(2000, name="bash", ppid=1, cpu=2.0),
    )
    rows = mr.rank_by_ancestry(p, "cpu")
    top = rows[0]
    assert top["pid"] == 1000 and top["name"] == "firefox"
    assert top["value"] == 18.0 and top["count"] == 3   # 5 + 10 + 3
    bash = [r for r in rows if r["pid"] == 2000][0]
    assert bash["value"] == 2.0 and bash["count"] == 1


def test_rank_by_ancestry_stops_at_init_not_grouping_under_pid1():
    # Two independent apps directly under init must stay two rows, not one.
    p = procs(rec(10, ppid=1, cpu=4.0), rec(20, ppid=1, cpu=6.0))
    rows = mr.rank_by_ancestry(p, "cpu")
    assert sorted(r["pid"] for r in rows) == [10, 20]


def test_rank_by_ancestry_survives_a_cycle():
    # Recycled-pid loop (a <-> b): the seen-set guard must terminate the walk.
    p = procs(rec(10, ppid=20, cpu=1.0), rec(20, ppid=10, cpu=1.0))
    rows = mr.rank_by_ancestry(p, "cpu")
    assert sum(r["count"] for r in rows) == 2


# --- unit roll-up -----------------------------------------------------------

def test_rank_by_unit_groups_and_excludes_unitless():
    p = procs(
        rec(1, rss=100, unit="app.service"),
        rec(2, rss=200, unit="app.service"),
        rec(3, rss=999, unit=None),          # no unit -> excluded
        rec(4, rss=50, unit="other.scope"),
    )
    rows = mr.rank_by_unit(p, "memory")
    top = rows[0]
    assert top["unit"] == "app.service" and top["value"] == 300 and top["count"] == 2
    assert all(r["unit"] is not None for r in rows)
    assert 999 not in [r["value"] for r in rows]


def test_rank_dispatch_modes():
    p = procs(rec(1, cpu=1.0, unit="u.service"))
    assert mr.rank(p, "cpu", "by_process")[0]["pid"] == 1
    assert mr.rank(p, "cpu", "by_tree")[0]["pid"] == 1
    assert mr.rank(p, "cpu", "by_unit")[0]["unit"] == "u.service"


# --- capacity zone + fraction ----------------------------------------------

def test_capacity_zone_thresholds():
    assert mr.capacity_zone(None) is None
    assert mr.capacity_zone(0) == mr.ZONE_NOMINAL
    assert mr.capacity_zone(59.9) == mr.ZONE_NOMINAL
    assert mr.capacity_zone(60) == mr.ZONE_MEDIUM
    assert mr.capacity_zone(84.9) == mr.ZONE_MEDIUM
    assert mr.capacity_zone(85) == mr.ZONE_NEAR
    assert mr.capacity_zone(100) == mr.ZONE_NEAR


def test_fraction_clamps():
    assert mr.fraction(50, 100) == 0.5
    assert mr.fraction(150, 100) == 1.0
    assert mr.fraction(-5, 100) == 0.0
    assert mr.fraction(None, 100) is None
    assert mr.fraction(5, 0) is None


# --- network auto-scale ceiling --------------------------------------------

def test_network_ceiling_floor_and_double():
    assert mr.network_ceiling(None) == float(mr.BYTES_PER_MB)      # idle -> floor
    assert mr.network_ceiling(0) == float(mr.BYTES_PER_MB)
    assert mr.network_ceiling(10 * mr.BYTES_PER_MB) == 20 * mr.BYTES_PER_MB
    # 2x a sub-floor max still clamps up to the 1 MB/s floor.
    assert mr.network_ceiling(0.3 * mr.BYTES_PER_MB) == float(mr.BYTES_PER_MB)


# --- gauge readings (incl. degraded / empty) --------------------------------

def test_cpu_reading():
    assert mr.cpu_reading({"cpu": {"pct": 12.0}})["pct"] == 12.0
    assert mr.cpu_reading({})["pct"] is None


def test_mem_reading_used_total_and_derived():
    r = mr.mem_reading({"mem": {"total": 1000, "used": 600}})
    assert (r["used"], r["total"], r["pct"]) == (600, 1000, 60.0)
    # used derived from available when absent.
    r2 = mr.mem_reading({"mem": {"total": 1000, "available": 400}})
    assert r2["used"] == 600 and r2["pct"] == 60.0
    assert mr.mem_reading({})["pct"] is None            # honest None, not 0


def test_swap_reading_and_zero_total():
    r = mr.swap_reading({"mem": {"swap_total": 1000, "swap_free": 250}})
    assert (r["used"], r["pct"]) == (750, 75.0)
    # No swap configured -> percent is None, never a divide-by-zero.
    assert mr.swap_reading({"mem": {"swap_total": 0, "swap_free": 0}})["pct"] is None


def test_disk_reading_busiest():
    r = mr.disk_reading({"disks": {
        "sda": {"util": 5.0}, "nvme0n1": {"util": 40.0}, "dm-0": {"util": None}}})
    assert r["pct"] == 40.0 and r["busiest"] == "nvme0n1"
    assert mr.disk_reading({"disks": {}})["pct"] is None


def test_net_reading_sum_and_absent():
    r = mr.net_reading({"net": {
        "eth0": {"rx_rate": 1000.0, "tx_rate": 2000.0},
        "wlan0": {"rx_rate": None, "tx_rate": None}}})
    assert (r["rx"], r["tx"], r["total"]) == (1000.0, 2000.0, 3000.0)
    empty = mr.net_reading({"net": {"eth0": {"rx_rate": None, "tx_rate": None}}})
    assert empty["total"] is None                       # honest empty, not 0


def test_load_reading_is_unknown_until_reader_lands():
    r = mr.load_reading({"cpu": {"ncpu": 8}})
    assert r["value"] is None and r["ncpu"] == 8        # probe-first "—"
