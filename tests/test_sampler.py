"""Tests for src/modules/manager_sampler.py (Phase 2b).

Three concerns, matching the task-003 acceptance gates:

1. The pure step function ``build_snapshot`` — rate math, the first-sample /
   Δwall / counter-reset / PID-recycle guards, the frozen record schema, and the
   ``from_backoff`` / ``rollup`` tagging — exercised with fully injected readers
   and clock (no I/O, no threads).
2. The stateful shell — bounded drop-oldest queue + newest-wins ``drain_latest``,
   the watchdog state machine, backoff interval selection, and the one-sample
   baseline re-arm on interval change.
3. The GLib-free mandate — an AST gate proving the module references no toolkit.

All fixture-backed reads go through ``tests/fixtures/proc``; nothing here touches
the live kernel (that is the opt-in ``live`` tier, tests/test_live_procfs.py).
"""

import ast
import logging
import os

import pytest

import manager_sampler
import procfs

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
PROC = os.path.join(FIX, "proc")

MODULE_PATH = os.path.join(
    os.path.dirname(FIX), "..", "src", "modules", "manager_sampler.py")
MODULE_PATH = os.path.abspath(MODULE_PATH)


# ---------------------------------------------------------------------------
# Builders for injected readers / clock (the mandated test seam).
# ---------------------------------------------------------------------------

def stat_rec(pid, utime=0, stime=0, starttime=111, state="S", comm="proc",
             ppid=1, nice=0, threads=1):
    return {
        "pid": pid, "locked": False, "comm": comm, "state": state, "ppid": ppid,
        "utime": utime, "stime": stime, "nice": nice, "num_threads": threads,
        "starttime": starttime, "rss_pages": 0, "rss_bytes": 0,
    }


def status_rec(pid, uid=1000, rss=2048, vsize=4096, shared=64):
    return {
        "pid": pid, "locked": False, "name": "proc", "state": "S", "ppid": 1,
        "uid": uid, "vm_rss_bytes": rss, "vm_size_bytes": vsize,
        "vm_swap_bytes": 0, "shared_bytes": shared,
    }


def make_readers(*, pids=(), stat=None, status=None, io=None, cmdline=None,
                 cgroup=None, rollup=None, oom=None, affinity=None,
                 system_stat=None, meminfo=None,
                 net=None, diskstats=None, pressure=None, loadavg=None,
                 iter_error=None):
    stat = stat or {}
    status = status or {}
    io = io or {}
    cmdline = cmdline or {}
    cgroup = cgroup or {}
    rollup = rollup or {}
    oom = oom or {}
    affinity = affinity or {}

    def _iter():
        if iter_error is not None:
            raise iter_error
        return iter(pids)

    return manager_sampler.Readers(
        iter_pids=_iter,
        parse_stat=lambda pid: stat.get(pid),
        parse_status=lambda pid: status.get(pid),
        parse_io=lambda pid: io.get(pid),
        read_cmdline=lambda pid: cmdline.get(pid),
        parse_cgroup=lambda pid: cgroup.get(pid),
        parse_smaps_rollup=lambda pid: rollup.get(pid),
        read_oom_score=lambda pid: oom.get(pid),
        read_affinity=lambda pid: affinity.get(pid),
        system_stat=lambda: system_stat,
        system_meminfo=lambda: meminfo,
        system_net_dev=lambda: net or {},
        system_diskstats=lambda: diskstats or {},
        system_pressure=lambda: pressure,
        system_loadavg=lambda: loadavg,
    )


def make_clock(period=2.0, from_backoff=False, rollups=frozenset(),
               uid_name=None):
    return manager_sampler.StepClock(
        clk_tck=100,
        period=period,
        from_backoff=from_backoff,
        uid_name=uid_name or (lambda uid: "user%d" % uid),
        rollup_targets=rollups,
    )


# ===========================================================================
# 1. Pure step function — rate math + guards.
# ===========================================================================

def test_first_sample_emits_none_rates():
    readers = make_readers(pids=[100], stat={100: stat_rec(100, utime=100)},
                           status={100: status_rec(100)})
    snap = manager_sampler.build_snapshot(None, 1000.0, make_clock(), readers)
    rec = snap.procs[(100, 111)]
    assert rec["cpu_pct"] is None
    assert rec["io_read_rate"] is None
    assert rec["io_write_rate"] is None


def test_cpu_pct_from_synthetic_jiffies():
    # Δ(utime+stime) = 50 jiffies over Δwall = 2 s at CLK_TCK 100:
    # 50 / (100 * 2) * 100 = 25.0 % (one core).
    r1 = make_readers(pids=[100], stat={100: stat_rec(100, utime=100, stime=0)},
                      status={100: status_rec(100)})
    snap1 = manager_sampler.build_snapshot(None, 1000.0, make_clock(), r1)

    r2 = make_readers(pids=[100], stat={100: stat_rec(100, utime=150, stime=0)},
                      status={100: status_rec(100)})
    snap2 = manager_sampler.build_snapshot(snap1, 1002.0, make_clock(), r2)
    assert snap2.procs[(100, 111)]["cpu_pct"] == pytest.approx(25.0)


def test_io_rates_bytes_per_second():
    r1 = make_readers(pids=[100], stat={100: stat_rec(100)},
                      status={100: status_rec(100)},
                      io={100: {"read_bytes": 1000, "write_bytes": 2000}})
    snap1 = manager_sampler.build_snapshot(None, 1000.0, make_clock(), r1)

    r2 = make_readers(pids=[100], stat={100: stat_rec(100)},
                      status={100: status_rec(100)},
                      io={100: {"read_bytes": 5000, "write_bytes": 2000}})
    snap2 = manager_sampler.build_snapshot(snap1, 1002.0, make_clock(), r2)
    rec = snap2.procs[(100, 111)]
    assert rec["io_read_rate"] == pytest.approx(2000.0)   # (5000-1000)/2
    assert rec["io_write_rate"] == pytest.approx(0.0)      # (2000-2000)/2


def test_dwall_guard_skips_rates_when_interval_too_short():
    r1 = make_readers(pids=[100], stat={100: stat_rec(100, utime=100)},
                      status={100: status_rec(100)})
    snap1 = manager_sampler.build_snapshot(None, 1000.0, make_clock(), r1)

    r2 = make_readers(pids=[100], stat={100: stat_rec(100, utime=200)},
                      status={100: status_rec(100)})
    # r058 P2-5: guard floor is 0.5×period — jitter above it is ACCEPTED.
    # Δwall = 1.0 s ≥ 0.5×(2.0 s) -> rates compute despite sub-period gap.
    snap2 = manager_sampler.build_snapshot(snap1, 1001.0, make_clock(period=2.0), r2)
    assert snap2.procs[(100, 111)]["cpu_pct"] == 100.0

    # Δwall = 0.5 s < 0.5×period (double-tick) -> rate fields None.
    r3 = make_readers(pids=[100], stat={100: stat_rec(100, utime=300)},
                      status={100: status_rec(100)})
    snap3 = manager_sampler.build_snapshot(snap2, 1001.5, make_clock(period=2.0), r3)
    assert snap3.procs[(100, 111)]["cpu_pct"] is None


def test_counter_reset_emits_none():
    r1 = make_readers(pids=[100], stat={100: stat_rec(100, utime=500)},
                      status={100: status_rec(100)},
                      io={100: {"read_bytes": 9000, "write_bytes": 9000}})
    snap1 = manager_sampler.build_snapshot(None, 1000.0, make_clock(), r1)

    # utime and io both go backwards (reset/wrap) -> no-data, not garbage.
    r2 = make_readers(pids=[100], stat={100: stat_rec(100, utime=100)},
                      status={100: status_rec(100)},
                      io={100: {"read_bytes": 10, "write_bytes": 10}})
    snap2 = manager_sampler.build_snapshot(snap1, 1002.0, make_clock(), r2)
    rec = snap2.procs[(100, 111)]
    assert rec["cpu_pct"] is None
    assert rec["io_read_rate"] is None
    assert rec["io_write_rate"] is None


def test_pid_recycle_mismatch_rearms_like_first_sample():
    r1 = make_readers(pids=[100], stat={100: stat_rec(100, utime=100, starttime=111)},
                      status={100: status_rec(100)})
    snap1 = manager_sampler.build_snapshot(None, 1000.0, make_clock(), r1)

    # Same pid, different starttime -> identity mismatch -> deltas re-arm.
    r2 = make_readers(pids=[100], stat={100: stat_rec(100, utime=999, starttime=999)},
                      status={100: status_rec(100)})
    snap2 = manager_sampler.build_snapshot(snap1, 1002.0, make_clock(), r2)
    assert (100, 111) not in snap2.procs
    assert snap2.procs[(100, 999)]["cpu_pct"] is None


def test_steady_state_zero_delta_is_zero_not_none():
    # A genuine 0 delta over a valid interval is 0.0 (present), never None.
    r = make_readers(pids=[100], stat={100: stat_rec(100, utime=100)},
                     status={100: status_rec(100)},
                     io={100: {"read_bytes": 10, "write_bytes": 10}})
    snap1 = manager_sampler.build_snapshot(None, 1000.0, make_clock(), r)
    snap2 = manager_sampler.build_snapshot(snap1, 1002.0, make_clock(), r)
    rec = snap2.procs[(100, 111)]
    assert rec["cpu_pct"] == pytest.approx(0.0)
    assert rec["io_read_rate"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Pure step function — classification, identity, rollup, backoff tag.
# ---------------------------------------------------------------------------

def test_kthread_defunct_and_normal_classification():
    stat = {
        1: stat_rec(1, state="S", comm="kworker"),   # kthread: empty cmdline, not Z
        2: stat_rec(2, state="Z", comm="defunct"),   # zombie: empty cmdline, Z
        3: stat_rec(3, state="R", comm="app"),       # normal: has cmdline
    }
    cmdline = {1: [], 2: [], 3: ["/usr/bin/app"]}
    readers = make_readers(pids=[1, 2, 3], stat=stat, cmdline=cmdline)
    snap = manager_sampler.build_snapshot(None, 1.0, make_clock(), readers)

    k = snap.procs[(1, 111)]
    assert k["is_kthread"] is True and k["is_defunct"] is False
    z = snap.procs[(2, 111)]
    assert z["is_kthread"] is False and z["is_defunct"] is True
    a = snap.procs[(3, 111)]
    assert a["is_kthread"] is False and a["is_defunct"] is False


def test_unit_and_user_populated():
    readers = make_readers(
        pids=[100], stat={100: stat_rec(100)},
        status={100: status_rec(100, uid=0)},
        cgroup={100: "session-2"})
    snap = manager_sampler.build_snapshot(
        None, 1.0, make_clock(uid_name=lambda uid: "root" if uid == 0 else str(uid)),
        readers)
    rec = snap.procs[(100, 111)]
    assert rec["unit"] == "session-2"
    assert rec["user"] == "root"


def test_locked_process_has_full_schema_and_null_data():
    # PermissionError path: procfs returns a locked dict (pid + Nones). The
    # sampler must still emit a full-schema record with no fabricated data.
    locked_stat = {"pid": 100, "locked": True, "comm": None, "state": None,
                   "ppid": None, "utime": None, "stime": None, "nice": None,
                   "num_threads": None, "starttime": None,
                   "rss_pages": None, "rss_bytes": None}
    locked_status = {"pid": 100, "locked": True, "name": None, "state": None,
                     "ppid": None, "uid": None, "vm_rss_bytes": None,
                     "vm_size_bytes": None, "vm_swap_bytes": None,
                     "shared_bytes": None}
    readers = make_readers(pids=[100], stat={100: locked_stat},
                           status={100: locked_status})
    snap = manager_sampler.build_snapshot(None, 1.0, make_clock(), readers)
    rec = snap.procs[(100, None)]
    assert set(rec) == manager_sampler.RECORD_FIELDS
    assert rec["cpu_pct"] is None
    assert rec["user"] is None
    assert rec["is_kthread"] is False and rec["is_defunct"] is False


def test_truncated_and_exited_pids_are_skipped():
    def raiser(pid):
        raise FileNotFoundError

    readers = manager_sampler.Readers(
        iter_pids=lambda: iter([100, 200]),
        parse_stat=lambda pid: None if pid == 100 else raiser(pid),  # 100 truncated
        parse_status=lambda pid: None, parse_io=lambda pid: None,
        read_cmdline=lambda pid: None, parse_cgroup=lambda pid: None,
        parse_smaps_rollup=lambda pid: None,
        read_oom_score=lambda pid: None, read_affinity=lambda pid: None,
        system_stat=lambda: None, system_meminfo=lambda: None,
        system_net_dev=lambda: {}, system_diskstats=lambda: {},
        system_pressure=lambda: None, system_loadavg=lambda: None)
    snap = manager_sampler.build_snapshot(None, 1.0, make_clock(), readers)
    assert snap.procs == {}


def test_rollup_rides_only_requested_process():
    stat = {100: stat_rec(100), 200: stat_rec(200)}
    rollup = {100: {"pss_bytes": 1024}, 200: {"pss_bytes": 4096}}
    readers = make_readers(pids=[100, 200], stat=stat, rollup=rollup)
    clock = make_clock(rollups=frozenset({(100, 111)}))
    snap = manager_sampler.build_snapshot(None, 1.0, clock, readers)
    assert snap.procs[(100, 111)]["rollup"] == {"pss_bytes": 1024}
    assert snap.procs[(200, 111)]["rollup"] is None


def test_backoff_tag_propagates_to_envelope_and_records():
    readers = make_readers(pids=[100], stat={100: stat_rec(100)})
    snap = manager_sampler.build_snapshot(
        None, 1.0, make_clock(from_backoff=True), readers)
    assert snap.from_backoff is True
    assert snap.procs[(100, 111)]["from_backoff"] is True


# ---------------------------------------------------------------------------
# Pure step function — system section rate math.
# ---------------------------------------------------------------------------

def test_system_cpu_and_net_rates():
    sys1 = {"total": {"busy": 100, "total": 200}, "cpus": {0: {"busy": 100, "total": 200}},
            "ncpu": 1, "btime": 0}
    sys2 = {"total": {"busy": 150, "total": 300}, "cpus": {0: {"busy": 150, "total": 300}},
            "ncpu": 1, "btime": 0}
    net1 = {"eth0": {"rx_bytes": 1000, "tx_bytes": 2000}}
    net2 = {"eth0": {"rx_bytes": 3000, "tx_bytes": 2000}}

    r1 = make_readers(pids=[], system_stat=sys1, net=net1)
    snap1 = manager_sampler.build_snapshot(None, 1000.0, make_clock(), r1)
    r2 = make_readers(pids=[], system_stat=sys2, net=net2)
    snap2 = manager_sampler.build_snapshot(snap1, 1002.0, make_clock(), r2)

    # busy% = Δbusy/Δtotal*100 = 50/100*100 = 50.0
    assert snap2.system["cpu"]["pct"] == pytest.approx(50.0)
    assert snap2.system["cpu"]["per_core"][0] == pytest.approx(50.0)
    assert snap2.system["net"]["eth0"]["rx_rate"] == pytest.approx(1000.0)  # 2000/2
    assert snap2.system["net"]["eth0"]["tx_rate"] == pytest.approx(0.0)


def test_system_load_is_instantaneous_passthrough():
    # loadavg has no delta carry (r061): the reader's dict rides straight onto
    # system.load on every sample, first one included.
    load = {"load1": 0.5, "load5": 0.4, "load15": 0.3, "runnable": 1, "total": 700}
    r = make_readers(pids=[], system_stat=None, loadavg=load)
    snap = manager_sampler.build_snapshot(None, 1000.0, make_clock(), r)
    assert snap.system["load"] == load


def test_system_load_absent_reader_degrades_to_none():
    # A missing loadavg reader result (reader returned None) is carried as None,
    # never a fabricated value and never a crash.
    r = make_readers(pids=[], system_stat=None, loadavg=None)
    snap = manager_sampler.build_snapshot(None, 1000.0, make_clock(), r)
    assert snap.system["load"] is None


# ---------------------------------------------------------------------------
# r093 extended keys (task 010 Stage 1) — cpu_time / mem_pct / io totals /
# oom_score / affinity / cmdline / started; net_* left to attribution.
# ---------------------------------------------------------------------------

def test_extended_keys_default_to_none():
    # Minimal readers (no io/oom/affinity/cmdline, no system stat/meminfo):
    # every new key is present and None — never fabricated (r039).
    readers = make_readers(pids=[100], stat={100: stat_rec(100)})
    snap = manager_sampler.build_snapshot(None, 1.0, make_clock(), readers)
    rec = snap.procs[(100, 111)]
    for key in ("cpu_time", "mem_pct", "io_read_total", "io_write_total",
                "net_rx_rate", "net_tx_rate", "oom_score", "affinity",
                "cmdline", "started"):
        assert key in rec
    # cpu_time IS computable from stat (utime+stime present, default 0) — the
    # only always-None-here keys are the ones needing readers/system data.
    assert rec["cpu_time"] == pytest.approx(0.0)
    assert rec["mem_pct"] is None          # no meminfo total
    assert rec["started"] is None          # no btime
    assert rec["net_rx_rate"] is None and rec["net_tx_rate"] is None


def test_cpu_time_started_and_mem_pct_computed():
    system_stat = {"btime": 1000, "ncpu": 0, "total": None, "cpus": {}}
    meminfo = {"total": 204800, "available": 100000, "used": 104800,
               "cached": 0, "swap_total": 0, "swap_free": 0}
    readers = make_readers(
        pids=[100],
        stat={100: stat_rec(100, utime=100, stime=50, starttime=111)},
        status={100: status_rec(100, rss=2048)},
        system_stat=system_stat, meminfo=meminfo)
    snap = manager_sampler.build_snapshot(
        None, 1.0, make_clock(), readers)  # clk_tck=100
    rec = snap.procs[(100, 111)]
    assert rec["cpu_time"] == pytest.approx(1.5)        # (100+50)/100
    assert rec["started"] == pytest.approx(1000 + 111 / 100.0)
    assert rec["mem_pct"] == pytest.approx(1.0)         # 2048/204800*100


def test_io_totals_are_the_raw_counters_even_on_first_sample():
    readers = make_readers(
        pids=[100], stat={100: stat_rec(100)}, status={100: status_rec(100)},
        io={100: {"read_bytes": 40960, "write_bytes": 8192}})
    snap = manager_sampler.build_snapshot(None, 1.0, make_clock(), readers)
    rec = snap.procs[(100, 111)]
    assert rec["io_read_total"] == 40960     # totals, not rates
    assert rec["io_write_total"] == 8192
    assert rec["io_read_rate"] is None       # rate is still first-sample None


def test_oom_affinity_and_cmdline_from_readers():
    readers = make_readers(
        pids=[100], stat={100: stat_rec(100)},
        cmdline={100: ["/usr/bin/app", "--flag", "value"]},
        oom={100: 42}, affinity={100: (0, 1, 2, 3)})
    snap = manager_sampler.build_snapshot(None, 1.0, make_clock(), readers)
    rec = snap.procs[(100, 111)]
    assert rec["oom_score"] == 42
    assert rec["affinity"] == (0, 1, 2, 3)
    assert rec["cmdline"] == "/usr/bin/app --flag value"


def test_cmdline_empty_and_missing_are_none():
    readers = make_readers(
        pids=[1, 2], stat={1: stat_rec(1), 2: stat_rec(2)},
        cmdline={1: [], 2: None})  # kthread empty argv / restricted None
    snap = manager_sampler.build_snapshot(None, 1.0, make_clock(), readers)
    assert snap.procs[(1, 111)]["cmdline"] is None
    assert snap.procs[(2, 111)]["cmdline"] is None


def test_cmdline_string_is_capped_at_512():
    long_arg = "x" * 1000
    readers = make_readers(
        pids=[100], stat={100: stat_rec(100)}, cmdline={100: [long_arg]})
    snap = manager_sampler.build_snapshot(None, 1.0, make_clock(), readers)
    assert len(snap.procs[(100, 111)]["cmdline"]) == 512


def test_single_proc_stat_read_shared_btime(monkeypatch):
    # The pass reads /proc/stat once: btime for started + the system cpu math
    # both come from the SAME injected system_stat dict (no second read).
    calls = {"n": 0}
    system_stat = {"btime": 5, "ncpu": 1, "total": {"busy": 1, "total": 2},
                   "cpus": {0: {"busy": 1, "total": 2}}}

    def counting_stat():
        calls["n"] += 1
        return system_stat

    readers = manager_sampler.Readers(
        iter_pids=lambda: iter([100]),
        parse_stat=lambda pid: stat_rec(100, starttime=200),
        parse_status=lambda pid: None, parse_io=lambda pid: None,
        read_cmdline=lambda pid: None, parse_cgroup=lambda pid: None,
        parse_smaps_rollup=lambda pid: None,
        read_oom_score=lambda pid: None, read_affinity=lambda pid: None,
        system_stat=counting_stat, system_meminfo=lambda: None,
        system_net_dev=lambda: {}, system_diskstats=lambda: {},
        system_pressure=lambda: None, system_loadavg=lambda: None)
    snap = manager_sampler.build_snapshot(None, 1.0, make_clock(), readers)
    assert calls["n"] == 1  # one /proc/stat read per pass
    assert snap.procs[(100, 200)]["started"] == pytest.approx(5 + 200 / 100.0)


# ===========================================================================
# 2. Schema freeze (acceptance gate 6) — against the fixture tree.
# ===========================================================================

def test_record_field_count_is_r093_signed_set():
    # r048 froze 20 fields; r093 signed 10 more (io_prio DEFERRED, not added) ->
    # 30 fields. See docs/modules/sampling-pipeline.md "Schema freeze r093".
    assert len(manager_sampler.RECORD_FIELDS) == 30
    assert "io_prio" not in manager_sampler.RECORD_FIELDS


def test_record_schema_matches_frozen_appendix():
    readers = manager_sampler.default_readers(PROC)
    snap = manager_sampler.build_snapshot(None, 1.0, make_clock(period=0.0), readers)
    assert snap.procs, "fixture tree should yield at least one process"
    for key, record in snap.procs.items():
        assert set(record) == manager_sampler.RECORD_FIELDS, (
            "record %s deviates from frozen schema: %s" % (key, sorted(record)))


def test_snapshot_envelope_fields():
    readers = manager_sampler.default_readers(PROC)
    snap = manager_sampler.build_snapshot(None, 1.0, make_clock(period=0.0), readers)
    # Public envelope is exactly ts/from_backoff/procs/system; ``raw`` is the
    # documented private delta-carry (not part of the frozen schema).
    import dataclasses
    names = {f.name for f in dataclasses.fields(snap)}
    assert {"ts", "from_backoff", "procs", "system"} <= names
    assert names - {"ts", "from_backoff", "procs", "system"} == {"raw"}
    assert isinstance(snap.system["cpu"], dict)
    assert "mem" in snap.system and "net" in snap.system
    assert "disks" in snap.system and "psi" in snap.system


def test_fixture_tree_classifies_known_pids():
    readers = manager_sampler.default_readers(PROC)
    snap = manager_sampler.build_snapshot(None, 1.0, make_clock(period=0.0), readers)
    # 104 kworker -> kthread; 103 zombie -> defunct; 105 truncated -> skipped.
    assert snap.procs[(104, 350)]["is_kthread"] is True
    assert snap.procs[(103, 200)]["is_defunct"] is True
    assert not any(key[0] == 105 for key in snap.procs)


# ===========================================================================
# 3. Stateful shell — queue, watchdog, backoff, re-arm.
# ===========================================================================

class _Ticker:
    """Deterministic monotonic clock: each call advances by ``step`` seconds."""

    def __init__(self, start=1000.0, step=3.0):
        self.t = start
        self.step = step

    def __call__(self):
        value = self.t
        self.t += self.step
        return value


def test_queue_drop_oldest_and_drain_latest_newest_wins():
    s = manager_sampler.Sampler(proc_root=PROC, queue_size=4)
    for n in range(10):
        s._enqueue(n)
    assert s._queue.qsize() == 4          # bounded
    assert s.drain_latest() == 9          # newest wins
    assert s._queue.qsize() == 0          # and the queue is emptied
    assert s.drain_latest() is None       # empty -> None


def test_drain_latest_empty_returns_none():
    s = manager_sampler.Sampler(proc_root=PROC)
    assert s.drain_latest() is None


def test_tick_enqueues_snapshot_and_advances_baseline():
    s = manager_sampler.Sampler(proc_root=PROC, monotonic=_Ticker(step=3.0))
    s._tick()
    first = s.drain_latest()
    assert isinstance(first, manager_sampler.Snapshot)
    assert first.procs  # fixture processes present
    assert s._prev is first


def test_interval_change_rearms_baseline_for_one_sample():
    s = manager_sampler.Sampler(proc_root=PROC, monotonic=_Ticker(step=3.0),
                                interval=2.0)
    s._tick()  # first sample: no baseline
    s._tick()  # second sample: baseline present -> rates computed (0.0, static fixtures)
    snap2 = s.drain_latest()
    assert snap2.procs[(100, 123456)]["cpu_pct"] == pytest.approx(0.0)

    s.set_interval(5.0)  # interval change -> drop baselines for one sample
    s._tick()
    snap3 = s.drain_latest()
    assert snap3.procs[(100, 123456)]["cpu_pct"] is None


def test_set_interval_clamps_to_bounds():
    s = manager_sampler.Sampler(proc_root=PROC)
    s.set_interval(100.0)
    assert s._interval == manager_sampler.MAX_INTERVAL
    s.set_interval(0.01)
    assert s._interval == manager_sampler.MIN_INTERVAL


def test_backoff_interval_selected_when_iconified_and_inactive():
    s = manager_sampler.Sampler(proc_root=PROC, interval=2.0, backoff_interval=10.0)
    assert s._current_interval() == 2.0
    s.set_activity_state(active=False, iconified=True)
    assert s._current_interval() == 10.0
    # Still visible but inactive -> full cadence (no occlusion-based backoff).
    s.set_activity_state(active=False, iconified=False)
    assert s._current_interval() == 2.0


def test_backoff_tick_tags_snapshot():
    s = manager_sampler.Sampler(proc_root=PROC, monotonic=_Ticker())
    s.set_activity_state(active=False, iconified=True)
    s._tick()
    snap = s.drain_latest()
    assert snap.from_backoff is True


def test_request_rollup_fulfilled_on_next_tick_then_cleared():
    s = manager_sampler.Sampler(proc_root=PROC, monotonic=_Ticker())
    s.request_rollup(100, 123456)
    s._tick()
    snap = s.drain_latest()
    assert snap.procs[(100, 123456)]["rollup"] is not None
    # One-shot: the next tick no longer carries it.
    s._tick()
    snap2 = s.drain_latest()
    assert snap2.procs[(100, 123456)]["rollup"] is None


class _FakeNetAttr:
    """Injected attributor: returns a fixed pid-key -> (rx, tx)|None map."""

    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def poll(self, now, interval, total_rx, total_tx, pid_start):
        self.calls.append((total_rx, total_tx, dict(pid_start)))
        return self.mapping


def test_sampler_enriches_records_with_net_attribution():
    fake = _FakeNetAttr({(100, 123456): (500.0, 250.0)})
    s = manager_sampler.Sampler(proc_root=PROC, monotonic=_Ticker(), netattr=fake)
    s._tick()
    rec = s.drain_latest().procs[(100, 123456)]
    assert rec["net_rx_rate"] == 500.0
    assert rec["net_tx_rate"] == 250.0
    assert fake.calls  # the shell actually ran the attribution pass


def test_sampler_net_attribution_restricted_stays_none():
    # A restricted (Yama) pid maps to None -> the record keeps its None net
    # fields (lock + "—" in the UI), never a fabricated 0.
    fake = _FakeNetAttr({(100, 123456): None})
    s = manager_sampler.Sampler(proc_root=PROC, monotonic=_Ticker(), netattr=fake)
    s._tick()
    rec = s.drain_latest().procs[(100, 123456)]
    assert rec["net_rx_rate"] is None and rec["net_tx_rate"] is None


def test_sampler_net_attribution_failure_never_breaks_tick():
    class _Boom:
        def poll(self, *_a):
            raise RuntimeError("attribution blew up")

    s = manager_sampler.Sampler(proc_root=PROC, monotonic=_Ticker(),
                                netattr=_Boom())
    s._tick()  # must not raise
    snap = s.drain_latest()
    assert snap.procs[(100, 123456)]["net_rx_rate"] is None


def test_watchdog_stops_after_consecutive_failures():
    failing = make_readers(iter_error=RuntimeError("boom"))
    logger = logging.getLogger("test.sampler.watchdog")
    s = manager_sampler.Sampler(readers=failing, max_failures=3,
                                sleep=lambda _s: False, logger=logger)
    s._run()  # runs inline: fails 3 times, then the watchdog breaks the loop
    assert s._failures == 3


def test_watchdog_resets_failure_count_on_success():
    s = manager_sampler.Sampler(proc_root=PROC, monotonic=_Ticker())
    stops = {"n": 0}

    def sleeper(_seconds):
        stops["n"] += 1
        return stops["n"] >= 2  # stop after two successful iterations

    s._sleep = sleeper
    s._run()
    assert s._failures == 0
    assert stops["n"] == 2


# ===========================================================================
# 4. GLib-free mandate (acceptance gate 2) — AST reference gate.
# ===========================================================================

# AST-based (not a raw text grep) so the docstrings that *state* the ban -- which
# necessarily spell "GLib"/"GTK"/"gi" in prose -- are not themselves flagged.
FORBIDDEN_TOKENS = {"gi", "GLib", "Gtk", "Gdk", "GObject",
                    "idle_add", "timeout_add", "GestureClick"}


def _code_identifiers(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names


def test_sampler_is_glib_free():
    with open(MODULE_PATH, "r", encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=MODULE_PATH)
    used = _code_identifiers(tree)
    offenders = sorted(used & FORBIDDEN_TOKENS)
    assert offenders == [], "toolkit references in a GLib-free module: %s" % offenders


# ===========================================================================
# 5. iter_pids (added to procfs.py under this task).
# ===========================================================================

def test_iter_pids_numeric_only():
    pids = set(procfs.iter_pids(PROC))
    assert {100, 101, 102, 103, 104, 105} <= pids
    # Non-numeric /proc entries (stat, meminfo, net, ...) are excluded.
    assert all(isinstance(p, int) for p in pids)


def test_iter_pids_missing_root_yields_nothing():
    assert list(procfs.iter_pids(os.path.join(PROC, "does-not-exist"))) == []
