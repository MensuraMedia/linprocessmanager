"""Threaded, GLib-free sampler for linprocman (Phase 2b).

Owns *timing*. A background thread turns ``/proc`` (and later ``/sys``) reads
into immutable :class:`Snapshot` objects on a fixed cadence, buffers them in a
bounded drop-oldest queue, and hands the newest to the UI on demand via
:meth:`Sampler.drain_latest`. This module is the only stateful shell between the
kernel-reading readers and the UI world.

Spec: docs/modules/sampling-pipeline.md (binding) + the task-003 contract. The
rules below are lifted verbatim from those documents.

Hard boundaries (all grep-gated):

- **GLib-free.** No ``gi``/``GLib``/``GTK`` anywhere in this file. The single
  GLib idle source that drains the queue on the main thread is installed by the
  table layer (task 004), never here.
- **Pure step function.** :func:`build_snapshot` does the rate math with every
  input injected — the previous snapshot, the current wall time, a
  :class:`StepClock` context (constants + activity/rollup state), and a
  :class:`Readers` bundle. It reads no clock and no globals; the thread loop is
  the only stateful part. This is the mandated unit-test seam.
- **No-data is pure Python.** Absent/unreadable data is ``None`` (or a rate that
  simply comes back ``None``). The ``(-1, has_data=False)`` sentinel translation
  is task 004's model-layer job, not this module's.
- **Identity is ``(pid, starttime)`` everywhere** — a per-process rate delta is
  computed only when the previous sample carries the same identity. A recycled
  PID (matching pid, different starttime) re-arms exactly like a first sample.

Import policy: stdlib only, no network, no toolkit. ``procfs`` is imported for
the default reader bundle only; tests inject their own readers.
"""

import functools
import logging
import pwd
import queue
import threading
import time
from dataclasses import dataclass, field

import procfs

# Interval bounds (seconds) — docs/modules/sampling-pipeline.md cadence.
MIN_INTERVAL = 0.5
MAX_INTERVAL = 5.0
DEFAULT_INTERVAL = 2.0

# While the window is iconified/withdrawn AND the app is inactive, sample slowly
# to keep identities/deltas warm without burning cycles.
DEFAULT_BACKOFF_INTERVAL = 10.0

# Bounded queue: small, drop-oldest on full (no per-snapshot callback pileup).
QUEUE_SIZE = 4

# Consecutive tick failures tolerated before the watchdog stops the thread.
DEFAULT_MAX_FAILURES = 5

_LOG = logging.getLogger("linprocman.sampler")

# The exact per-process record field set, frozen by the task-003 acceptance gate
# (schema-freeze before task 004 is dispatched). Adding/renaming a field here is
# a defect. The schema test asserts every record's keys equal this set.
RECORD_FIELDS = frozenset({
    "pid", "starttime", "name", "user", "state", "ppid",
    "cpu_pct", "mem_rss", "mem_vsize", "mem_shared",
    "io_read_rate", "io_write_rate", "nice", "threads", "unit",
    "is_kthread", "is_defunct", "from_backoff", "rollup",
})


# ---------------------------------------------------------------------------
# Immutable value types.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Readers:
    """Injected reader bundle — the only I/O :func:`build_snapshot` performs.

    Production wiring binds these to :mod:`procfs` (see :func:`default_readers`);
    tests inject fakes so the step function is exercised against synthetic bytes,
    never the live kernel.
    """

    iter_pids: object
    parse_stat: object
    parse_status: object
    parse_io: object
    read_cmdline: object
    parse_cgroup: object
    parse_smaps_rollup: object
    system_stat: object
    system_meminfo: object
    system_net_dev: object
    system_diskstats: object
    system_pressure: object


@dataclass(frozen=True)
class StepClock:
    """Constants + per-tick context injected into the pure step function.

    Named ``clock`` in the mandated signature: it carries the tick constant
    (``clk_tck``) and everything the step needs that would otherwise be a global
    or a live clock read — the sampler period (for the Δwall guard), the backoff
    tag, the uid→name resolver, and the set of one-shot rollup targets.
    """

    clk_tck: int
    period: float
    from_backoff: bool
    uid_name: object            # callable: uid:int -> str
    rollup_targets: frozenset   # {(pid, starttime), ...}


@dataclass(frozen=True)
class _RawState:
    """Internal delta-carry — NOT part of the frozen Snapshot schema.

    Holds the raw counters the *next* step needs to compute deltas (previous
    jiffies, io/net/disk byte counters, and the sample's wall time). It rides on
    :attr:`Snapshot.raw` (``compare=False``/``repr=False``) so the public
    envelope stays exactly ``ts``/``from_backoff``/``procs``/``system`` and each
    record keeps exactly :data:`RECORD_FIELDS`.
    """

    ts: float
    procs: dict         # (pid, starttime) -> (utime, stime, read_bytes, write_bytes)
    cpu_total: object   # {"busy":int, "total":int} | None
    cpu_cores: dict     # index -> {"busy":int, "total":int}
    net: dict           # iface -> (rx_bytes, tx_bytes)
    disks: dict         # dev -> {"sectors_read","sectors_written","io_ticks"}


@dataclass(frozen=True)
class Snapshot:
    """One immutable sample. Public schema: ``ts``/``from_backoff``/``procs``/
    ``system``; :attr:`raw` is the private delta-carry (see :class:`_RawState`).

    ``ts`` is a monotonic timestamp so task 004 can detect staleness — the
    sampler never fakes liveness. ``procs`` maps ``(pid, starttime)`` to a plain
    record dict (:data:`RECORD_FIELDS`). ``system`` holds the machine-wide
    section (cpu/mem/net/disks/psi).
    """

    ts: float
    from_backoff: bool
    procs: dict
    system: dict
    raw: object = field(default=None, repr=False, compare=False)


# ---------------------------------------------------------------------------
# Pure rate math (no I/O, no globals, no clock reads).
# ---------------------------------------------------------------------------

def _cpu_pct(utime, stime, prev_utime, prev_stime, clk_tck, dwall):
    """cpu% = Δ(utime+stime) / (CLK_TCK × Δwall) × 100 (100% = one core).

    ``None`` on any missing counter or a negative delta (counter reset). Callers
    pass ``dwall=None`` to fold in the first-sample / Δwall-guard cases.
    """
    if dwall is None or dwall <= 0:
        return None
    if None in (utime, stime, prev_utime, prev_stime):
        return None
    delta = (utime + stime) - (prev_utime + prev_stime)
    if delta < 0:  # counter reset (should not happen for a live jiffy counter)
        return None
    return delta / (clk_tck * dwall) * 100.0


def _rate(cur, prev, dwall):
    """bytes/s over Δwall. ``None`` on missing counters, guard, or reset."""
    if dwall is None or dwall <= 0:
        return None
    if cur is None or prev is None:
        return None
    delta = cur - prev
    if delta < 0:  # counter reset (iface down/up, wrap) -> no-data, not garbage
        return None
    return delta / dwall


def _busy_pct(cur, prev):
    """Whole/per-core CPU busy% from two ``/proc/stat`` jiffy readings."""
    if not cur or not prev:
        return None
    d_busy = cur["busy"] - prev["busy"]
    d_total = cur["total"] - prev["total"]
    if d_total <= 0 or d_busy < 0:
        return None
    return d_busy / d_total * 100.0


def _util_pct(cur_ticks, prev_ticks, dwall):
    """Disk utilisation% from io_ticks (ms spent doing I/O) over Δwall."""
    if dwall is None or dwall <= 0:
        return None
    if cur_ticks is None or prev_ticks is None:
        return None
    delta = cur_ticks - prev_ticks
    if delta < 0:
        return None
    return delta / (dwall * 1000.0) * 100.0


def _read_opt(reader, pid):
    """Call a per-PID reader tolerating a mid-read exit.

    The readers already fold ``PermissionError`` into ``None``/locked dicts; the
    one thing that can still escape is ``FileNotFoundError`` when the process
    exits between enumeration and this read — treated as absent data, never a
    crash.
    """
    try:
        return reader(pid)
    except (FileNotFoundError, PermissionError):
        return None


def _read_system(reader):
    """Call a no-arg system reader, degrading a missing/locked file to ``None``."""
    try:
        return reader()
    except (FileNotFoundError, PermissionError):
        return None


# ---------------------------------------------------------------------------
# Pure step function — the mandated testability seam.
# ---------------------------------------------------------------------------

def build_snapshot(prev, now, clock, readers):
    """Turn one round of reads into an immutable :class:`Snapshot` (pure).

    Parameters
    ----------
    prev : Snapshot | None
        The previous snapshot (``None`` on the first sample or after a re-arm).
        Deltas are computed against ``prev.raw``.
    now : float
        Monotonic timestamp for this sample — injected, never read inside.
    clock : StepClock
        Tick constant, period, backoff tag, uid→name resolver, rollup targets.
    readers : Readers
        The injected I/O bundle (the only I/O this function performs).

    Rate fields emit ``None`` on: first sample, Δwall shorter than one period,
    ``(pid, starttime)`` mismatch (recycling), and negative counter deltas.
    """
    prev_raw = prev.raw if prev is not None else None

    # Δwall guard: skip all rate fields if elapsed < one period (clock weirdness,
    # double tick) or non-positive; a first sample has no prev at all.
    dwall = None
    if prev_raw is not None:
        candidate = now - prev_raw.ts
        if candidate >= clock.period:
            dwall = candidate

    procs, procs_raw = _build_procs(prev_raw, dwall, clock, readers)
    system, sys_raw = _build_system(prev_raw, dwall, readers)

    raw = _RawState(
        ts=now,
        procs=procs_raw,
        cpu_total=sys_raw["cpu_total"],
        cpu_cores=sys_raw["cpu_cores"],
        net=sys_raw["net"],
        disks=sys_raw["disks"],
    )
    return Snapshot(
        ts=now,
        from_backoff=clock.from_backoff,
        procs=procs,
        system=system,
        raw=raw,
    )


def _build_procs(prev_raw, dwall, clock, readers):
    """Build the per-process records + the raw delta-carry for next time."""
    procs = {}
    raw = {}
    for pid in readers.iter_pids():
        built = _one_proc(pid, prev_raw, dwall, clock, readers)
        if built is None:
            continue
        key, record, counters = built
        procs[key] = record
        raw[key] = counters
    return procs, raw


def _one_proc(pid, prev_raw, dwall, clock, readers):
    """One process record, or ``None`` to skip (exit / truncated line)."""
    try:
        stat = readers.parse_stat(pid)
    except FileNotFoundError:
        return None  # exited between enumeration and read
    if stat is None:
        return None  # truncated/short stat line -> skip this PID this sample

    starttime = stat.get("starttime")
    state = stat.get("state")
    name = stat.get("comm")
    ppid = stat.get("ppid")
    utime = stat.get("utime")
    stime = stat.get("stime")

    status = _read_opt(readers.parse_status, pid)
    io = _read_opt(readers.parse_io, pid)
    cmdline = _read_opt(readers.read_cmdline, pid)
    cgroup = _read_opt(readers.parse_cgroup, pid)

    # Fall back to status when stat was locked (PermissionError) or absent.
    if status:
        if name is None:
            name = status.get("name")
        if state is None:
            state = status.get("state")
        if ppid is None:
            ppid = status.get("ppid")

    uid = status.get("uid") if status else None
    user = clock.uid_name(uid) if uid is not None else None

    mem_rss = status.get("vm_rss_bytes") if status else None
    mem_vsize = status.get("vm_size_bytes") if status else None
    mem_shared = status.get("shared_bytes") if status else None

    cur_read = io.get("read_bytes") if io else None
    cur_write = io.get("write_bytes") if io else None

    # Rates: only when identity matches the previous sample (recycle guard) and
    # the Δwall guard passed.
    key = (pid, starttime)
    cpu_pct = io_read_rate = io_write_rate = None
    prev_proc = prev_raw.procs.get(key) if prev_raw is not None else None
    if dwall is not None and prev_proc is not None:
        p_utime, p_stime, p_read, p_write = prev_proc
        cpu_pct = _cpu_pct(utime, stime, p_utime, p_stime, clock.clk_tck, dwall)
        io_read_rate = _rate(cur_read, p_read, dwall)
        io_write_rate = _rate(cur_write, p_write, dwall)

    # Kernel-thread detector: empty cmdline AND state != Z. Unknown cmdline
    # (PermissionError -> None) is not a kernel thread.
    if cmdline is None:
        is_kthread = False
    else:
        is_kthread = (not cmdline) and state != "Z"
    is_defunct = state == "Z"

    rollup = None
    if key in clock.rollup_targets:
        rollup = _read_opt(readers.parse_smaps_rollup, pid)

    record = {
        "pid": pid,
        "starttime": starttime,
        "name": name,
        "user": user,
        "state": state,
        "ppid": ppid,
        "cpu_pct": cpu_pct,
        "mem_rss": mem_rss,
        "mem_vsize": mem_vsize,
        "mem_shared": mem_shared,
        "io_read_rate": io_read_rate,
        "io_write_rate": io_write_rate,
        "nice": stat.get("nice"),
        "threads": stat.get("num_threads"),
        "unit": cgroup,  # str (unit / "—") or None (unreadable)
        "is_kthread": is_kthread,
        "is_defunct": is_defunct,
        "from_backoff": clock.from_backoff,
        "rollup": rollup,
    }
    counters = (utime, stime, cur_read, cur_write)
    return key, record, counters


def _build_system(prev_raw, dwall, readers):
    """Build the machine-wide section + its raw delta-carry."""
    stat = _read_system(readers.system_stat)
    mem = _read_system(readers.system_meminfo)
    net = _read_system(readers.system_net_dev)
    disks = _read_system(readers.system_diskstats)
    psi = _read_system(readers.system_pressure)

    cpu_total_raw = stat.get("total") if stat else None
    cpu_cores_raw = (stat.get("cpus") if stat else None) or {}
    ncpu = stat.get("ncpu") if stat else 0

    cpu_pct = None
    if dwall is not None and prev_raw is not None:
        cpu_pct = _busy_pct(cpu_total_raw, prev_raw.cpu_total)

    per_core = {}
    for index, core in cpu_cores_raw.items():
        pct = None
        if dwall is not None and prev_raw is not None:
            pct = _busy_pct(core, prev_raw.cpu_cores.get(index))
        per_core[index] = pct

    net_out = {}
    net_raw = {}
    for iface, vals in (net or {}).items():
        rx = vals.get("rx_bytes")
        tx = vals.get("tx_bytes")
        net_raw[iface] = (rx, tx)
        rx_rate = tx_rate = None
        if dwall is not None and prev_raw is not None:
            prev_iface = prev_raw.net.get(iface)
            if prev_iface is not None:
                rx_rate = _rate(rx, prev_iface[0], dwall)
                tx_rate = _rate(tx, prev_iface[1], dwall)
        net_out[iface] = {"rx_rate": rx_rate, "tx_rate": tx_rate}

    disks_out = {}
    disks_raw = {}
    for dev, vals in (disks or {}).items():
        sr = vals.get("sectors_read")
        sw = vals.get("sectors_written")
        ticks = vals.get("io_ticks")
        disks_raw[dev] = {
            "sectors_read": sr, "sectors_written": sw, "io_ticks": ticks,
        }
        read_rate = write_rate = util = None
        if dwall is not None and prev_raw is not None:
            prev_dev = prev_raw.disks.get(dev)
            if prev_dev is not None:
                sr_rate = _rate(sr, prev_dev.get("sectors_read"), dwall)
                sw_rate = _rate(sw, prev_dev.get("sectors_written"), dwall)
                read_rate = sr_rate * 512 if sr_rate is not None else None
                write_rate = sw_rate * 512 if sw_rate is not None else None
                util = _util_pct(ticks, prev_dev.get("io_ticks"), dwall)
        disks_out[dev] = {
            "read_rate": read_rate, "write_rate": write_rate, "util": util,
        }

    system = {
        "cpu": {"pct": cpu_pct, "per_core": per_core, "ncpu": ncpu},
        "mem": mem,
        "net": net_out,
        "disks": disks_out,
        "psi": psi,
    }
    sys_raw = {
        "cpu_total": cpu_total_raw,
        "cpu_cores": cpu_cores_raw,
        "net": net_raw,
        "disks": disks_raw,
    }
    return system, sys_raw


# ---------------------------------------------------------------------------
# Reader wiring.
# ---------------------------------------------------------------------------

def default_readers(proc_root=procfs.PROC):
    """Bind the :mod:`procfs` readers to a ``proc_root`` as a :class:`Readers`."""
    bind = functools.partial
    return Readers(
        iter_pids=bind(procfs.iter_pids, proc_root=proc_root),
        parse_stat=bind(procfs.parse_stat, proc_root=proc_root),
        parse_status=bind(procfs.parse_status, proc_root=proc_root),
        parse_io=bind(procfs.parse_io, proc_root=proc_root),
        read_cmdline=bind(procfs.read_cmdline, proc_root=proc_root),
        parse_cgroup=bind(procfs.parse_cgroup, proc_root=proc_root),
        parse_smaps_rollup=bind(procfs.parse_smaps_rollup, proc_root=proc_root),
        system_stat=bind(procfs.system_stat, proc_root=proc_root),
        system_meminfo=bind(procfs.system_meminfo, proc_root=proc_root),
        system_net_dev=bind(procfs.system_net_dev, proc_root=proc_root),
        system_diskstats=bind(procfs.system_diskstats, proc_root=proc_root),
        system_pressure=bind(procfs.system_pressure, proc_root=proc_root),
    )


# ---------------------------------------------------------------------------
# The stateful thread shell (owns timing + the queue; touches no GTK).
# ---------------------------------------------------------------------------

class Sampler:
    """Background thread: reads → :func:`build_snapshot` → bounded queue.

    Public API (all thread-safe): :meth:`start`, :meth:`stop`,
    :meth:`set_interval`, :meth:`set_activity_state`, :meth:`request_rollup`,
    :meth:`drain_latest`. The UI injects window state via
    :meth:`set_activity_state`; this module never reads GTK.
    """

    def __init__(self, proc_root=procfs.PROC, interval=DEFAULT_INTERVAL,
                 readers=None, clk_tck=None, queue_size=QUEUE_SIZE,
                 max_failures=DEFAULT_MAX_FAILURES,
                 backoff_interval=DEFAULT_BACKOFF_INTERVAL,
                 uid_name=None, monotonic=None, sleep=None, logger=None):
        self._readers = readers if readers is not None else default_readers(proc_root)
        self._clk_tck = clk_tck if clk_tck is not None else procfs.CLK_TCK
        self._max_failures = max_failures
        self._backoff_interval = backoff_interval
        self._log = logger if logger is not None else _LOG
        self._monotonic = monotonic if monotonic is not None else time.monotonic
        self._uid_name = uid_name if uid_name is not None else self._resolve_uid

        self._queue = queue.Queue(maxsize=queue_size)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._sleep = sleep  # None -> _stop_event.wait (interruptible)

        # State guarded by _lock.
        self._interval = self._clamp(interval)
        self._active = True
        self._iconified = False
        self._rollup_targets = set()
        self._rearm = False  # drop baselines for one sample (interval change)

        # Delta carry across ticks (thread-confined; only _run touches it).
        self._prev = None
        self._failures = 0

        # uid -> name cache, guarded by its own lock.
        self._uid_cache = {}
        self._uid_lock = threading.Lock()

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _clamp(seconds):
        return max(MIN_INTERVAL, min(MAX_INTERVAL, float(seconds)))

    def _resolve_uid(self, uid):
        """uid -> user name, cached. Unknown uid degrades to its number."""
        with self._uid_lock:
            if uid in self._uid_cache:
                return self._uid_cache[uid]
        try:
            name = pwd.getpwuid(uid).pw_name
        except (KeyError, OSError, OverflowError):
            name = str(uid)
        with self._uid_lock:
            self._uid_cache[uid] = name
        return name

    def _in_backoff_locked(self):
        # Backoff keys on iconified/withdrawn + inactive (r046 ruling). Wayland
        # cannot report occlusion, so an occluded-but-visible window still samples
        # at full cadence — a documented limitation.
        return self._iconified and not self._active

    # -- public API -------------------------------------------------------

    def set_interval(self, seconds):
        """Set the sampler period (clamped). Clears rate baselines for one
        sample so the next interval's deltas are honest."""
        seconds = self._clamp(seconds)
        with self._lock:
            if seconds != self._interval:
                self._interval = seconds
                self._rearm = True

    def set_activity_state(self, active, iconified):
        """UI-injected window state (the sampler never reads GTK)."""
        with self._lock:
            self._active = bool(active)
            self._iconified = bool(iconified)

    def request_rollup(self, pid, starttime):
        """Queue a one-shot ``smaps_rollup`` read for a process (thread-safe).

        The result rides the next snapshot's record under ``rollup``.
        """
        with self._lock:
            self._rollup_targets.add((pid, starttime))

    def drain_latest(self):
        """Return the newest queued snapshot (or ``None``) and empty the queue."""
        latest = None
        while True:
            try:
                latest = self._queue.get_nowait()
            except queue.Empty:
                break
        return latest

    def start(self):
        """Start the background thread (idempotent while running)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._failures = 0
        self._thread = threading.Thread(
            target=self._run, name="linprocman-sampler", daemon=True)
        self._thread.start()

    def stop(self, timeout=None):
        """Signal the thread to stop and join it."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        self._thread = None

    # -- thread internals -------------------------------------------------

    def _current_interval(self):
        with self._lock:
            return self._backoff_interval if self._in_backoff_locked() else self._interval

    def _wait(self, seconds):
        """Interruptible sleep; returns True if a stop was requested."""
        if self._sleep is not None:
            return bool(self._sleep(seconds))
        return self._stop_event.wait(seconds)

    def _tick(self):
        """Take one sample and enqueue it. Raises on reader failure (the
        watchdog in :meth:`_run` catches and counts)."""
        now = self._monotonic()
        with self._lock:
            from_backoff = self._in_backoff_locked()
            period = self._interval
            rollups = frozenset(self._rollup_targets)
            self._rollup_targets.clear()
            rearm = self._rearm
            self._rearm = False

        prev = None if rearm else self._prev
        clock = StepClock(
            clk_tck=self._clk_tck,
            period=period,
            from_backoff=from_backoff,
            uid_name=self._uid_name,
            rollup_targets=rollups,
        )
        snapshot = build_snapshot(prev, now, clock, self._readers)
        self._prev = snapshot
        self._enqueue(snapshot)

    def _enqueue(self, snapshot):
        """put_nowait + drop-oldest on full (bounded, no callback pileup)."""
        try:
            self._queue.put_nowait(snapshot)
        except queue.Full:
            try:
                self._queue.get_nowait()  # drop the oldest
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(snapshot)
            except queue.Full:  # pragma: no cover - single producer
                pass

    def _run(self):
        """Thread loop under a top-level watchdog: log and continue on failure,
        stop cleanly after N consecutive failures."""
        while not self._stop_event.is_set():
            start = self._monotonic()
            try:
                self._tick()
                self._failures = 0
            except Exception:  # noqa: BLE001 - watchdog must catch everything
                self._failures += 1
                self._log.exception(
                    "sampler tick failed (%d/%d)",
                    self._failures, self._max_failures)
                if self._failures >= self._max_failures:
                    self._log.error(
                        "sampler stopping after %d consecutive failures",
                        self._failures)
                    break
            interval = self._current_interval()
            elapsed = self._monotonic() - start
            if self._wait(max(0.0, interval - elapsed)):
                break
