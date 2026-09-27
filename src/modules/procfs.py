"""Pure /proc readers for linprocman.

Turns ``/proc`` bytes into plain dicts. No UI imports, no state, no globals
beyond the constants read once from the running kernel (page size, clock
tick). This is one of only two modules (with ``sysfs.py``) that reads kernel
interfaces, so this is the only file that knows ``/proc`` file layouts.

Spec: docs/modules/procfs-data.md (binding). Parsing rules and the error
taxonomy below are taken verbatim from that document.

Error taxonomy
--------------
- ``FileNotFoundError`` -> the process exited; the per-PID readers let it
  propagate so the caller drops the row.
- ``PermissionError`` (hidepid >= 1, other users) -> a minimal *locked* dict:
  ``pid`` plus every data field ``None`` and ``locked=True``. The row stays,
  visibly restricted, and is distinct from an exit.
- ``parse_io`` / ``parse_smaps_rollup`` unreadable -> ``None`` (the caller
  renders "-" cells); never an error past the caller.

No other exception escapes a reader.

Import policy: stdlib only, and only ``os``/``re`` here (constraint 6 of the
task contract; the AST gate enforces the no-network rule across ``src/``).
"""

import os
import re

# Read once from the running kernel; never hard-coded (procfs-data.md).
PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")
CLK_TCK = os.sysconf("SC_CLK_TCK")

# Default kernel mount point. Tests pass a fixture tree via ``proc_root`` so
# every parser is exercised against bytes, never the live kernel.
PROC = "/proc"

_KB = 1024


# ---------------------------------------------------------------------------
# Low-level IO (single choke point so tests can simulate PermissionError).
# ---------------------------------------------------------------------------

def _read_bytes(path):
    """Read a whole /proc file as bytes. Lets OSError subclasses propagate."""
    with open(path, "rb") as handle:
        return handle.read()


def _pid_path(proc_root, pid, name):
    return os.path.join(proc_root, str(pid), name)


def _to_int(token):
    try:
        return int(token)
    except (TypeError, ValueError):
        return None


def _to_float(token):
    try:
        return float(token)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Per-PID readers.
# ---------------------------------------------------------------------------

def _locked(pid, keys):
    """Minimal locked dict: pid + every data field None + locked marker."""
    row = {"pid": pid, "locked": True}
    for key in keys:
        row[key] = None
    return row


_STAT_KEYS = (
    "comm", "state", "ppid", "utime", "stime", "starttime",
    "nice", "num_threads", "rss_pages", "rss_bytes",
)


def decode_stat(raw):
    """Parse ``/proc/<pid>/stat`` bytes into a dict, or ``None`` if truncated.

    comm is everything between the first ``(`` and the **last** ``)`` (it may
    contain spaces and parentheses). After the last ``)`` the remainder splits
    on whitespace into ``tokens`` where ``tokens[0]`` is proc(5) field 3
    (state) and field *n* is ``tokens[n-3]``.
    """
    text = raw.decode("utf-8", "replace")
    try:
        open_paren = text.index("(")
        close_paren = text.rindex(")")
    except ValueError:
        return None
    if close_paren < open_paren:
        return None

    pid = _to_int(text[:open_paren].strip())
    comm = text[open_paren + 1:close_paren]
    tokens = text[close_paren + 1:].split()

    # Need through field 24 (rss) -> tokens[21]; anything shorter is truncated.
    if len(tokens) < 22:
        return None

    rss_pages = _to_int(tokens[21])
    rss_bytes = rss_pages * PAGE_SIZE if rss_pages is not None else None
    return {
        "pid": pid,
        "locked": False,
        "comm": comm,
        "state": tokens[0],
        "ppid": _to_int(tokens[1]),
        "utime": _to_int(tokens[11]),
        "stime": _to_int(tokens[12]),
        "nice": _to_int(tokens[16]),
        "num_threads": _to_int(tokens[17]),
        "starttime": _to_int(tokens[19]),
        "rss_pages": rss_pages,
        "rss_bytes": rss_bytes,
    }


def parse_stat(pid, proc_root=PROC):
    """Read+parse ``/proc/<pid>/stat``.

    FileNotFoundError propagates (process exited). PermissionError -> locked
    dict. A truncated/short line yields ``None`` (skip this PID this sample).
    """
    try:
        raw = _read_bytes(_pid_path(proc_root, pid, "stat"))
    except PermissionError:
        return _locked(pid, _STAT_KEYS)
    return decode_stat(raw)


_STATUS_KEYS = (
    "name", "state", "ppid", "uid",
    "vm_rss_bytes", "vm_size_bytes", "vm_swap_bytes", "shared_bytes",
)


def decode_status(raw):
    """Parse ``/proc/<pid>/status`` bytes.

    VmRSS is the memory source of truth; shared = RssFile + RssShmem. PPid is
    surfaced for the sampler's cross-check against stat. Fields absent for the
    process (e.g. kernel threads have no VmRSS) come back as ``None``.
    """
    text = raw.decode("utf-8", "replace")
    fields = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()

    def kb_bytes(key):
        value = fields.get(key)
        if value is None:
            return None
        number = _to_int(value.split()[0]) if value.split() else None
        return number * _KB if number is not None else None

    uid = None
    if "Uid" in fields:
        parts = fields["Uid"].split()
        if parts:
            uid = _to_int(parts[0])

    rss_file = kb_bytes("RssFile")
    rss_shmem = kb_bytes("RssShmem")
    if rss_file is None and rss_shmem is None:
        shared = None
    else:
        shared = (rss_file or 0) + (rss_shmem or 0)

    return {
        "pid": _to_int(fields.get("Pid")),
        "locked": False,
        "name": fields.get("Name"),
        "state": fields.get("State", "").split()[0] if fields.get("State") else None,
        "ppid": _to_int(fields.get("PPid")),
        "uid": uid,
        "vm_rss_bytes": kb_bytes("VmRSS"),
        "vm_size_bytes": kb_bytes("VmSize"),
        "vm_swap_bytes": kb_bytes("VmSwap"),
        "shared_bytes": shared,
    }


def parse_status(pid, proc_root=PROC):
    """Read+parse ``/proc/<pid>/status``. PermissionError -> locked dict."""
    try:
        raw = _read_bytes(_pid_path(proc_root, pid, "status"))
    except PermissionError:
        return _locked(pid, _STATUS_KEYS)
    return decode_status(raw)


def decode_statm(raw):
    """Parse ``/proc/<pid>/statm`` bytes (values in pages).

    Fields: size resident shared text lib data dt. Used only as the shared-page
    fallback; VmRSS remains the memory source of truth.
    """
    parts = raw.split()
    if len(parts) < 3:
        return None
    size = _to_int(parts[0])
    resident = _to_int(parts[1])
    shared = _to_int(parts[2])
    return {
        "size_pages": size,
        "resident_pages": resident,
        "shared_pages": shared,
        "size_bytes": size * PAGE_SIZE if size is not None else None,
        "resident_bytes": resident * PAGE_SIZE if resident is not None else None,
        "shared_bytes": shared * PAGE_SIZE if shared is not None else None,
    }


def parse_statm(pid, proc_root=PROC):
    """Read+parse ``/proc/<pid>/statm``. PermissionError -> ``None``."""
    try:
        raw = _read_bytes(_pid_path(proc_root, pid, "statm"))
    except PermissionError:
        return None
    return decode_statm(raw)


def decode_io(raw):
    """Parse ``/proc/<pid>/io`` bytes -> read/write byte counters."""
    fields = {}
    for line in raw.decode("utf-8", "replace").splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = _to_int(value.strip())
    return {
        "read_bytes": fields.get("read_bytes"),
        "write_bytes": fields.get("write_bytes"),
        "rchar": fields.get("rchar"),
        "wchar": fields.get("wchar"),
    }


def parse_io(pid, proc_root=PROC):
    """Read+parse ``/proc/<pid>/io``.

    io is routinely restricted (EACCES) or absent; either way the caller wants
    "-" cells, not an error, so both PermissionError and FileNotFoundError
    collapse to ``None`` here (procfs-data.md: "never error past caller").
    """
    try:
        raw = _read_bytes(_pid_path(proc_root, pid, "io"))
    except (PermissionError, FileNotFoundError):
        return None
    return decode_io(raw)


def decode_smaps_rollup(raw):
    """Parse ``/proc/<pid>/smaps_rollup`` bytes -> Pss/Rss/Pss_Anon bytes."""
    fields = {}
    for line in raw.decode("utf-8", "replace").splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        tokens = value.split()
        fields[key.strip()] = _to_int(tokens[0]) if tokens else None

    def kb_bytes(key):
        number = fields.get(key)
        return number * _KB if number is not None else None

    return {
        "pss_bytes": kb_bytes("Pss"),
        "rss_bytes": kb_bytes("Rss"),
        "pss_anon_bytes": kb_bytes("Pss_Anon"),
    }


def parse_smaps_rollup(pid, proc_root=PROC):
    """Read+parse ``/proc/<pid>/smaps_rollup`` (selected process only).

    Unreadable (EACCES) or absent -> ``None``.
    """
    try:
        raw = _read_bytes(_pid_path(proc_root, pid, "smaps_rollup"))
    except (PermissionError, FileNotFoundError):
        return None
    return decode_smaps_rollup(raw)


def decode_cmdline(raw):
    """Parse ``/proc/<pid>/cmdline`` bytes -> argv list.

    Arguments are NUL-separated with a trailing NUL. Kernel threads *and*
    zombies read empty here -> ``[]``.
    """
    if not raw:
        return []
    parts = raw.split(b"\x00")
    return [p.decode("utf-8", "replace") for p in parts if p]


def snapshot_procs(proc_root=PROC):
    """Live process table: {(pid, starttime): {pid, ppid, starttime, comm}}.

    The fresh-collection source for group actions — collect the tree at
    click time, never from a cached snapshot (r074).
    """
    out = {}
    for pid in iter_pids(proc_root):
        try:
            st = parse_stat(pid, proc_root)
        except (FileNotFoundError, PermissionError, OSError):
            continue
        out[(pid, st["starttime"])] = {
            "pid": pid, "starttime": st["starttime"],
            "ppid": st["ppid"], "comm": st["comm"],
            "state": st["state"],
        }
    return out


def read_cmdline(pid, proc_root=PROC):
    """Read+parse ``/proc/<pid>/cmdline``. PermissionError -> ``None``."""
    try:
        raw = _read_bytes(_pid_path(proc_root, pid, "cmdline"))
    except PermissionError:
        return None
    return decode_cmdline(raw)


def is_kernel_thread(cmdline, state):
    """Kernel-thread detector: empty cmdline AND state != Z.

    A zombie's cmdline also reads empty, but zombies are user processes in a
    terminal state and must never be grouped under kthreadd.
    """
    empty = not cmdline
    return empty and state != "Z"


def readlink_target(pid, what, proc_root=PROC):
    """Resolve the ``exe``/``cwd``/``root`` symlink for a PID.

    EACCES (caller shows a lock) and a missing link (kernel threads have no
    ``exe``) both yield ``None``.
    """
    try:
        return os.readlink(_pid_path(proc_root, pid, what))
    except (PermissionError, FileNotFoundError):
        return None
    except OSError:
        return None


def decode_cgroup(raw):
    """Parse ``/proc/<pid>/cgroup`` bytes -> a display unit name.

    Reads the cgroup v2 ``0::<path>`` line. Fallbacks (procfs-data.md):
    ``0::/`` (kernel threads) -> "-"; ``init.scope`` stays as-is; a leaf with a
    ``.scope``/``.service`` suffix has the suffix stripped; otherwise the raw
    path tail.
    """
    path = None
    for line in raw.decode("utf-8", "replace").splitlines():
        if line.startswith("0::"):
            path = line[3:]
            break
    if path is None or path == "/" or path == "":
        return "—"  # em dash
    leaf = path.rstrip("/").rsplit("/", 1)[-1]
    if leaf == "" or leaf == "init.scope":
        return leaf or "—"
    for suffix in (".scope", ".service"):
        if leaf.endswith(suffix):
            return leaf[: -len(suffix)]
    return leaf


def parse_cgroup(pid, proc_root=PROC):
    """Read+parse ``/proc/<pid>/cgroup``. PermissionError -> ``None``."""
    try:
        raw = _read_bytes(_pid_path(proc_root, pid, "cgroup"))
    except PermissionError:
        return None
    return decode_cgroup(raw)


def starttime_to_wall(starttime_jiffies, btime):
    """Wall-clock start = ``btime + starttime / CLK_TCK`` (epoch seconds)."""
    if starttime_jiffies is None or btime is None:
        return None
    return btime + starttime_jiffies / CLK_TCK


# ---------------------------------------------------------------------------
# PID enumeration.
# ---------------------------------------------------------------------------

def iter_pids(proc_root=PROC):
    """Yield the integer PIDs present under ``proc_root``.

    Numeric directory entries only (``/proc`` also holds ``self``, ``stat``,
    ``meminfo`` and friends). The sampler owns timing and identity but must not
    list ``/proc`` itself — the boundary rule keeps every kernel read in this
    module — so PID enumeration lives here. An unreadable/absent ``proc_root``
    yields nothing rather than raising (universality: degrade, never crash).
    """
    try:
        names = os.listdir(proc_root)
    except (FileNotFoundError, PermissionError, NotADirectoryError):
        return
    for name in names:
        if name.isdigit():
            yield int(name)


# ---------------------------------------------------------------------------
# System-wide readers (owned here, fixture-tested).
# ---------------------------------------------------------------------------

def _cpu_line(fields):
    """Split one ``/proc/stat`` cpu line into busy/total/steal jiffies.

    busy = user+nice+system+irq+softirq+iowait (guest already lives inside
    user, so it is never added twice). steal is reported separately but is part
    of total for the % divisor.
    """
    nums = [_to_int(f) or 0 for f in fields]
    # user nice system idle iowait irq softirq steal guest guest_nice
    padded = nums + [0] * (10 - len(nums))
    user, nice, system, idle, iowait, irq, softirq, steal = padded[:8]
    busy = user + nice + system + irq + softirq + iowait
    total = user + nice + system + idle + iowait + irq + softirq + steal
    return {
        "busy": busy,
        "total": total,
        "idle": idle,
        "iowait": iowait,
        "steal": steal,
    }


def decode_system_stat(raw):
    """Parse ``/proc/stat`` bytes.

    Returns aggregate + per-CPU busy/total jiffies, ``btime`` (boot wall-clock,
    seconds), and ``ncpu`` = the count of per-CPU lines (the self-consistent %
    divisor; ``os.cpu_count()`` disagrees when CPUs are offline).
    """
    total = None
    cpus = {}
    btime = None
    for line in raw.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if not parts:
            continue
        head = parts[0]
        if head == "cpu":
            total = _cpu_line(parts[1:])
        elif head.startswith("cpu"):
            index = _to_int(head[3:])
            if index is not None:
                cpus[index] = _cpu_line(parts[1:])
        elif head == "btime":
            btime = _to_int(parts[1]) if len(parts) > 1 else None
    return {
        "btime": btime,
        "ncpu": len(cpus),
        "total": total,
        "cpus": cpus,
    }


def system_stat(proc_root=PROC):
    return decode_system_stat(_read_bytes(os.path.join(proc_root, "stat")))


def decode_meminfo(raw):
    """Parse ``/proc/meminfo`` bytes.

    ``used`` = MemTotal - MemAvailable (not the naive free-buffers). All byte
    values.
    """
    fields = {}
    for line in raw.decode("utf-8", "replace").splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        tokens = value.split()
        fields[key.strip()] = _to_int(tokens[0]) if tokens else None

    def kb_bytes(key):
        number = fields.get(key)
        return number * _KB if number is not None else None

    total = kb_bytes("MemTotal")
    available = kb_bytes("MemAvailable")
    used = total - available if (total is not None and available is not None) else None
    return {
        "total": total,
        "available": available,
        "used": used,
        "cached": kb_bytes("Cached"),
        "swap_total": kb_bytes("SwapTotal"),
        "swap_free": kb_bytes("SwapFree"),
    }


def system_meminfo(proc_root=PROC):
    return decode_meminfo(_read_bytes(os.path.join(proc_root, "meminfo")))


def decode_net_dev(raw):
    """Parse ``/proc/net/dev`` bytes -> per-interface rx/tx bytes.

    The two header lines are skipped and the loopback ``lo`` is excluded at
    parse time (procfs-data.md).
    """
    result = {}
    lines = raw.decode("utf-8", "replace").splitlines()
    for line in lines:
        if ":" not in line:
            continue  # skips the two header lines (no colon)
        name, _, rest = line.partition(":")
        iface = name.strip()
        if iface == "lo":
            continue
        cols = rest.split()
        if len(cols) < 9:
            continue
        result[iface] = {
            "rx_bytes": _to_int(cols[0]),
            "tx_bytes": _to_int(cols[8]),
        }
    return result


def system_net_dev(proc_root=PROC):
    return decode_net_dev(_read_bytes(os.path.join(proc_root, "net", "dev")))


def decode_diskstats(raw):
    """Parse ``/proc/diskstats`` bytes -> per-device counters.

    Columns (1-indexed): 3 name, 4 reads, 6 sectors read, 8 writes, 10 sectors
    written, 13 io_ticks (ms doing I/O).
    """
    result = {}
    for line in raw.decode("utf-8", "replace").splitlines():
        cols = line.split()
        if len(cols) < 13:
            continue
        name = cols[2]
        result[name] = {
            "reads": _to_int(cols[3]),
            "sectors_read": _to_int(cols[5]),
            "writes": _to_int(cols[7]),
            "sectors_written": _to_int(cols[9]),
            "io_ticks": _to_int(cols[12]),
        }
    return result


def system_diskstats(proc_root=PROC):
    return decode_diskstats(_read_bytes(os.path.join(proc_root, "diskstats")))


_PSI_PAIR = re.compile(r"(\w+)=([0-9.]+)")


def _decode_pressure_file(raw):
    """Parse one ``/proc/pressure/*`` file -> {'some': {...}, 'full': {...}}."""
    out = {}
    for line in raw.decode("utf-8", "replace").splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        kind = parts[0]
        stats = {}
        for key, value in _PSI_PAIR.findall(parts[1]):
            try:
                stats[key] = float(value)
            except ValueError:
                continue
        out[kind] = stats
    return out


def system_pressure(proc_root=PROC):
    """Read ``/proc/pressure/{cpu,memory,io}``.

    A resource whose file is absent (PSI not compiled in) comes back ``None``;
    never an error.
    """
    result = {}
    for resource in ("cpu", "memory", "io"):
        path = os.path.join(proc_root, "pressure", resource)
        try:
            result[resource] = _decode_pressure_file(_read_bytes(path))
        except (FileNotFoundError, PermissionError):
            result[resource] = None
    return result


_LOADAVG_KEYS = ("load1", "load5", "load15", "runnable", "total")


def decode_loadavg(raw):
    """Parse ``/proc/loadavg`` bytes -> the three load averages + run-queue.

    Format: ``load1 load5 load15 runnable/total lastpid`` (five whitespace
    tokens, the fourth a ``runnable/total`` pair). Per the r061 sign-off this
    decoder is total and **never raises**: a short line (``len < 5``) or a
    fourth token with no ``/`` yields the full key set with every value
    ``None`` (honest absence, never a fabricated 0). Individual unparseable
    numbers degrade to ``None`` field-by-field.
    """
    none_fields = {key: None for key in _LOADAVG_KEYS}
    parts = raw.decode("utf-8", "replace").split()
    if len(parts) < 5 or "/" not in parts[3]:
        return none_fields
    runnable_s, _, total_s = parts[3].partition("/")
    return {
        "load1": _to_float(parts[0]),
        "load5": _to_float(parts[1]),
        "load15": _to_float(parts[2]),
        "runnable": _to_int(runnable_s),
        "total": _to_int(total_s),
    }


def system_loadavg(proc_root=PROC):
    """Read+parse ``/proc/loadavg`` (instantaneous — no delta carry).

    Read/decode split with never-raise guards (r061 sign-off): an absent or
    restricted file degrades to the all-``None`` field set rather than raising,
    so the sampler can add ``system.load`` unconditionally.
    """
    try:
        raw = _read_bytes(os.path.join(proc_root, "loadavg"))
    except (FileNotFoundError, PermissionError):
        return decode_loadavg(b"")
    return decode_loadavg(raw)
