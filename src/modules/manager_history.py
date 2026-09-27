"""Shared system-history ring store (Phase 5).

Spec: docs/modules/resource-graphs.md (ring law) + docs/modules/graphs-hub.md
(the hub/detail surfaces that consume these rings) + metric-band-basics.md §3
(Basics sparklines consume the same rings).

This is the single ``manager_history`` ring store shared by the Basics
sparklines, the Graphs hub mini-charts, and the per-metric detail pages. It is
**UI-import-free** and stateless-per-call so the ring math is exercised entirely
against fixtures without a display.

Ring law (r059 sign-off, LOCK-FREE):

- Every point is a ``(ts, value)`` tuple — never a bare positional value — so a
  hidden window renders as a gap, not a compressed run of activity.
- ``from_backoff`` samples are **excluded at insert time** (a backoff window is
  a gap in the record, not a data point).
- ``value`` may be ``None`` (no-data at that instant); renderers break the line
  at ``None`` and at large timestamp gaps. Absence is never a fabricated 0.
- **Main-thread writes only.** The Processes page owns the single GLib drain
  source (r046); it forwards each snapshot on that thread and the writer here
  runs there too. No lock is needed because there is exactly one writer thread
  and readers run on the same (main) thread at draw time.

History is not persisted across restarts.
"""

from collections import deque

try:  # app layout: python3 src/main.py (src on sys.path)
    from modules import manager_rank as mr
except ImportError:  # standalone/test layout (src/modules on sys.path)
    import manager_rank as mr

# ~5 min of history at the 0.5 s cadence floor is 600 points; the age trim keeps
# the window honest regardless of the chosen interval (docs: 300/period samples).
DEFAULT_MAXLEN = 600
RETENTION_S = 300.0

# The series the store carries, in hub order. Seven feed the seven hub charts;
# the pressure chart draws the three PSI ``some avg10`` series as a triple.
SERIES = (
    "cpu", "memory", "swap", "disk", "network", "load",
    "psi_cpu", "psi_mem", "psi_io",
)


class History:
    """A bounded, age-trimmed ``(ts, value)`` ring per series.

    Not thread-safe by design (main-thread-writes-only, see the module note); a
    lock would only add cost the single-writer contract already makes needless.
    """

    def __init__(self, maxlen=DEFAULT_MAXLEN, retention_s=RETENTION_S):
        self._maxlen = maxlen
        self._retention_s = retention_s
        self._rings = {}  # series -> deque[(ts, value)]

    def insert(self, series, ts, value, from_backoff=False):
        """Append ``(ts, value)`` to ``series`` unless it is a backoff sample.

        Backoff exclusion happens HERE (ring law): the caller may hand every
        snapshot through and the gap is enforced at insert. Points older than
        the retention window are evicted so the ring stays ~5 min deep.
        """
        if from_backoff:
            return
        ring = self._rings.get(series)
        if ring is None:
            ring = self._rings[series] = deque(maxlen=self._maxlen)
        ring.append((ts, value))
        cutoff = ts - self._retention_s
        while ring and ring[0][0] < cutoff:
            ring.popleft()

    def slice(self, series, window_s):
        """Points within the last ``window_s`` seconds of the newest sample.

        Anchored on the newest point (not wall time) so a paused/quiet store
        still returns its tail rather than an empty window.
        """
        ring = self._rings.get(series)
        if not ring:
            return []
        newest = ring[-1][0]
        cutoff = newest - window_s
        return [(ts, value) for ts, value in ring if ts >= cutoff]

    def last(self, series):
        """The newest ``(ts, value)`` for ``series``, or ``None`` if empty."""
        ring = self._rings.get(series)
        if not ring:
            return None
        return ring[-1]

    def clear(self):
        self._rings.clear()


# ---------------------------------------------------------------------------
# Snapshot -> series values (the single definition of what each series holds).
# ---------------------------------------------------------------------------

def _load1(system):
    return ((system or {}).get("load") or {}).get("load1")


def _psi_avg10(system, resource):
    resource_psi = ((system or {}).get("psi") or {}).get(resource) or {}
    return (resource_psi.get("some") or {}).get("avg10")


def series_values(system):
    """Map one snapshot's ``system`` section to ``{series: scalar}``.

    Percent gauges (cpu/memory/swap/disk) reuse the shared gauge readings in
    :mod:`manager_rank`; network is the summed byte-rate; load is 1-min
    loadavg; the PSI series are each resource's ``some avg10``. Absent data is
    ``None`` — inserted as a gap, never a 0.
    """
    system = system or {}
    return {
        "cpu": mr.cpu_reading(system)["pct"],
        "memory": mr.mem_reading(system)["pct"],
        "swap": mr.swap_reading(system)["pct"],
        "disk": mr.disk_reading(system)["pct"],
        "network": mr.net_reading(system)["total"],
        "load": _load1(system),
        "psi_cpu": _psi_avg10(system, "cpu"),
        "psi_mem": _psi_avg10(system, "memory"),
        "psi_io": _psi_avg10(system, "io"),
    }


def record(history, snapshot):
    """Insert one snapshot's series into ``history`` (main-thread writer).

    Backoff exclusion is delegated to :meth:`History.insert`; this simply hands
    every series through with the snapshot's ``from_backoff`` tag.
    """
    values = series_values(snapshot.system)
    for series, value in values.items():
        history.insert(series, snapshot.ts, value,
                       from_backoff=snapshot.from_backoff)


# ---------------------------------------------------------------------------
# Window statistics (current / min / avg / max over a slice) — pure + shared.
# ---------------------------------------------------------------------------

def window_stats(points):
    """``{current, min, avg, max}`` over ``points`` (a ``(ts, value)`` slice).

    ``None`` values are ignored (gaps do not count toward the stats). Every
    field is ``None`` when the slice holds no real values — the detail strip
    then renders "—" rather than a fabricated 0.
    """
    values = [value for _ts, value in points if value is not None]
    if not values:
        return {"current": None, "min": None, "avg": None, "max": None}
    return {
        "current": values[-1],
        "min": min(values),
        "avg": sum(values) / len(values),
        "max": max(values),
    }
