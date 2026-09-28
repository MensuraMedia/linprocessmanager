"""Per-process network attribution — r053 socket-owner model (honest).

Core, UI-free, stdlib only. The kernel exposes no per-socket byte counters
without eBPF/root (both rejected by the offline/no-root mandate), so this module
*attributes* each interface's rx/tx throughput across the sockets processes
hold, weighted by how much of the current sampling interval each socket was
open. This is a labelled estimate — "socket-owner attribution (proportional),
not kernel accounting" (docs/modules/process-preview.md §4 honesty rule) — never
presented as measured per-process bandwidth.

Design (process-preview.md §4):

- **Own processes (exact enough):** ``/proc/<pid>/fd/*`` -> socket inodes,
  matched against ``/proc/net/{tcp,tcp6,udp,udp6}`` inode tables. A process that
  holds the only open network socket for the interval receives the whole
  interface delta; when several sockets/processes are open the delta is split
  by open-duration share and then equally among a socket's holders.
- **Yama ptrace_scope=1 / other users:** the fd listing raises EACCES ->
  that pid is *restricted* and attributed ``None`` (a lock + "—" in the UI),
  never a fabricated 0.
- **Cadence / bounded work:** fd tables are rescanned only when their mtime
  changed (incremental cache); the rest is set math over inode maps. The
  Sampler wraps :meth:`poll` so any failure degrades to "no attribution" and
  never trips the watchdog.

Import policy: stdlib only, no toolkit, no network. ``procfs`` supplies the
default reader callables; tests inject fakes (there is no way to build symlink
``/proc/<pid>/fd`` fixtures without a live kernel, so the seam is dependency
injection — the same pattern the sampler uses).
"""

import functools

try:  # app layout: python3 src/main.py (src on sys.path)
    from modules import procfs
except ImportError:  # standalone/test layout (src/modules on sys.path)
    import procfs


def open_weight(now, first_seen, interval):
    """Fraction of the current interval a socket was open, clamped to [0, 1].

    A socket already open at the interval's start (``first_seen`` at least one
    ``interval`` ago) weighs a full 1.0; one that appeared partway through
    weighs proportionally less. With no usable interval (first sample / clock
    weirdness) every socket weighs 1.0 so the split is purely by holder count.
    """
    if interval is None or interval <= 0:
        return 1.0
    return min(1.0, max(0.0, (now - first_seen) / interval))


def attribute(inode_pids, active, weights, total_rx, total_tx,
              pid_start, restricted):
    """Pure attribution step -> ``{(pid, starttime): (rx, tx) | None}``.

    Parameters
    ----------
    inode_pids : dict[int, set[int]]
        socket inode -> the pids holding it (from the fd scan).
    active : set[int]
        network-socket inodes actually held by a scanned pid.
    weights : dict[int, float]
        per-active-socket open-duration weight (see :func:`open_weight`).
    total_rx, total_tx : float | None
        summed interface byte-rates this interval. ``None`` (first sample /
        counter reset) means the interval carries no usable total, so every
        scannable pid is left unknown (absent from the result -> record stays
        ``None``).
    pid_start : dict[int, int | None]
        pid -> starttime, the identity map for the pids to attribute.
    restricted : set[int]
        pids whose fd table was EACCES (Yama) -> attributed ``None``.
    """
    result = {}
    for pid in restricted:
        if pid in pid_start:
            result[(pid, pid_start[pid])] = None

    if total_rx is None and total_tx is None:
        return result  # no interval total -> leave every scannable pid unknown

    total_rx = total_rx or 0.0
    total_tx = total_tx or 0.0

    sum_w = sum(weights.values())
    if sum_w <= 0:
        # Every active socket is brand-new (0 duration) -> equal split so the
        # interval's traffic is not silently dropped.
        weights = {ino: 1.0 for ino in active}
        sum_w = float(len(active))

    pid_rx = {}
    pid_tx = {}
    if sum_w > 0:
        for ino in active:
            holders = [p for p in inode_pids.get(ino, ())
                       if p in pid_start and p not in restricted]
            if not holders:
                continue
            frac = weights.get(ino, 0.0) / sum_w
            rx = total_rx * frac / len(holders)
            tx = total_tx * frac / len(holders)
            for pid in holders:
                pid_rx[pid] = pid_rx.get(pid, 0.0) + rx
                pid_tx[pid] = pid_tx.get(pid, 0.0) + tx

    for pid, starttime in pid_start.items():
        if pid in restricted:
            continue
        result[(pid, starttime)] = (pid_rx.get(pid, 0.0), pid_tx.get(pid, 0.0))
    return result


class NetAttributor:
    """Stateful per-pass attributor (owns the fd-scan cache + socket open times).

    Reader callables are injected so tests drive fake ``/proc`` trees; production
    binds them to :mod:`procfs` for ``proc_root``.
    """

    def __init__(self, proc_root="/proc", *, scan_fds=None, fd_mtime=None,
                 read_net=None):
        bind = functools.partial
        self._scan_fds = scan_fds if scan_fds is not None else bind(
            procfs.read_socket_inodes, proc_root=proc_root)
        self._fd_mtime = fd_mtime if fd_mtime is not None else bind(
            procfs.fd_table_mtime, proc_root=proc_root)
        self._read_net = read_net if read_net is not None else bind(
            procfs.read_net_sockets, proc_root=proc_root)
        self._first_seen = {}   # active socket inode -> first monotonic ts
        self._fd_cache = {}     # pid -> (mtime | None, frozenset inodes)
        self._families = {}     # active socket inode -> family (for the pane)

    # -- public -----------------------------------------------------------

    def poll(self, now, interval, total_rx, total_tx, pid_start):
        """One attribution pass. Returns ``{(pid, starttime): (rx, tx) | None}``.

        ``pid_start`` (pid -> starttime) both selects the pids to attribute and
        supplies their identity keys. Restricted (Yama) pids map to ``None``.
        """
        inode_pids, restricted = self._scan(pid_start)
        net = self._read_net() or {}

        active = {ino for ino in inode_pids if ino in net}
        for ino in active:
            self._first_seen.setdefault(ino, now)
        for ino in list(self._first_seen):
            if ino not in active:
                del self._first_seen[ino]
        for pid in list(self._fd_cache):
            if pid not in pid_start:
                del self._fd_cache[pid]

        self._families = {ino: net[ino] for ino in active}
        weights = {ino: open_weight(now, self._first_seen[ino], interval)
                   for ino in active}
        return attribute(inode_pids, active, weights, total_rx, total_tx,
                         pid_start, restricted)

    def open_sockets(self):
        """pid -> open network socket count (from the last fd scan).

        Feeds the Network page's Conns column (r113). Restricted pids (no
        readable fd table) are absent from the map — the page renders "—".
        """
        return {pid: len(cached[1]) for pid, cached in self._fd_cache.items()
                if cached is not None}

    def families_for(self, pids):
        """Sorted socket-family labels currently held by any of ``pids``.

        Feeds the preview "socket families in use" line. Best-effort: only the
        families observed on the most recent :meth:`poll` are known here.
        """
        pids = set(pids)
        fams = set()
        # The cache stores pid->inodes; invert only for the requested pids.
        for pid in pids:
            cached = self._fd_cache.get(pid)
            if cached is None:
                continue
            for ino in cached[1]:
                family = self._families.get(ino)
                if family is not None:
                    fams = fams | {family}
        return sorted(fams)

    # -- internals --------------------------------------------------------

    def _scan(self, pid_start):
        inode_pids = {}
        restricted = set()
        for pid in pid_start:
            inodes = self._scan_one(pid)
            if inodes is None:
                restricted.add(pid)
                continue
            for ino in inodes:
                inode_pids.setdefault(ino, set()).add(pid)
        return inode_pids, restricted

    def _scan_one(self, pid):
        """Cached fd inode set for a pid, or ``None`` if the fd table is EACCES.

        Rescans only when the fd directory mtime changed (incremental cache).
        """
        mtime = self._fd_mtime(pid)
        cached = self._fd_cache.get(pid)
        if cached is not None and mtime is not None and cached[0] == mtime:
            return cached[1]
        try:
            inodes = frozenset(self._scan_fds(pid))
        except PermissionError:
            self._fd_cache.pop(pid, None)
            return None
        self._fd_cache[pid] = (mtime, inodes)
        return inodes
