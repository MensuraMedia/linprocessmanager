"""Hostile-fixture tests for src/modules/procfs.py.

Every parser is exercised against bytes from tests/fixtures/proc/ (a tree that
mirrors the real /proc layout) or against byte literals — never the live
kernel. The error taxonomy (FileNotFoundError -> exit, PermissionError ->
locked, io -> None) is covered too.
"""

import os

import pytest

import procfs

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
PROC = os.path.join(FIX, "proc")
PROC_OFFLINE = os.path.join(FIX, "proc_offline")


# ---------------------------------------------------------------------------
# stat
# ---------------------------------------------------------------------------

def test_stat_normal():
    d = procfs.parse_stat(100, proc_root=PROC)
    assert d["pid"] == 100
    assert d["comm"] == "bash"
    assert d["state"] == "S"
    assert d["ppid"] == 99
    assert d["utime"] == 50
    assert d["stime"] == 20
    assert d["nice"] == 0
    assert d["num_threads"] == 1
    assert d["starttime"] == 123456
    assert d["rss_pages"] == 512
    assert d["rss_bytes"] == 512 * procfs.PAGE_SIZE
    assert d["locked"] is False


def test_stat_comm_with_spaces():
    d = procfs.parse_stat(101, proc_root=PROC)
    assert d["comm"] == "Web Content"
    assert d["state"] == "S"
    assert d["ppid"] == 99
    assert d["num_threads"] == 4
    assert d["starttime"] == 555


def test_stat_comm_with_parens():
    # comm is between the FIRST '(' and the LAST ')'.
    d = procfs.parse_stat(102, proc_root=PROC)
    assert d["comm"] == "a) b (c"
    assert d["state"] == "R"
    assert d["ppid"] == 1
    assert d["num_threads"] == 2


def test_stat_zombie_empty_cmdline():
    d = procfs.parse_stat(103, proc_root=PROC)
    assert d["state"] == "Z"
    # A zombie reads an empty cmdline but is NOT a kernel thread.
    assert procfs.read_cmdline(103, proc_root=PROC) == []
    assert procfs.is_kernel_thread([], d["state"]) is False


def test_stat_truncated_returns_none():
    assert procfs.parse_stat(105, proc_root=PROC) is None


def test_decode_stat_truncated_bytes():
    assert procfs.decode_stat(b"105 (short) S 99 105\n") is None


def test_stat_missing_pid_raises_exit():
    with pytest.raises(FileNotFoundError):
        procfs.parse_stat(999999, proc_root=PROC)


def test_stat_permission_locked(monkeypatch):
    def boom(_path):
        raise PermissionError("hidepid")
    monkeypatch.setattr(procfs, "_read_bytes", boom)
    d = procfs.parse_stat(100, proc_root=PROC)
    assert d["locked"] is True
    assert d["pid"] == 100
    assert d["comm"] is None
    assert d["rss_bytes"] is None


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def test_status_normal():
    d = procfs.parse_status(100, proc_root=PROC)
    assert d["name"] == "bash"
    assert d["state"] == "S"
    assert d["ppid"] == 99
    assert d["uid"] == 1000
    assert d["vm_rss_bytes"] == 2048 * 1024
    assert d["vm_size_bytes"] == 12056 * 1024
    assert d["vm_swap_bytes"] == 128 * 1024
    assert d["shared_bytes"] == (400 + 48) * 1024


def test_status_hidepid_eacces_locked(monkeypatch):
    def boom(_path):
        raise PermissionError("hidepid >= 1")
    monkeypatch.setattr(procfs, "_read_bytes", boom)
    d = procfs.parse_status(100, proc_root=PROC)
    assert d["locked"] is True
    assert d["pid"] == 100
    assert d["vm_rss_bytes"] is None
    assert d["name"] is None


def test_status_kthread_no_vmrss():
    raw = b"Name:\tkworker/0:1\nState:\tS (sleeping)\nPid:\t104\nPPid:\t2\n"
    d = procfs.decode_status(raw)
    assert d["name"] == "kworker/0:1"
    assert d["ppid"] == 2
    assert d["vm_rss_bytes"] is None
    assert d["shared_bytes"] is None


# ---------------------------------------------------------------------------
# statm
# ---------------------------------------------------------------------------

def test_statm_shared_pages():
    d = procfs.parse_statm(100, proc_root=PROC)
    assert d["shared_pages"] == 400
    assert d["resident_pages"] == 512
    assert d["shared_bytes"] == 400 * procfs.PAGE_SIZE


# ---------------------------------------------------------------------------
# io
# ---------------------------------------------------------------------------

def test_io_normal():
    d = procfs.parse_io(100, proc_root=PROC)
    assert d["read_bytes"] == 40960
    assert d["write_bytes"] == 8192


def test_io_missing_returns_none():
    # pid 104 (kthread fixture) has no io file -> None, never an error.
    assert procfs.parse_io(104, proc_root=PROC) is None


def test_io_restricted_returns_none(monkeypatch):
    def boom(_path):
        raise PermissionError("restricted io")
    monkeypatch.setattr(procfs, "_read_bytes", boom)
    assert procfs.parse_io(100, proc_root=PROC) is None


# ---------------------------------------------------------------------------
# smaps_rollup
# ---------------------------------------------------------------------------

def test_smaps_rollup():
    d = procfs.parse_smaps_rollup(100, proc_root=PROC)
    assert d["pss_bytes"] == 1024 * 1024
    assert d["rss_bytes"] == 2048 * 1024
    assert d["pss_anon_bytes"] == 800 * 1024


def test_smaps_rollup_missing_returns_none():
    assert procfs.parse_smaps_rollup(104, proc_root=PROC) is None


# ---------------------------------------------------------------------------
# cmdline + kernel-thread detector
# ---------------------------------------------------------------------------

def test_cmdline_decode_argv():
    assert procfs.decode_cmdline(b"bash\x00-i\x00") == ["bash", "-i"]


def test_cmdline_empty_is_empty_list():
    assert procfs.decode_cmdline(b"") == []
    # kthread fixture (pid 104) has an empty cmdline file.
    assert procfs.read_cmdline(104, proc_root=PROC) == []


def test_is_kernel_thread():
    assert procfs.is_kernel_thread([], "S") is True       # kthread
    assert procfs.is_kernel_thread([], "Z") is False      # zombie, not kthread
    assert procfs.is_kernel_thread(["bash"], "S") is False  # user process


# ---------------------------------------------------------------------------
# cgroup fallbacks
# ---------------------------------------------------------------------------

def test_cgroup_root_is_dash():
    assert procfs.decode_cgroup(b"0::/\n") == "—"


def test_cgroup_init_scope_stays():
    assert procfs.decode_cgroup(b"0::/init.scope\n") == "init.scope"


def test_cgroup_strips_service_suffix():
    raw = b"0::/system.slice/NetworkManager.service\n"
    assert procfs.decode_cgroup(raw) == "NetworkManager"


def test_cgroup_strips_scope_suffix():
    raw = b"0::/user.slice/user-1000.slice/session-2.scope\n"
    assert procfs.decode_cgroup(raw) == "session-2"


def test_cgroup_raw_tail_fallback():
    raw = b"12:pids:/legacy\n0::/somepath\n"
    assert procfs.decode_cgroup(raw) == "somepath"


def test_cgroup_no_v2_line_is_dash():
    assert procfs.decode_cgroup(b"12:pids:/legacy\n") == "—"


def test_parse_cgroup_from_fixture():
    assert procfs.parse_cgroup(100, proc_root=PROC) == "session-2"


# ---------------------------------------------------------------------------
# started-time math
# ---------------------------------------------------------------------------

def test_starttime_to_wall():
    wall = procfs.starttime_to_wall(123456, 1700000000)
    assert wall == 1700000000 + 123456 / procfs.CLK_TCK


def test_starttime_to_wall_none_safe():
    assert procfs.starttime_to_wall(None, 1700000000) is None


# ---------------------------------------------------------------------------
# system_stat
# ---------------------------------------------------------------------------

def test_system_stat_btime_and_busy():
    d = procfs.system_stat(proc_root=PROC)
    assert d["btime"] == 1700000000
    assert d["ncpu"] == 2
    # busy = user+nice+system+irq+softirq+iowait (guest not double counted).
    assert d["total"]["busy"] == 100 + 20 + 50 + 5 + 10 + 30
    assert d["total"]["total"] == 100 + 20 + 50 + 1000 + 30 + 5 + 10 + 0
    assert set(d["cpus"].keys()) == {0, 1}
    assert d["cpus"][0]["busy"] == 50 + 10 + 25 + 2 + 5 + 15


def test_system_stat_cpu_offline_variant():
    d = procfs.system_stat(proc_root=PROC_OFFLINE)
    # cpu1 is offline: only cpu0 and cpu2 lines are present.
    assert d["ncpu"] == 2
    assert set(d["cpus"].keys()) == {0, 2}


# ---------------------------------------------------------------------------
# meminfo
# ---------------------------------------------------------------------------

def test_system_meminfo_used():
    d = procfs.system_meminfo(proc_root=PROC)
    assert d["total"] == 16384000 * 1024
    assert d["available"] == 8000000 * 1024
    # used = MemTotal - MemAvailable (not free-buffers).
    assert d["used"] == (16384000 - 8000000) * 1024
    assert d["swap_total"] == 2000000 * 1024
    assert d["swap_free"] == 1500000 * 1024


# ---------------------------------------------------------------------------
# net/dev
# ---------------------------------------------------------------------------

def test_system_net_dev_excludes_lo():
    d = procfs.system_net_dev(proc_root=PROC)
    assert "lo" not in d
    assert d["eth0"]["rx_bytes"] == 500000
    assert d["eth0"]["tx_bytes"] == 250000
    assert d["wlan0"]["rx_bytes"] == 12345
    assert d["wlan0"]["tx_bytes"] == 54321


# ---------------------------------------------------------------------------
# diskstats
# ---------------------------------------------------------------------------

def test_system_diskstats():
    d = procfs.system_diskstats(proc_root=PROC)
    assert d["sda"]["reads"] == 1000
    assert d["sda"]["writes"] == 800
    assert d["sda"]["io_ticks"] == 900
    assert d["sda"]["sectors_read"] == 80000
    assert d["sda"]["sectors_written"] == 64000
    assert d["nvme0n1"]["reads"] == 2000


# ---------------------------------------------------------------------------
# pressure
# ---------------------------------------------------------------------------

def test_system_pressure():
    d = procfs.system_pressure(proc_root=PROC)
    assert d["cpu"]["some"]["avg10"] == 0.10
    assert d["cpu"]["some"]["total"] == 12345.0
    assert d["memory"]["full"]["avg300"] == 2.50
    assert d["io"]["some"]["avg60"] == 6.00


def test_system_pressure_missing_is_none():
    # proc_offline has no pressure/ dir -> each resource None, never an error.
    d = procfs.system_pressure(proc_root=PROC_OFFLINE)
    assert d["cpu"] is None
    assert d["memory"] is None
    assert d["io"] is None


# ---------------------------------------------------------------------------
# loadavg (r061 — signed decode/read split, never raises)
# ---------------------------------------------------------------------------

def test_decode_loadavg_normal():
    d = procfs.decode_loadavg(b"0.52 0.58 0.59 2/1234 56789\n")
    assert d["load1"] == pytest.approx(0.52)
    assert d["load5"] == pytest.approx(0.58)
    assert d["load15"] == pytest.approx(0.59)
    assert d["runnable"] == 2
    assert d["total"] == 1234


def test_decode_loadavg_short_line_is_all_none():
    # Fewer than five tokens -> every field None (honest absence, no crash).
    d = procfs.decode_loadavg(b"0.52 0.58 0.59\n")
    assert set(d) == {"load1", "load5", "load15", "runnable", "total"}
    assert all(v is None for v in d.values())


def test_decode_loadavg_missing_slash_is_all_none():
    # Fourth token without a '/' -> the run-queue pair is malformed -> all None.
    d = procfs.decode_loadavg(b"0.52 0.58 0.59 2-1234 56789\n")
    assert all(v is None for v in d.values())


def test_decode_loadavg_empty_is_all_none():
    d = procfs.decode_loadavg(b"")
    assert all(v is None for v in d.values())


def test_system_loadavg_from_fixture():
    d = procfs.system_loadavg(proc_root=PROC)
    assert d["load1"] == pytest.approx(0.52)
    assert d["total"] == 1234


def test_system_loadavg_missing_file_never_raises():
    # Absent file -> the all-None field set, not an exception (r061 sign-off).
    d = procfs.system_loadavg(proc_root=os.path.join(PROC, "does-not-exist"))
    assert all(v is None for v in d.values())


# ---------------------------------------------------------------------------
# r093 (task 010) — oom_score / affinity / cmdline_string readers.
# ---------------------------------------------------------------------------

def test_read_oom_score_from_fixture():
    assert procfs.read_oom_score(100, proc_root=PROC) == 667


def test_read_oom_score_missing_is_none():
    # pid 104 has no oom_score fixture -> None, never an error.
    assert procfs.read_oom_score(104, proc_root=PROC) is None


def test_read_oom_score_restricted_is_none(monkeypatch):
    def boom(_path):
        raise PermissionError("restricted")
    monkeypatch.setattr(procfs, "_read_bytes", boom)
    assert procfs.read_oom_score(100, proc_root=PROC) is None


def test_read_affinity_returns_sorted_tuple(monkeypatch):
    monkeypatch.setattr(procfs.os, "sched_getaffinity",
                        lambda pid: {2, 0, 1}, raising=False)
    assert procfs.read_affinity(1234) == (0, 1, 2)


def test_read_affinity_oserror_is_none(monkeypatch):
    def boom(pid):
        raise OSError("EPERM/ESRCH")
    monkeypatch.setattr(procfs.os, "sched_getaffinity", boom, raising=False)
    assert procfs.read_affinity(1234) is None


def test_cmdline_string_joins_caps_and_none():
    assert procfs.cmdline_string(["/bin/app", "-x", "y"]) == "/bin/app -x y"
    assert procfs.cmdline_string([]) is None          # kernel thread / zombie
    assert procfs.cmdline_string(None) is None         # restricted
    assert len(procfs.cmdline_string(["z" * 1000])) == 512


# ---------------------------------------------------------------------------
# r093 (task 010) — socket-owner attribution readers.
# ---------------------------------------------------------------------------

def test_read_net_sockets_maps_inode_to_family():
    net = procfs.read_net_sockets(proc_root=PROC)
    assert net[45678] == "tcp"
    assert net[45679] == "tcp"


def test_read_net_sockets_absent_files_degrade():
    # A tree with no net/ dir -> empty map, never an error.
    net = procfs.read_net_sockets(proc_root=PROC_OFFLINE)
    assert net == {}


def test_read_socket_inodes_parses_symlinks(monkeypatch):
    links = {"0": "socket:[45678]", "1": "/dev/null",
             "2": "socket:[45679]", "3": "pipe:[999]"}
    monkeypatch.setattr(procfs.os, "listdir", lambda _p: list(links))
    monkeypatch.setattr(procfs.os, "readlink",
                        lambda p: links[os.path.basename(p)])
    assert procfs.read_socket_inodes(1234, proc_root=PROC) == {45678, 45679}


def test_read_socket_inodes_eacces_raises(monkeypatch):
    def boom(_p):
        raise PermissionError("Yama")
    monkeypatch.setattr(procfs.os, "listdir", boom)
    with pytest.raises(PermissionError):
        procfs.read_socket_inodes(1234, proc_root=PROC)


def test_read_socket_inodes_exit_is_empty(monkeypatch):
    def boom(_p):
        raise FileNotFoundError("exited")
    monkeypatch.setattr(procfs.os, "listdir", boom)
    assert procfs.read_socket_inodes(1234, proc_root=PROC) == set()


def test_fd_table_mtime_missing_is_none():
    assert procfs.fd_table_mtime(999999, proc_root=PROC) is None


def test_read_maps_basenames_dedups_file_backed_only():
    names, count = procfs.read_maps_basenames(100, proc_root=PROC)
    # anonymous / [stack] regions are skipped; libc appears twice -> deduped.
    assert names == ["bash", "libc.so.6", "libncursesw.so.6"]
    assert count == 3


def test_read_maps_basenames_caps_and_reports_total():
    names, count = procfs.read_maps_basenames(100, proc_root=PROC, cap=2)
    assert names == ["bash", "libc.so.6"]   # capped
    assert count == 3                        # but the true total is reported


def test_read_maps_basenames_absent_is_empty():
    assert procfs.read_maps_basenames(999999, proc_root=PROC) == ([], 0)
