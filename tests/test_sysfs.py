"""Fixture tests for src/modules/sysfs.py.

hwmon temperature + fan trees, cpufreq (cpuinfo and sysfs fallback), GPU busy,
and graceful degradation when the nodes are absent (universality mandate).
All reads are against tests/fixtures/sys/ and tests/fixtures/proc/cpuinfo.
"""

import os

import sysfs

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SYS = os.path.join(FIX, "sys")
PROC = os.path.join(FIX, "proc")
MISSING = os.path.join(FIX, "does_not_exist")


# ---------------------------------------------------------------------------
# temperatures
# ---------------------------------------------------------------------------

def test_read_temperatures():
    temps = sysfs.read_temperatures(sys_root=SYS)
    by_celsius = {t["celsius"]: t for t in temps}
    assert 45.0 in by_celsius
    assert 42.0 in by_celsius
    # temp1 has an explicit label; temp2 falls back to the hwmon chip name.
    assert by_celsius[45.0]["label"] == "Package id 0"
    assert by_celsius[45.0]["chip"] == "coretemp"
    assert by_celsius[42.0]["label"] == "coretemp"


def test_read_temperatures_missing_hwmon_degrades():
    assert sysfs.read_temperatures(sys_root=MISSING) == []


# ---------------------------------------------------------------------------
# fans
# ---------------------------------------------------------------------------

def test_read_fans():
    fans = sysfs.read_fans(sys_root=SYS)
    assert len(fans) == 1
    assert fans[0]["rpm"] == 3000
    assert fans[0]["label"] == "CPU Fan"
    assert fans[0]["chip"] == "thinkpad"


def test_read_fans_missing_degrades():
    assert sysfs.read_fans(sys_root=MISSING) == []


# ---------------------------------------------------------------------------
# cpu frequency
# ---------------------------------------------------------------------------

def test_read_cpu_freq_from_cpuinfo():
    freq = sysfs.read_cpu_freq(proc_root=PROC, sys_root=SYS)
    assert freq["per_core"] == [2400.0, 1800.5]
    assert freq["min"] == 1800.5
    assert freq["max"] == 2400.0
    assert freq["avg"] == (2400.0 + 1800.5) / 2


def test_read_cpu_freq_sysfs_fallback():
    # No cpuinfo at proc_root -> fall back to scaling_cur_freq (kHz -> MHz).
    freq = sysfs.read_cpu_freq(proc_root=MISSING, sys_root=SYS)
    assert freq["per_core"] == [2400.0, 1800.0]
    assert freq["max"] == 2400.0


def test_read_cpu_freq_absent_is_none():
    assert sysfs.read_cpu_freq(proc_root=MISSING, sys_root=MISSING) is None


# ---------------------------------------------------------------------------
# GPU busy
# ---------------------------------------------------------------------------

def test_read_gpu_busy():
    assert sysfs.read_gpu_busy(sys_root=SYS) == 37


def test_read_gpu_busy_absent_is_none():
    assert sysfs.read_gpu_busy(sys_root=MISSING) is None
