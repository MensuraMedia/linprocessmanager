"""Tests for src/modules/manager_actions.py (Phase 3 — actions & permissions).

The module never touches the live kernel here: ``probe`` reads through injected
``stat_reader`` / ``status_reader`` stand-ins and the mutations run against
injected ``kill_func`` / ``setpriority_func`` / ``setaffinity_func`` spies. That
keeps the click-time guard, the confirm matrix, the corrected renice permission
table, the errno contract, the bulk summary, and the zombie no-effect path all
exercised headlessly — matching the actions-permissions.md test list.
"""

import errno
import signal

import pytest

import manager_actions as ma


# ---------------------------------------------------------------------------
# Fixtures / builders.
# ---------------------------------------------------------------------------

MY_UID = 1000


def _stat(pid, starttime, comm="firefox", state="S", nice=0):
    return {
        "pid": pid, "locked": False, "comm": comm, "state": state,
        "ppid": 1, "utime": 0, "stime": 0, "nice": nice,
        "num_threads": 1, "starttime": starttime,
        "rss_pages": 1, "rss_bytes": 4096,
    }


def _status(pid, uid=MY_UID, name="firefox", state="S"):
    return {
        "pid": pid, "locked": False, "name": name, "state": state,
        "ppid": 1, "uid": uid, "vm_rss_bytes": 4096, "vm_size_bytes": 4096,
        "vm_swap_bytes": 0, "shared_bytes": 0,
    }


def _readers(stat_table, status_table):
    def stat_reader(pid, proc_root=None):
        entry = stat_table[pid]
        if entry == "gone":
            raise FileNotFoundError
        return entry

    def status_reader(pid, proc_root=None):
        entry = status_table.get(pid)
        if entry == "gone" or entry is None:
            raise FileNotFoundError
        return entry

    return stat_reader, status_reader


def _probe(pid, key_start, stat, status, uid=MY_UID):
    stat_reader, status_reader = _readers({pid: stat}, {pid: status})
    return ma.probe((pid, key_start), getuid_func=lambda: uid,
                    stat_reader=stat_reader, status_reader=status_reader)


def _target(pid=100, name="firefox", state="S", uid=MY_UID, nice=0,
            own=True, status=ma.OK, key_starttime=555):
    return ma.Target(pid=pid, key_starttime=key_starttime, name=name,
                     state=state, uid=uid, nice=nice, own=own, status=status)


class Spy:
    """Records calls; optionally raises a chosen OSError."""

    def __init__(self, raises=None):
        self.calls = []
        self._raises = raises

    def __call__(self, *args):
        self.calls.append(args)
        if self._raises is not None:
            raise self._raises


# ---------------------------------------------------------------------------
# Guard: fresh-read + starttime compare.
# ---------------------------------------------------------------------------

def test_guard_match_is_ok():
    t = _probe(100, 555, _stat(100, 555), _status(100))
    assert t.status == ma.OK
    assert t.name == "firefox"
    assert t.own is True


def test_guard_mismatch_is_reused():
    # Live starttime differs from the snapshot key -> PID recycled.
    t = _probe(100, 555, _stat(100, 999), _status(100))
    assert t.status == ma.REUSED


def test_guard_reused_does_not_send():
    t = _target(status=ma.REUSED)
    kill = Spy()
    results = ma.signal_results("end", [t], kill_func=kill)
    assert kill.calls == []                      # nothing sent
    assert results[0].kind == "guard"
    msg = ma.render_signal("end", results)
    assert msg == ("Not sent — PID 100 exited and the PID was reused "
                   "(starttime guard)")


def test_guard_gone_does_not_send():
    stat_reader, status_reader = _readers({100: "gone"}, {100: "gone"})
    t = ma.probe((100, 555), getuid_func=lambda: MY_UID,
                 stat_reader=stat_reader, status_reader=status_reader)
    assert t.status == ma.GONE
    kill = Spy()
    results = ma.signal_results("kill", [t], kill_func=kill)
    assert kill.calls == []
    assert "has exited" in ma.render_signal("kill", results)


def test_guard_unreadable_falls_back_and_sends():
    # A permission-locked stat cannot be compared -> snapshot fallback, still
    # acts on the key we hold (actions-permissions.md fresh-read fallback).
    locked = {"pid": 100, "locked": True, "comm": None, "state": None,
              "starttime": None, "nice": None}
    t = _probe(100, 555, locked, _status(100))
    assert t.status == ma.UNREADABLE
    kill = Spy()
    ma.signal_results("end", [t], kill_func=kill)
    assert kill.calls == [(100, signal.SIGTERM)]


# ---------------------------------------------------------------------------
# Signal send + wording.
# ---------------------------------------------------------------------------

def test_send_calls_correct_signal_and_wording():
    t = _target(pid=4182, name="firefox")
    kill = Spy()
    results = ma.signal_results("end", [t], kill_func=kill)
    assert kill.calls == [(4182, signal.SIGTERM)]
    assert ma.render_signal("end", results) == "SIGTERM sent to firefox (4182)"


def test_kill_maps_to_sigkill():
    t = _target(pid=4182, name="firefox")
    kill = Spy()
    ma.signal_results("kill", [t], kill_func=kill)
    assert kill.calls == [(4182, signal.SIGKILL)]


def test_custom_signal_uses_supplied_number():
    t = _target(pid=4182, name="firefox")
    kill = Spy()
    results = ma.signal_results("signal", [t], signum=signal.SIGUSR1,
                                kill_func=kill)
    assert kill.calls == [(4182, signal.SIGUSR1)]
    assert ma.render_signal("signal", results, signum=signal.SIGUSR1) == (
        "SIGUSR1 sent to firefox (4182)")


def test_eperm_single_reports_exact_errno_text():
    t = _target(pid=1, name="systemd", uid=0, own=False)
    kill = Spy(raises=OSError(errno.EPERM, "Operation not permitted"))
    results = ma.signal_results("kill", [t], kill_func=kill)
    assert results[0].kind == "failed"
    assert ma.render_signal("kill", results) == (
        "Failed to kill systemd (1): Operation not permitted")


# ---------------------------------------------------------------------------
# Confirmation matrix.
# ---------------------------------------------------------------------------

class FakeSettings:
    def __init__(self, **kw):
        self._d = kw

    def get(self, key, default=None):
        return self._d.get(key, default)


def test_kill_always_confirms():
    assert ma.needs_confirm("kill", [_target(own=True)]) is True
    assert ma.needs_confirm("kill", [_target(own=False)]) is True


def test_end_confirms_by_default_for_own():
    assert ma.needs_confirm("end", [_target(own=True)]) is True


def test_end_opt_out_silences_own_only():
    settings = FakeSettings(end_confirm_own=False)
    assert ma.needs_confirm("end", [_target(own=True)], settings) is False
    # A foreign target still confirms even with the opt-out set.
    both = [_target(own=True), _target(pid=1, own=False)]
    assert ma.needs_confirm("end", both, settings) is True


def test_stop_continue_do_not_confirm():
    assert ma.needs_confirm("stop", [_target()]) is False
    assert ma.needs_confirm("continue", [_target()]) is False


# ---------------------------------------------------------------------------
# Renice permission table (own/others x increase/decrease).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("own,current,value,allowed", [
    (True, 0, 5, True),     # own + increase  -> allowed
    (True, 0, -5, False),   # own + decrease  -> EPERM
    (True, 5, 5, False),    # own + no change (not an increase) -> EPERM
    (True, 5, 2, False),    # own + decrease back toward a former value -> EPERM
    (False, 0, 5, False),   # others + increase -> EPERM
    (False, 0, -5, False),  # others + decrease -> EPERM
])
def test_renice_permission_table(own, current, value, allowed):
    t = _target(own=own, nice=current)
    got, _reason = ma.renice_permission(t, value)
    assert got is allowed


def test_renice_success():
    t = _target(pid=4182, name="firefox", own=True, nice=0)
    spy = Spy()
    result = ma.renice(t, 10, setpriority_func=spy)
    import os
    assert spy.calls == [(os.PRIO_PROCESS, 4182, 10)]
    assert ma.render_renice(result, 10) == "Niceness of firefox (4182) set to 10"


def test_renice_permission_denied_makes_no_syscall():
    t = _target(pid=1, name="systemd", own=False, nice=0)
    spy = Spy()
    result = ma.renice(t, 10, setpriority_func=spy)
    assert spy.calls == []                       # pre-checked, never attempted
    assert result.kind == "failed"
    assert result.err == errno.EPERM


def test_renice_syscall_eperm_reports_errno():
    t = _target(pid=4182, name="firefox", own=True, nice=0)
    spy = Spy(raises=OSError(errno.EPERM, "Operation not permitted"))
    result = ma.renice(t, 10, setpriority_func=spy)
    assert ma.render_renice(result, 10) == (
        "Failed to renice firefox (4182): Operation not permitted")


# ---------------------------------------------------------------------------
# Affinity.
# ---------------------------------------------------------------------------

def test_affinity_own_sets_mask():
    t = _target(pid=4182, name="firefox", own=True)
    spy = Spy()
    result = ma.set_affinity(t, [0, 1], setaffinity_func=spy)
    assert spy.calls == [(4182, {0, 1})]
    assert ma.render_affinity(result, [0, 1]) == (
        "CPU affinity of firefox (4182) set to {0, 1}")


def test_affinity_others_denied_without_syscall():
    t = _target(pid=1, name="systemd", own=False)
    spy = Spy()
    result = ma.set_affinity(t, [0], setaffinity_func=spy)
    assert spy.calls == []
    assert result.kind == "failed"
    assert result.err == errno.EPERM


def test_affinity_others_disabled_in_menu():
    t = _target(own=False)
    enabled, reason = ma.feasibility("affinity", t)
    assert enabled is False
    assert "root" in reason


# ---------------------------------------------------------------------------
# Bulk summary.
# ---------------------------------------------------------------------------

def test_bulk_summary_counts_and_names_failures():
    ok_a = _target(pid=4182, name="firefox", own=True)
    ok_b = _target(pid=4183, name="bash", own=True)
    root = _target(pid=1, name="systemd", uid=0, own=False)

    def kill(pid, signum):
        if pid == 1:
            raise OSError(errno.EPERM, "Operation not permitted")

    results = ma.signal_results("kill", [ok_a, ok_b, root], kill_func=kill)
    assert ma.render_signal("kill", results) == (
        "SIGKILL sent to 2 processes · 1 failed (EPERM): systemd (1)")


def test_bulk_all_sent():
    a = _target(pid=10, name="a")
    b = _target(pid=11, name="b")
    kill = Spy()
    results = ma.signal_results("end", [a, b], kill_func=kill)
    assert ma.render_signal("end", results) == "SIGTERM sent to 2 processes"


# ---------------------------------------------------------------------------
# Zombie no-effect path.
# ---------------------------------------------------------------------------

def test_zombie_signal_marked_no_effect_not_sent():
    z = _target(pid=777, name="defunct-child", state="Z")
    kill = Spy()
    results = ma.signal_results("end", [z], kill_func=kill)
    assert kill.calls == []                      # never sent
    assert results[0].kind == "no_effect"
    assert ma.render_signal("end", results) == (
        "No SIGTERM sent to defunct-child (777) — no effect on a defunct process")


def test_zombie_menu_item_disabled_with_reason():
    z = _target(state="Z")
    enabled, reason = ma.feasibility("end", z)
    assert enabled is False
    assert reason == "no effect on a defunct process"


# ---------------------------------------------------------------------------
# has_failure -> warn-icon driver for the status strip.
# ---------------------------------------------------------------------------

def test_has_failure_flags_non_sent():
    assert ma.has_failure([ma.Result(1, "a", "sent")]) is False
    assert ma.has_failure([ma.Result(1, "a", "failed", err=errno.EPERM)]) is True
    assert ma.has_failure(ma.Result(1, "a", "guard", detail="x")) is True
