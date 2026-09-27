#!/usr/bin/env python3
"""Performance baseline & threshold derivation (r071).

First-run capture measures the machine (specs + idle CPU noise floor);
``derive`` turns those into per-metric alert thresholds. Pure logic lives
in ``derive``/``Thresholds`` (fixture-tested); ``capture`` performs the one
short sampling loop. Formulae are documented in
docs/modules/perf-thresholds.md — change the doc and the code together.

This module is UI-import-free and GLib-free (core-modules rule).
"""

import os
import time

try:  # app layout (python3 src/main.py)
    from modules import procfs
except ImportError:  # standalone/test layout
    import procfs


SCHEMA = 1


def clamp(value, low, high):
    return max(low, min(high, value))


def _p90(samples):
    ordered = sorted(samples)
    if not ordered:
        return 0.0
    idx = min(len(ordered) - 1, int(round(0.9 * (len(ordered) - 1))))
    return ordered[idx]


def derive(specs, idle_samples):
    """Pure threshold derivation.

    specs: dict with keys cpu_cores (int), ram_gb (float),
           has_swap (bool), ssd (bool), idle_p90 (float, percent).
    idle_samples: list of total-CPU% samples taken at idle.
    Returns a plain dict of thresholds, JSON-safe.
    """
    idle_p90 = _p90(idle_samples) if idle_samples else 2.0

    cpu_yellow = clamp(idle_p90 + 12, 20, 45)
    cpu_red = clamp(idle_p90 * 4 + 20, 55, 85)

    ram_gb = float(specs.get("ram_gb") or 8.0)
    if ram_gb <= 4:
        mem_yellow, mem_red = 50, 80
    elif ram_gb >= 32:
        mem_yellow, mem_red = 75, 90
    else:
        bump = clamp(ram_gb - 8, 0, 24)  # +1%/GB between 8 and 32 GB
        mem_yellow = clamp(55 + bump, 55, 75)
        mem_red = min(95, mem_yellow + 25)

    swap_red = 10 if ram_gb < 16 else 20
    swap_yellow = max(5, swap_red // 2)

    disk_red = 60 if specs.get("ssd", True) else 85
    disk_yellow = disk_red * 0.7

    ncpu = int(specs.get("cpu_cores") or 1)
    load_red = round(ncpu * 1.5, 2)

    return {
        "schema": SCHEMA,
        "cpu_yellow": round(cpu_yellow, 1),
        "cpu_red": round(cpu_red, 1),
        "mem_yellow": round(mem_yellow, 1),
        "mem_red": round(mem_red, 1),
        "swap_yellow": swap_yellow,
        "swap_red": swap_red,
        "disk_yellow": round(disk_yellow, 1),
        "disk_red": disk_red,
        "net_alert_pct": 80.0,           # % of auto-scale ceiling
        "load_red": load_red,
        "idle_p90": round(idle_p90, 1),
    }


def capture(idle_seconds=6.0, sample_step=0.5, sleep_func=time.sleep,
            monotonic_func=time.monotonic):
    """Measure the machine and derive thresholds.

    The idle sampling loop is deliberately simple (wall-clock % from
    /proc/stat totals); it runs before the sampler thread starts, so there
    is no contention. Returns (specs, thresholds).
    """
    ncpu = 0
    total_jiffies = []
    prev = None
    deadline = monotonic_func() + idle_seconds
    while monotonic_func() < deadline:
        stat = procfs.system_stat()
        ncpu = stat.get("ncpu", ncpu) or 1
        totals = stat.get("total") or {}
        busy = totals.get("busy")
        idle_j = totals.get("idle")
        if busy is not None and idle_j is not None:
            if prev is not None:
                dtotal = (busy + idle_j) - (prev[0] + prev[1])
                dbusy = busy - prev[0]
                if dtotal > 0:
                    total_jiffies.append(100.0 * dbusy / dtotal)
            prev = (busy, idle_j)
        sleep_func(sample_step)

    mem = procfs.system_meminfo()
    ram_gb = round((mem.get("total") or 0) / (1024 ** 3), 2)
    has_swap = (mem.get("swap_total") or 0) > 0

    ssd = True
    try:
        for entry in os.listdir("/sys/block"):
            try:
                with open(f"/sys/block/{entry}/queue/rotational") as f:
                    if f.read().strip() == "1":
                        ssd = False
                        break
            except OSError:
                continue  # queue/rotational absent on some devices
    except OSError:
        pass

    specs = {
        "cpu_cores": ncpu,
        "ram_gb": ram_gb,
        "has_swap": has_swap,
        "ssd": ssd,
        "kernel": os.uname().release,
    }
    thresholds = derive(specs, total_jiffies)
    return specs, thresholds


class Thresholds:
    """Provider consulted by UI zone helpers. Falls back to fixed defaults
    when no baseline exists (first seconds of first run)."""

    DEFAULTS = {
        "cpu_yellow": 60.0, "cpu_red": 85.0,
        "mem_yellow": 60.0, "mem_red": 85.0,
        "swap_yellow": 5.0, "swap_red": 20.0,
        "disk_yellow": 42.0, "disk_red": 60.0,
        "net_alert_pct": 80.0,
        "load_red": None,   # None -> ncpu * 1.5 at use time
    }

    def __init__(self, values=None):
        merged = dict(self.DEFAULTS)
        if values:
            for key, val in values.items():
                if key in merged or key in ("schema", "idle_p90"):
                    merged[key] = val
        self._values = merged

    def get(self, metric, level):
        """level: 'yellow' | 'red'. Returns float or None (unknown)."""
        return self._values.get(f"{metric}_{level}")

    def zone(self, metric, pct):
        """'nominal' | 'amber' | 'critical' — shared by every zone helper."""
        yellow = self.get(metric, "yellow")
        red = self.get(metric, "red")
        if pct is None:
            return None
        if red is not None and pct >= red:
            return "critical"
        if yellow is not None and pct >= yellow:
            return "amber"
        return "nominal"

    def to_dict(self):
        return dict(self._values)
