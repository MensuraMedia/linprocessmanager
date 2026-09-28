"""Pure disk capacity + I/O-rate math for the Disks page (Phase 6, task 011).

UI-import-free and stdlib-only, headlessly testable against plain dicts and
duck-typed ``statvfs`` results. Three concerns:

- **Capacity math** — turn an ``os.statvfs`` result into the quantities the
  Disks table shows (df-style usage %, the bavail-vs-bfree distinction, inode
  %) per ``docs/modules/disks-capacity.md`` §1.
- **I/O rates** — per-device read/write bytes/s + busy% from two
  ``procfs.system_diskstats`` snapshots. The counter-reset clamp is *shared*
  with the network delta machinery: :func:`disk_rates` calls the sampler's
  ``_rate`` / ``_util_pct`` so a reset is a gap (``None``), never a negative
  spike.
- **Enumeration rules** — pseudo/loop hiding, bind-mount dedup by ``st_dev``,
  whole-disk/partition topology, and unmounted-device detection — all as pure
  list transforms so the page stays a thin view.

Boundary law: no ``gi``, no toolkit; the page owns ``os.statvfs`` / ``os.stat``
(off the UI thread) and hands the results here.
"""

import re

try:  # app layout: python3 src/main.py (src on sys.path)
    from modules import manager_rank as mr
    from modules.manager_sampler import _rate, _util_pct
except ImportError:  # standalone/test layout (src/modules on sys.path)
    import manager_rank as mr
    from manager_sampler import _rate, _util_pct

_SECTOR = 512  # /proc/diskstats sector counters are always 512-byte units.

# Fixed usage-zone thresholds (percent) when no r071 baseline provider is
# supplied. The provider's derived disk thresholds (yellow 42 / red 60 on an
# SSD) override these — see :func:`usage_zone`.
DEFAULT_YELLOW = 60.0
DEFAULT_RED = 85.0

# Filesystem types hidden by default: kernel/virtual filesystems plus the
# squashfs images snap loop-mounts. These carry no operator-meaningful disk
# capacity, so they fold into the "N hidden" count row (the kernel-threads
# pattern). Real on-disk filesystems (ext4/btrfs/xfs/vfat/…) are never here.
# "overlay" is deliberately NOT here: a container's root filesystem is overlay
# and carries real, operator-meaningful capacity — hiding it would blank the
# main row. tmpfs IS hidden (RAM-backed, not disk) — an interpretation call
# documented in the task report.
_PSEUDO_FSTYPES = frozenset({
    "proc", "sysfs", "devtmpfs", "tmpfs", "devpts", "cgroup", "cgroup2",
    "pstore", "bpf", "securityfs", "debugfs", "tracefs", "configfs",
    "fusectl", "fuse.gvfsd-fuse", "mqueue", "hugetlbfs", "ramfs", "nsfs",
    "autofs", "binfmt_misc", "efivarfs", "squashfs",
    "rpc_pipefs", "selinuxfs",
})

_RAMLOOP_RE = re.compile(r"^(?:ram|loop)\d+$")


# ---------------------------------------------------------------------------
# Capacity math (statvfs).
# ---------------------------------------------------------------------------

def _empty_capacity():
    return {
        "total": None, "used": None, "free": None, "available": None,
        "system_free": None, "usage_pct": None, "inode_pct": None,
    }


def capacity(st):
    """Capacity dict from an ``os.statvfs`` result (or ``None``).

    ``st`` may be any object exposing the ``f_frsize``/``f_bsize``,
    ``f_blocks``/``f_bfree``/``f_bavail`` and ``f_files``/``f_ffree`` fields.
    ``None`` (statvfs failed / stale mount) yields the all-``None`` dict so the
    caller renders "—" rather than a fabricated 0 (r039 taxonomy).

    Block size is ``f_frsize`` (the fundamental unit ``f_blocks`` counts),
    falling back to ``f_bsize`` — this matches ``df`` and keeps the byte totals
    honest on filesystems where the two differ. Usage % is df-style
    (``used / (used + available)``), so the root reserve is excluded from the
    denominator, and ``free`` is the user-available space (``f_bavail``) the
    operator can still write.
    """
    if st is None:
        return _empty_capacity()

    block = getattr(st, "f_frsize", 0) or getattr(st, "f_bsize", 0)
    blocks = getattr(st, "f_blocks", 0)
    bfree = getattr(st, "f_bfree", 0)
    bavail = getattr(st, "f_bavail", 0)
    if not block or not blocks:
        # A filesystem that reports no blocks (some pseudo mounts) has no
        # meaningful capacity — honest "—", never a divide by zero.
        result = _empty_capacity()
    else:
        total = blocks * block
        available = bavail * block
        system_free = bfree * block
        used = (blocks - bfree) * block
        denom = used + available
        usage_pct = (used / denom * 100.0) if denom > 0 else None
        result = {
            "total": total,
            "used": used,
            "free": available,          # user-available (bavail) — the "Free" column
            "available": available,     # explicit alias for callers
            "system_free": system_free,  # includes the root reserve (bfree)
            "usage_pct": usage_pct,
            "inode_pct": None,
        }

    files = getattr(st, "f_files", 0)
    ffree = getattr(st, "f_ffree", 0)
    if files and files > 0:
        result["inode_pct"] = (1.0 - ffree / files) * 100.0
    return result


# ---------------------------------------------------------------------------
# Zone mapping (r071 baseline-provider override).
# ---------------------------------------------------------------------------

def usage_zone(pct, yellow=DEFAULT_YELLOW, red=DEFAULT_RED):
    """Zone name for a usage percent, using the SAME machinery as every gauge.

    Returns one of :data:`mr.ZONE_NOMINAL` / :data:`mr.ZONE_MEDIUM` /
    :data:`mr.ZONE_NEAR`, or ``None`` when the value is unknown. ``yellow`` /
    ``red`` come from the r071 thresholds provider (``Thresholds.get("disk",
    …)`` — yellow 42 / red 60 on this SSD); the fixed defaults apply when no
    provider is consulted.
    """
    if pct is None:
        return None
    if red is not None and pct >= red:
        return mr.ZONE_NEAR
    if yellow is not None and pct >= yellow:
        return mr.ZONE_MEDIUM
    return mr.ZONE_NOMINAL


# ---------------------------------------------------------------------------
# I/O rates (shared counter-reset clamp).
# ---------------------------------------------------------------------------

def disk_rates(cur, prev, dwall):
    """Per-device ``{read_rate, write_rate, busy}`` from two diskstats snapshots.

    ``cur`` / ``prev`` are :func:`procfs.system_diskstats` dicts; ``dwall`` is
    the wall-clock gap (seconds) between them. Rates are bytes/s
    (``sectors × 512 / Δt``); ``busy`` is the io_ticks utilisation percent. A
    missing previous device, a missing counter, a non-positive Δt, or a counter
    *reset* (negative delta — device re-enumerated, wrap) all yield ``None`` for
    that field via the shared ``_rate`` / ``_util_pct`` clamp: a reset is a gap,
    not a spike.
    """
    out = {}
    for dev, vals in (cur or {}).items():
        prev_dev = (prev or {}).get(dev)
        read_rate = write_rate = busy = None
        if prev_dev is not None:
            sr = _rate(vals.get("sectors_read"), prev_dev.get("sectors_read"), dwall)
            sw = _rate(vals.get("sectors_written"),
                       prev_dev.get("sectors_written"), dwall)
            read_rate = sr * _SECTOR if sr is not None else None
            write_rate = sw * _SECTOR if sw is not None else None
            busy = _util_pct(vals.get("io_ticks"), prev_dev.get("io_ticks"), dwall)
        out[dev] = {"read_rate": read_rate, "write_rate": write_rate, "busy": busy}
    return out


# ---------------------------------------------------------------------------
# Enumeration rules (pseudo/loop hiding, dedup, topology).
# ---------------------------------------------------------------------------

def is_pseudo(fstype, device):
    """True for a filesystem hidden by default (pseudo / squashfs / loop).

    ``fstype`` in the pseudo/virtual set, or a device backed by a loop node
    (``/dev/loop*``) — snaps mount squashfs over loop, so either signal hides
    the row. Real block devices under ``/dev/`` with a real fstype stay
    visible.
    """
    if fstype in _PSEUDO_FSTYPES:
        return True
    base = device.rsplit("/", 1)[-1]
    if base.startswith("loop") and base[4:].isdigit():
        return True
    return False


def dedup_by_stdev(entries):
    """Drop duplicate filesystems (bind mounts) keeping the first per ``st_dev``.

    Bind mounts and a device mounted twice share an ``st_dev``; the first
    occurrence (kernel order) wins. Entries whose ``st_dev`` is ``None`` (stat
    failed) are always kept — an unprovable duplicate is never silently
    dropped.
    """
    seen = set()
    out = []
    for entry in entries:
        dev_id = entry.get("st_dev")
        if dev_id is not None:
            if dev_id in seen:
                continue
            seen.add(dev_id)
        out.append(entry)
    return out


def _is_child(child, parent):
    """True when block-device name ``child`` is a partition of ``parent``.

    ``sda1`` -> ``sda`` (suffix all digits, parent ends in a letter);
    ``nvme0n1p2`` -> ``nvme0n1`` (suffix ``p`` + digits, parent ends in a
    digit). Anything else is unrelated.
    """
    if child == parent or not child.startswith(parent) or not parent:
        return False
    rest = child[len(parent):]
    if rest.isdigit() and not parent[-1].isdigit():
        return True
    if rest.startswith("p") and rest[1:].isdigit() and parent[-1].isdigit():
        return True
    return False


def top_level_devices(names):
    """Whole-disk device names (no parent in the set), excluding ram/loop.

    Used to sum read/write totals and pick the busiest device without
    double-counting a disk and its partitions.
    """
    names = set(names)
    tops = set()
    for name in names:
        if _RAMLOOP_RE.match(name):
            continue
        if any(_is_child(name, other) for other in names if other != name):
            continue
        tops.add(name)
    return tops


def unmounted_devices(diskstats_names, mounted_basenames):
    """Leaf block devices carrying no mount — the flagged rows.

    A *leaf* has no partitions of its own (a whole disk with partitions is not
    itself a filesystem, so it never flags). ram/loop pseudo devices are
    excluded. ``mounted_basenames`` is the set of device basenames already in
    the mount table. Returns a sorted list of device names.
    """
    names = set(diskstats_names)
    parents = {p for p in names if any(_is_child(c, p) for c in names)}
    out = []
    for name in names:
        if _RAMLOOP_RE.match(name):
            continue
        if name in parents:
            continue
        if name in mounted_basenames:
            continue
        out.append(name)
    return sorted(out)


def device_basename(device):
    """The diskstats key for a mount device path (``/dev/nvme0n1p2`` -> name).

    A non-``/dev`` source (``tmpfs``, ``cgroup2``, an NFS ``host:/export``) has
    no block-device counterpart -> ``None`` (no rate row to join).
    """
    if not device.startswith("/dev/"):
        return None
    return device[len("/dev/"):]
