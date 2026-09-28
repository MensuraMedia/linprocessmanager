"""Pure-logic tests for src/modules/disks.py + the mounts reader integration.

Every helper is exercised against plain dicts / duck-typed statvfs objects — no
display, no live kernel. Covers: capacity math (bavail-vs-bfree, inodes,
df-style usage %), the shared counter-reset clamp on diskstats rates, zone
mapping with the baseline-provider override, pseudo/loop hiding + hidden count,
bind-mount dedup by st_dev, and whole-disk/partition topology.
"""

import os

import pytest

import disks
import procfs
import manager_rank as mr

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
PROC = os.path.join(FIX, "proc")


class _Statvfs:
    """Duck-typed os.statvfs result for the capacity math."""

    def __init__(self, frsize, blocks, bfree, bavail, files, ffree, bsize=None):
        self.f_frsize = frsize
        self.f_bsize = bsize if bsize is not None else frsize
        self.f_blocks = blocks
        self.f_bfree = bfree
        self.f_bavail = bavail
        self.f_files = files
        self.f_ffree = ffree


# ---------------------------------------------------------------------------
# capacity math
# ---------------------------------------------------------------------------

def test_capacity_df_style_math():
    st = _Statvfs(frsize=1000, blocks=1000, bfree=300, bavail=250,
                  files=1000, ffree=800)
    cap = disks.capacity(st)
    assert cap["total"] == 1_000_000
    assert cap["used"] == 700_000            # (blocks - bfree) * frsize
    assert cap["available"] == 250_000       # bavail * frsize (user-available)
    assert cap["free"] == 250_000            # "Free" column == available
    assert cap["system_free"] == 300_000     # bfree * frsize (incl. reserve)
    # df-style: used / (used + available), NOT used / total.
    assert cap["usage_pct"] == pytest.approx(700_000 / 950_000 * 100.0)
    assert cap["inode_pct"] == pytest.approx(20.0)


def test_capacity_bavail_differs_from_bfree():
    # The reserve makes available (bavail) < system free (bfree); usage % must
    # use available so a "full for the user" disk reads near 100 %.
    st = _Statvfs(frsize=1, blocks=100, bfree=5, bavail=0,
                  files=10, ffree=10)
    cap = disks.capacity(st)
    assert cap["available"] == 0
    assert cap["system_free"] == 5
    assert cap["usage_pct"] == pytest.approx(100.0)  # 95 / (95 + 0)


def test_capacity_none_and_zero_blocks():
    assert disks.capacity(None)["total"] is None
    zero = disks.capacity(_Statvfs(0, 0, 0, 0, 0, 0))
    assert zero["total"] is None
    assert zero["usage_pct"] is None
    assert zero["inode_pct"] is None


def test_capacity_frsize_falls_back_to_bsize():
    st = _Statvfs(frsize=0, blocks=10, bfree=0, bavail=0, files=0, ffree=0,
                  bsize=4096)
    assert disks.capacity(st)["total"] == 40960


# ---------------------------------------------------------------------------
# I/O rates + shared reset clamp
# ---------------------------------------------------------------------------

def test_disk_rates_normal():
    prev = {"sda": {"sectors_read": 100, "sectors_written": 200, "io_ticks": 1000}}
    cur = {"sda": {"sectors_read": 1100, "sectors_written": 200, "io_ticks": 1900}}
    rates = disks.disk_rates(cur, prev, dwall=2.0)["sda"]
    assert rates["read_rate"] == pytest.approx(1000 * 512 / 2.0)
    assert rates["write_rate"] == pytest.approx(0.0)
    assert rates["busy"] == pytest.approx(45.0)  # 900ms / (2s) -> 45 %


def test_disk_rates_counter_reset_is_gap_not_spike():
    prev = {"sda": {"sectors_read": 5000, "sectors_written": 5000, "io_ticks": 5000}}
    cur = {"sda": {"sectors_read": 10, "sectors_written": 10, "io_ticks": 10}}
    rates = disks.disk_rates(cur, prev, dwall=2.0)["sda"]
    assert rates["read_rate"] is None
    assert rates["write_rate"] is None
    assert rates["busy"] is None


def test_disk_rates_first_sample_and_missing_prev():
    cur = {"sda": {"sectors_read": 100, "sectors_written": 100, "io_ticks": 100}}
    rates = disks.disk_rates(cur, prev=None, dwall=2.0)["sda"]
    assert rates == {"read_rate": None, "write_rate": None, "busy": None}
    # A device present now but absent last time is a first sample -> None.
    rates = disks.disk_rates(cur, prev={"sdb": {}}, dwall=2.0)["sda"]
    assert rates["read_rate"] is None


def test_disk_rates_nonpositive_dwall():
    prev = {"sda": {"sectors_read": 0, "sectors_written": 0, "io_ticks": 0}}
    cur = {"sda": {"sectors_read": 100, "sectors_written": 0, "io_ticks": 0}}
    assert disks.disk_rates(cur, prev, dwall=0.0)["sda"]["read_rate"] is None


# ---------------------------------------------------------------------------
# zone mapping + baseline override
# ---------------------------------------------------------------------------

def test_usage_zone_fixed_defaults():
    assert disks.usage_zone(50.0) == mr.ZONE_NOMINAL
    assert disks.usage_zone(70.0) == mr.ZONE_MEDIUM
    assert disks.usage_zone(90.0) == mr.ZONE_NEAR
    assert disks.usage_zone(None) is None


def test_usage_zone_baseline_provider_override():
    # This machine's derived disk thresholds (yellow 42 / red 60) shift the
    # bands: 50 % is amber (not nominal) and 65 % is critical (not medium).
    assert disks.usage_zone(30.0, yellow=42.0, red=60.0) == mr.ZONE_NOMINAL
    assert disks.usage_zone(50.0, yellow=42.0, red=60.0) == mr.ZONE_MEDIUM
    assert disks.usage_zone(65.0, yellow=42.0, red=60.0) == mr.ZONE_NEAR


# ---------------------------------------------------------------------------
# pseudo/loop hiding + hidden count
# ---------------------------------------------------------------------------

def test_is_pseudo_classification():
    assert disks.is_pseudo("ext4", "/dev/sda1") is False
    assert disks.is_pseudo("btrfs", "/dev/nvme0n1p2") is False
    assert disks.is_pseudo("squashfs", "/dev/loop0") is True
    assert disks.is_pseudo("proc", "proc") is True
    assert disks.is_pseudo("tmpfs", "tmpfs") is True
    assert disks.is_pseudo("ext4", "/dev/loop7") is True   # loop-backed real fs


def test_hidden_count_from_fixture_mounts():
    mounts = procfs.system_mounts(proc_root=PROC)
    hidden = [m for m in mounts if disks.is_pseudo(m["fstype"], m["device"])]
    visible = [m for m in mounts if not disks.is_pseudo(m["fstype"], m["device"])]
    # sysfs, proc, devtmpfs, tmpfs, cgroup2 + two squashfs loops = 7 hidden.
    assert len(hidden) == 7
    # ext4 x2 + btrfs x2 (before st_dev dedup) stay visible.
    assert len(visible) == 4


# ---------------------------------------------------------------------------
# dedup by st_dev
# ---------------------------------------------------------------------------

def test_dedup_by_stdev_drops_bind_mounts():
    entries = [
        {"device": "/dev/nvme1n1", "mount": "/mnt/data", "st_dev": 42},
        {"device": "/dev/nvme1n1", "mount": "/mnt/data backup", "st_dev": 42},
        {"device": "/dev/nvme0n1p2", "mount": "/", "st_dev": 7},
    ]
    out = disks.dedup_by_stdev(entries)
    assert [e["mount"] for e in out] == ["/mnt/data", "/"]


def test_dedup_keeps_entries_with_unknown_stdev():
    entries = [{"mount": "/a", "st_dev": None}, {"mount": "/b", "st_dev": None}]
    assert len(disks.dedup_by_stdev(entries)) == 2


# ---------------------------------------------------------------------------
# topology: whole disks + unmounted leaves
# ---------------------------------------------------------------------------

def test_top_level_devices_excludes_partitions_and_pseudo():
    names = ["sda", "sda1", "sda2", "nvme0n1", "nvme0n1p1", "loop0", "ram0", "sr0"]
    assert disks.top_level_devices(names) == {"sda", "nvme0n1", "sr0"}


def test_unmounted_devices_flags_leaf_devices_only():
    names = ["nvme0n1", "nvme0n1p1", "nvme0n1p2", "nvme0n1p3",
             "nvme1n1", "sr0", "loop0", "ram0"]
    mounted = {"nvme0n1p2", "nvme0n1p3", "nvme1n1"}
    # nvme0n1 has partitions (not a fs), its mounted parts are excluded, ram/loop
    # excluded -> only the unmounted leaves nvme0n1p1 and sr0 flag.
    assert disks.unmounted_devices(names, mounted) == ["nvme0n1p1", "sr0"]


def test_device_basename():
    assert disks.device_basename("/dev/nvme0n1p2") == "nvme0n1p2"
    assert disks.device_basename("tmpfs") is None
    assert disks.device_basename("host:/export") is None
