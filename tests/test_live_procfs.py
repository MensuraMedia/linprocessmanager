"""Opt-in ``live`` tier — the sampler against the REAL /proc on this machine.

Deselected by default (pytest.ini: ``addopts = -m "not live"``) so the standard
suite stays hermetic. Run explicitly with::

    python3 -m pytest -m live

Every assertion is an *own-process* invariant — facts that must hold for the
running interpreter regardless of what else is on the machine — so the tier needs
no psutil, no root, and no fixed machine state. r048 added this after live
testing surfaced the ``iter_pids`` boundary gap.
"""

import os

import pytest

import manager_sampler
import procfs

pytestmark = pytest.mark.live

OWN_PID = os.getpid()


def _own_identity():
    stat = procfs.parse_stat(OWN_PID)
    assert stat is not None and not stat.get("locked")
    return (OWN_PID, stat["starttime"])


def _clock(period=0.0, rollups=frozenset()):
    return manager_sampler.StepClock(
        clk_tck=procfs.CLK_TCK, period=period, from_backoff=False,
        uid_name=lambda uid: str(uid), rollup_targets=rollups)


def test_iter_pids_includes_own_pid():
    assert OWN_PID in set(procfs.iter_pids("/proc"))


def test_live_snapshot_contains_own_record_with_frozen_schema():
    readers = manager_sampler.default_readers("/proc")
    snap = manager_sampler.build_snapshot(None, 1.0, _clock(), readers)
    key = _own_identity()
    assert key in snap.procs, "own pid missing from live snapshot"
    rec = snap.procs[key]
    assert set(rec) == manager_sampler.RECORD_FIELDS
    assert rec["pid"] == OWN_PID
    assert rec["name"]              # comm is non-empty for a live process
    assert rec["is_defunct"] is False
    assert rec["mem_rss"] is None or rec["mem_rss"] > 0


def test_live_two_samples_yield_nonnegative_own_cpu_rate():
    readers = manager_sampler.default_readers("/proc")
    key = _own_identity()
    snap1 = manager_sampler.build_snapshot(None, 1.0, _clock(), readers)
    # Δwall = 1.0 s >= period 0.0 and identity is stable -> a real rate.
    snap2 = manager_sampler.build_snapshot(snap1, 2.0, _clock(), readers)
    cpu = snap2.procs[key]["cpu_pct"]
    assert cpu is not None and cpu >= 0.0


def test_live_rollup_for_own_pid():
    readers = manager_sampler.default_readers("/proc")
    key = _own_identity()
    snap = manager_sampler.build_snapshot(None, 1.0, _clock(rollups=frozenset({key})), readers)
    rollup = snap.procs[key]["rollup"]
    # smaps_rollup is readable for one's own process on this machine.
    assert rollup is not None
    assert rollup.get("rss_bytes") is None or rollup["rss_bytes"] > 0


def test_live_system_section_present():
    readers = manager_sampler.default_readers("/proc")
    snap = manager_sampler.build_snapshot(None, 1.0, _clock(), readers)
    assert snap.system["cpu"]["ncpu"] >= 1
    assert snap.system["mem"]["total"] > 0
