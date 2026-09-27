"""Group (subtree) termination — r074.

Pure tests for descendant collection, verify/escalate sequencing, and the
summary contract. Live kernel runs use tests/live_group_actions.py.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "modules"))

import manager_actions as ma
from manager_actions import Target, OK, REUSED


def rec(pid, ppid, name="p", starttime=None):
    if starttime is None:
        starttime = 100000 + pid
    return {"pid": pid, "ppid": ppid, "starttime": starttime, "name": name}


def procs(*records):
    return {(r["pid"], r["starttime"]): r for r in records}


def fake_probe(live, names=None):
    """probe_func replacement: builds Targets from a live-set dict
    pid -> starttime, classifying REUSED when the key's starttime differs.
    ``live`` is mutated by tests to model process exit (pop)."""
    names = names or {}

    def _probe(key, *a, **k):
        pid, key_start = key
        status = OK if live.get(pid) == key_start else REUSED
        return Target(pid=pid, key_starttime=key_start,
                      name=names.get(pid, "p%d" % pid), state="S",
                      uid=1000, nice=0, own=True, status=status)
    return _probe


class Test:
    def test_descendant_keys_children_first(self):
        snapshot = procs(
            rec(1, 0, "systemd"), rec(2, 1, "sh"), rec(3, 2, "child"),
            rec(4, 2, "child2"), rec(9, 3, "grandchild"), rec(5, 1, "other"))
        keys = ma.descendant_keys((2, 1002), snapshot)
        pids = [k[0] for k in keys]
        assert 3 in pids and 4 in pids and 9 in pids
        assert 1 not in pids and 2 not in pids
        # BFS level order: direct children (3, 4) before the grandchild (9)
        assert pids.index(3) < pids.index(9) and pids.index(4) < pids.index(9)

    def test_descendant_cycles_guarded(self):
        snapshot = procs(rec(2, 1), rec(3, 2), rec(2, 3))  # 2<->3 cycle
        keys = ma.descendant_keys((2, 1002), snapshot)
        assert len(keys) == 1  # terminates, no infinite loop

    def test_group_terminate_sigterm_then_escalate(self):
        # victims ignore SIGTERM -> must be escalated to SIGKILL
        starttimes = {10: 100010, 11: 100011, 12: 100012}
        live = dict(starttimes)          # pid -> starttime (SIGKILL removes)
        snapshot = procs(rec(10, 11, "root"), rec(11, 10, "kid"),
                         rec(12, 10, "kid2"))
        killed = []
        probe = fake_probe(live)

        def live_reader(pid):
            if pid in live:
                return {"starttime": live[pid]}
            raise FileNotFoundError(pid)

        def kill_func(pid, sig):
            killed.append((pid, sig))
            if sig == 9:
                live.pop(pid, None)

        polls = {"n": 0}

        def poll():
            polls["n"] += 1

        summary = ma.group_terminate(
            "end-group", (10, 100010), "root", snapshot, signum=15,
            grace_attempts=3, poll=poll, kill_func=kill_func,
            probe_func=probe, live_reader=live_reader)

        # all three members signalled SIGTERM first (verification polling
        # retries the TERM on survivors before escalating — by design)
        terms = [(p, s) for p, s in killed if s == 15]
        assert len(terms) >= 3
        # then escalated to SIGKILL
        assert any(s == 9 for _, s in killed)
        assert summary["escalated"] >= 1
        assert summary["terminated"] == 3
        assert summary["survivors"] == []

    def test_group_terminate_all_exit_on_sigterm(self):
        starttimes = {20: 100020, 21: 100021}
        live = dict(starttimes)
        snapshot = procs(rec(20, 21, "root"), rec(21, 20, "kid"))
        probe = fake_probe(live)

        def live_reader(pid):
            if pid in live:
                return {"starttime": live[pid]}
            raise FileNotFoundError(pid)

        def kill_func(pid, sig):
            live.pop(pid, None)

        summary = ma.group_terminate(
            "end-group", (20, 100020), "root", snapshot, signum=15,
            grace_attempts=4, poll=lambda: None, kill_func=kill_func,
            probe_func=probe, live_reader=live_reader)
        assert summary["terminated"] == 2
        assert summary["escalated"] == 0

    def test_summary_text_contract(self):
        text = ma.group_summary_text({
            "action": "kill-group", "root": "firefox", "total": 5,
            "terminated": 5, "escalated": 2, "survivors": []})
        assert "firefox" in text and "SIGKILL" in text and "5/5" in text
