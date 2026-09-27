"""Pure ranking / roll-up / gauge-reading model for the metric band + Basics
page (docs/modules/metric-band-basics.md).

This is the model layer behind the Processes-page metric band and the read-only
Basics page. It is **UI-import-free** (no ``gi``, no toolkit) and stateless —
every function is a pure transform of a snapshot's ``procs`` / ``system``
sections, so it is exercised entirely against fixtures without a display.

Two families live here:

- **Gauge readings** — turn ``snapshot.system`` into the numeric value + scale a
  gauge needs (percent, used/total bytes, busiest device, summed net rate). The
  band/Basics widgets do the cairo drawing; the numbers come from here.
- **Contributor rankings** — "who is responsible for this metric": top-N raw
  processes, the same rolled up by ancestry (a child folds into its nearest
  in-snapshot ancestor: firefox + Web Content + RDD = one firefox line), and the
  same rolled up by cgroup unit (systemd's own grouping).

Boundary law: the input is a snapshot section, never ``/proc``. No new sampling
happens here — this is the CURRENT snapshot, re-shaped.
"""

# 1 MiB, matching the 1024-based formatting the table/band use for byte rates.
BYTES_PER_MB = 1024 * 1024

# Metrics the band exposes, in band order (Variant 2 — Load replaces the plain
# Processes tile). ``network`` is present but has no per-process drill.
BAND_METRICS = ("cpu", "memory", "swap", "disk", "network", "load")

# Capacity threshold zones (r057, shared with the page's ``_cap_zone``):
#   <60 nominal · 60-84 medium · >=85 near-capacity.
ZONE_NOMINAL = "nominal"
ZONE_MEDIUM = "medium"
ZONE_NEAR = "near"


def capacity_zone(pct):
    """Zone name for a 0-100 percentage, or ``None`` when the value is unknown.

    Percent-of-scale for byte gauges (memory/swap) and net (fraction of the
    auto-scale ceiling) map through here too — the thresholds are the same.
    """
    if pct is None:
        return None
    if pct >= 85:
        return ZONE_NEAR
    if pct >= 60:
        return ZONE_MEDIUM
    return ZONE_NOMINAL


def fraction(value, ceiling):
    """Clamp ``value / ceiling`` to ``[0, 1]`` (a bar fill), or ``None``."""
    if value is None or not ceiling:
        return None
    return max(0.0, min(1.0, value / ceiling))


# ---------------------------------------------------------------------------
# Per-process contribution value (the "responsible" quantity per metric).
# ---------------------------------------------------------------------------

def metric_value(rec, metric):
    """The scalar a single process contributes to ``metric``, or ``None``.

    - cpu / load : ``cpu_pct`` (Load ranks by cpu — see the spec caption note).
    - memory     : ``mem_rss`` bytes.
    - swap       : ``mem_swap`` bytes.
    - disk       : read+write throughput bytes/s (NOT device util — the drill
                   caption states the two are orthogonal and must not be summed).
    - network    : ``None`` — /proc exposes no per-PID bandwidth (honest
                   permanent empty-state; socket attribution is backlog I9).
    """
    if metric in ("cpu", "load"):
        return rec.get("cpu_pct")
    if metric == "memory":
        return rec.get("mem_rss")
    if metric == "swap":
        return rec.get("mem_swap")
    if metric == "disk":
        r = rec.get("io_read_rate")
        w = rec.get("io_write_rate")
        if r is None and w is None:
            return None
        return (r or 0.0) + (w or 0.0)
    return None  # network + anything unknown: no per-process contribution


def is_drillable(metric):
    """True when a gauge has a per-process contributor ranking (all but net)."""
    return metric in BAND_METRICS and metric != "network"


def _unit_of(rec):
    """Display cgroup unit for a record, or ``None`` (the sampler's "—" and
    blank both mean "no unit" for grouping purposes)."""
    unit = rec.get("unit")
    if unit and unit != "—":
        return unit
    return None


def _finish(rows, limit, tiebreak):
    """Sort contribution rows by value desc with a deterministic tie-break, and
    trim to ``limit``."""
    rows.sort(key=lambda r: (-r["value"], tiebreak(r)))
    return rows[:limit]


# ---------------------------------------------------------------------------
# Rankings.
# ---------------------------------------------------------------------------

def rank_processes(procs, metric, limit=10):
    """Top-``limit`` raw processes by their contribution to ``metric``.

    Processes with no data for the metric are excluded (never shown as 0 —
    r039 taxonomy). Ties break on ascending pid so the order is stable.
    """
    rows = []
    for key, rec in (procs or {}).items():
        value = metric_value(rec, metric)
        if value is None:
            continue
        rows.append({
            "key": key,
            "pid": rec.get("pid"),
            "name": rec.get("name") or "?",
            "user": rec.get("user") or "?",
            "unit": _unit_of(rec),
            "value": float(value),
            "count": 1,
        })
    return _finish(rows, limit, lambda r: (r["pid"] if r["pid"] is not None else 0))


def _ancestry_root(pid, by_pid):
    """Nearest in-snapshot ancestor that heads an app subtree.

    Walk ``ppid`` upward while the parent is present in the snapshot, stopping at
    pid 1 (init) so the group root is the *app* (firefox), never systemd. A
    ``seen`` set guards against a recycled-pid cycle.
    """
    cur = pid
    seen = set()
    while cur in by_pid and cur not in seen:
        seen.add(cur)
        ppid = by_pid[cur][1].get("ppid")
        if ppid is None or ppid == cur or ppid == 1 or ppid == 0:
            break
        if ppid not in by_pid:
            break
        cur = ppid
    return cur


def rank_by_ancestry(procs, metric, limit=10):
    """Top-``limit`` contributors rolled up by ancestry (the first drill-down:
    raw → grouped-by-tree, answering "which *app* is responsible")."""
    procs = procs or {}
    by_pid = {}
    for key, rec in procs.items():
        pid = rec.get("pid")
        if pid is not None:
            by_pid[pid] = (key, rec)

    groups = {}
    for key, rec in procs.items():
        value = metric_value(rec, metric)
        if value is None:
            continue
        pid = rec.get("pid")
        root = _ancestry_root(pid, by_pid) if pid is not None else None
        root_key, root_rec = by_pid.get(root, (key, rec))
        group = groups.get(root)
        if group is None:
            group = groups[root] = {
                "key": root_key,
                "pid": root_rec.get("pid"),
                "name": root_rec.get("name") or "?",
                "user": root_rec.get("user") or "?",
                "unit": _unit_of(root_rec),
                "value": 0.0,
                "count": 0,
            }
        group["value"] += float(value)
        group["count"] += 1
    return _finish(list(groups.values()), limit,
                   lambda r: (r["pid"] if r["pid"] is not None else 0))


def rank_by_unit(procs, metric, limit=10):
    """Top-``limit`` contributors rolled up by cgroup unit (systemd's grouping).

    Processes with no unit are excluded — the unit view only speaks about
    unit-managed work.
    """
    groups = {}
    for key, rec in (procs or {}).items():
        value = metric_value(rec, metric)
        if value is None:
            continue
        unit = _unit_of(rec)
        if not unit:
            continue
        group = groups.get(unit)
        if group is None:
            group = groups[unit] = {
                "key": key,  # a representative process to jump to
                "pid": rec.get("pid"),
                "name": unit,
                "user": rec.get("user") or "?",
                "unit": unit,
                "value": 0.0,
                "count": 0,
            }
        group["value"] += float(value)
        group["count"] += 1
    return _finish(list(groups.values()), limit, lambda r: r["name"])


def rank(procs, metric, mode="by_process", limit=10):
    """Dispatch to the ranking for a drill ``mode`` (by_process/by_tree/by_unit)."""
    if mode == "by_tree":
        return rank_by_ancestry(procs, metric, limit)
    if mode == "by_unit":
        return rank_by_unit(procs, metric, limit)
    return rank_processes(procs, metric, limit)


# ---------------------------------------------------------------------------
# Gauge readings (system section -> numbers the band/Basics render).
# ---------------------------------------------------------------------------

def cpu_reading(system):
    """System CPU busy percent (0-100), or ``None``."""
    return {"pct": ((system or {}).get("cpu") or {}).get("pct")}


def mem_reading(system):
    """Memory: used/total bytes + percent used, honest ``None`` when absent."""
    mem = (system or {}).get("mem") or {}
    total = mem.get("total")
    used = mem.get("used")
    if used is None and total is not None and mem.get("available") is not None:
        used = total - mem["available"]
    pct = (100.0 * used / total) if (total and used is not None) else None
    return {"used": used, "total": total, "pct": pct}


def swap_reading(system):
    """Swap: used/total bytes + percent used (``used = total - free``)."""
    mem = (system or {}).get("mem") or {}
    total = mem.get("swap_total")
    free = mem.get("swap_free")
    used = (total - free) if (total is not None and free is not None) else None
    pct = (100.0 * used / total) if (total and used is not None) else None
    return {"used": used, "total": total, "pct": pct}


def disk_reading(system):
    """Busiest device utilisation percent + its name, or ``None`` when no disk
    reports util this sample."""
    disks = (system or {}).get("disks") or {}
    best = None
    busiest = None
    for dev, vals in disks.items():
        util = vals.get("util")
        if util is None:
            continue
        if best is None or util > best:
            best = util
            busiest = dev
    return {"pct": best, "busiest": busiest}


def net_reading(system):
    """Summed rx/tx byte-rates across interfaces (loopback already excluded at
    parse time), or ``None`` totals when no interface reports a rate."""
    net = (system or {}).get("net") or {}
    rx = 0.0
    tx = 0.0
    any_data = False
    for _iface, vals in net.items():
        r = vals.get("rx_rate")
        t = vals.get("tx_rate")
        if r is not None:
            rx += r
            any_data = True
        if t is not None:
            tx += t
            any_data = True
    if not any_data:
        return {"rx": None, "tx": None, "total": None}
    return {"rx": rx, "tx": tx, "total": rx + tx}


def load_reading(system):
    """Load: ``None`` — 1-min loadavg is not in the frozen schema yet.

    ``/proc/loadavg`` joins the reader table through the sign-off gate with the
    Phase-5 batch (out of scope here); until then the gauge renders "—"
    (probe-first rule), never a fabricated value.
    """
    return {"value": None, "ncpu": ((system or {}).get("cpu") or {}).get("ncpu")}


def network_ceiling(trailing_max, floor=BYTES_PER_MB):
    """Auto-scale ceiling for the Network bar: 2x the trailing max rate, with a
    1 MB/s floor so an idle link still shows a sane scale (Variant 2)."""
    if trailing_max is None or trailing_max <= 0:
        return float(floor)
    return max(float(floor), 2.0 * trailing_max)
