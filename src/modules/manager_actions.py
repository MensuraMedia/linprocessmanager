"""Actions & permissions — the only code in linprocman that mutates the system.

Signals, niceness, CPU affinity, and the safety rules around them: the
click-time PID-recycle guard, the confirmation matrix, the corrected renice
permission rule, the errno-to-status contract, and the "signal sent" (never
"ended") wording. Spec: docs/modules/actions-permissions.md (binding) — the
rules and the quoted status-line strings below are lifted verbatim from it.

UI-free by mandate (build-principles.md core-module rule): this module reads
the kernel only through ``procfs`` readers, mutates it only through injectable
``os`` primitives (``os.kill`` / ``os.setpriority`` / ``os.sched_setaffinity``),
and imports no toolkit — so every guard, permission verdict, and message is
exercised headlessly in tests. The page layer owns the dialogs, the menu, and
the status strip; it hands us ``(pid, starttime)`` keys and renders what we
return.

No elevation, ever (v1): no pkexec/sudo path exists here. EPERM is reported,
never worked around.
"""

import errno as _errno
import os
import signal
from dataclasses import dataclass

try:  # app layout: python3 src/main.py (src on sys.path)
    from modules import procfs
except ImportError:  # standalone/test layout (src/modules on sys.path)
    import procfs

PROC = procfs.PROC

# Signal-sending actions -> signal number. "signal" (the custom-signal picker)
# carries its number explicitly and is not in this map.
SIGNAL_ACTIONS = {
    "end": signal.SIGTERM,
    "kill": signal.SIGKILL,
    "stop": signal.SIGSTOP,
    "continue": signal.SIGCONT,
    "hangup": signal.SIGHUP,
}

# Failure-message verb per action: "Failed to <verb> <name> (<pid>): <errno>".
_FAIL_VERB = {
    "end": "end", "kill": "kill", "stop": "stop",
    "continue": "continue", "hangup": "hang up", "signal": "signal",
}

# Probe outcomes (the click-time guard verdict).
OK = "ok"
GONE = "gone"            # /proc/<pid> vanished — the process exited
REUSED = "reused"        # starttime mismatch — the PID was recycled
UNREADABLE = "unreadable"  # fresh read failed — fall back to the snapshot key


@dataclass
class Target:
    """A guarded action target: the fresh-read result for one selection key."""

    pid: int
    key_starttime: object   # the (pid, starttime) key's starttime (may be None/0)
    name: str
    state: str
    uid: object
    nice: object
    own: bool
    status: str             # OK | GONE | REUSED | UNREADABLE

    @property
    def defunct(self):
        return self.state == "Z"


@dataclass
class Result:
    """The outcome of one mutation, rendered by the status strip."""

    pid: int
    name: str
    kind: str               # sent | failed | guard | no_effect
    err: object = None      # errno int (failures only)
    detail: str = ""        # guard text / annotation


# ---------------------------------------------------------------------------
# Click-time guard: fresh /proc/<pid>/stat read + starttime compare.
# ---------------------------------------------------------------------------

def probe(key, *, proc_root=PROC, getuid_func=os.getuid,
          stat_reader=None, status_reader=None):
    """Read ``/proc/<pid>/stat`` fresh and classify the key against the kernel.

    ``key`` is a ``(pid, starttime)`` selection identity. The starttime is
    compared to the live value: a mismatch means the PID was recycled between
    the last snapshot and this click, and nothing must be sent. A fresh read
    that fails (permission-locked or truncated) degrades to ``UNREADABLE`` —
    the snapshot key is then the only identity we have (fallback), so the
    caller may still act. A vanished PID is ``GONE``.
    """
    stat_reader = stat_reader or procfs.parse_stat
    status_reader = status_reader or procfs.parse_status
    pid, key_start = key

    name = "PID %d" % pid
    state = "?"
    nice = None
    uid = None
    status = OK

    try:
        st = stat_reader(pid, proc_root=proc_root)
    except FileNotFoundError:
        st = None
        status = GONE

    if status != GONE:
        if st is None or st.get("locked"):
            # Truncated read or permission-locked stat: cannot compare
            # starttime -> snapshot fallback (act on the key we already hold).
            status = UNREADABLE
        else:
            if st.get("comm"):
                name = st["comm"]
            state = st.get("state") or "?"
            nice = st.get("nice")
            fresh_start = st.get("starttime")
            if (key_start not in (None, 0) and fresh_start is not None
                    and fresh_start != key_start):
                status = REUSED

    # Ownership + a non-truncated name from status (best effort; a locked or
    # missing status leaves uid None -> treated as another user's process).
    try:
        stt = status_reader(pid, proc_root=proc_root)
    except FileNotFoundError:
        stt = None
    if stt and not stt.get("locked"):
        uid = stt.get("uid")
        if stt.get("name"):
            name = stt["name"]

    own = uid is not None and uid == getuid_func()
    return Target(pid=pid, key_starttime=key_start, name=name, state=state,
                  uid=uid, nice=nice, own=own, status=status)


# ---------------------------------------------------------------------------
# Menu feasibility + confirmation matrix (pure over Target lists).
# ---------------------------------------------------------------------------

def feasibility(action, target):
    """``(enabled, reason)`` for one menu item against one target.

    Disabled-with-reason, never hidden (process-preview.md §3): zombies take no
    signal, another user's process cannot be reniced or pinned without root.
    """
    if target.status == GONE:
        return (False, "the process has exited")
    if action in SIGNAL_ACTIONS or action == "signal":
        if target.defunct:
            return (False, "no effect on a defunct process")
        return (True, None)
    if action == "renice":
        if not target.own:
            return (False, "changing another user's priority needs root")
        return (True, None)
    if action == "affinity":
        if not target.own:
            return (False, "setting another user's CPU affinity needs root")
        if target.defunct:
            return (False, "no effect on a defunct process")
        return (True, None)
    return (True, None)


def feasibility_many(action, targets):
    """Enable a menu item if it is feasible for ANY selected target; otherwise
    report the reason of the first infeasible one."""
    reason = None
    for target in targets:
        enabled, why = feasibility(action, target)
        if enabled:
            return (True, None)
        if reason is None:
            reason = why
    return (False, reason)


def needs_confirm(action, targets, settings=None):
    """Confirmation matrix (actions-permissions.md).

    Kill always confirms. End confirms for every target by default; the
    ``end_confirm_own`` setting (default true) may opt out of confirming when
    *all* targets are the user's own — a foreign process always confirms. Stop
    / continue / hangup / custom-signal do not force a confirm.
    """
    if action == "kill":
        return True
    if action == "end":
        if any(not t.own for t in targets):
            return True
        opt_in = True if settings is None else bool(
            settings.get("end_confirm_own", True))
        return opt_in
    return False


# ---------------------------------------------------------------------------
# Renice permission (corrected rule r039).
# ---------------------------------------------------------------------------

def renice_permission(target, value):
    """``(allowed, reason)`` for reniceing ``target`` to ``value``.

    Unprivileged users may only *increase* niceness of their *own* processes.
    Any decrease (raising priority), including back to a former value, and any
    change to another user's process, needs CAP_SYS_NICE and raises EPERM.
    """
    if not target.own:
        return (False, "Changing another user's process priority requires "
                       "CAP_SYS_NICE (root).")
    current = target.nice
    if current is not None and value <= current:
        return (False, "Lowering niceness (raising priority) requires "
                       "CAP_SYS_NICE (root); an unprivileged user may only "
                       "increase niceness.")
    return (True, "")


# ---------------------------------------------------------------------------
# Mutations. Each returns a Result; the strip wording is built by render_*.
# ---------------------------------------------------------------------------

def signal_results(action, targets, signum=None, *, kill_func=None):
    """Send ``signum`` (or the action's default) to each target, guard-first."""
    kill_func = kill_func or os.kill
    if signum is None:
        signum = SIGNAL_ACTIONS[action]
    return [_send_one(t, signum, kill_func) for t in targets]


def _send_one(target, signum, kill_func):
    if target.status == GONE:
        return Result(target.pid, target.name, "guard",
                      detail=_gone_detail(target))
    if target.status == REUSED:
        return Result(target.pid, target.name, "guard",
                      detail=_reused_detail(target))
    if target.defunct:
        return Result(target.pid, target.name, "no_effect")
    try:
        kill_func(target.pid, signum)
    except OSError as exc:
        return Result(target.pid, target.name, "failed", err=exc.errno)
    return Result(target.pid, target.name, "sent")


def renice(target, value, *, setpriority_func=None):
    """Renice ``target`` to absolute niceness ``value`` (guard + permission)."""
    setpriority_func = setpriority_func or os.setpriority
    guard = _guard_result(target)
    if guard is not None:
        return guard
    allowed, _reason = renice_permission(target, value)
    if not allowed:
        # Pre-checked EPERM: the dialog stated the rule; no syscall attempted.
        return Result(target.pid, target.name, "failed", err=_errno.EPERM)
    try:
        setpriority_func(os.PRIO_PROCESS, target.pid, value)
    except OSError as exc:
        return Result(target.pid, target.name, "failed", err=exc.errno)
    return Result(target.pid, target.name, "sent")


def set_affinity(target, cpus, *, setaffinity_func=None):
    """Pin ``target`` to the CPU set ``cpus`` (own processes only)."""
    setaffinity_func = setaffinity_func or os.sched_setaffinity
    guard = _guard_result(target)
    if guard is not None:
        return guard
    if not target.own:
        return Result(target.pid, target.name, "failed", err=_errno.EPERM)
    if target.defunct:
        return Result(target.pid, target.name, "no_effect")
    try:
        setaffinity_func(target.pid, set(cpus))
    except OSError as exc:
        return Result(target.pid, target.name, "failed", err=exc.errno)
    return Result(target.pid, target.name, "sent")


def _guard_result(target):
    if target.status == GONE:
        return Result(target.pid, target.name, "guard",
                      detail=_gone_detail(target))
    if target.status == REUSED:
        return Result(target.pid, target.name, "guard",
                      detail=_reused_detail(target))
    return None


# ---------------------------------------------------------------------------
# Status-line rendering (wording matters — actions-permissions.md §Status).
# ---------------------------------------------------------------------------

def signame(signum):
    try:
        return signal.Signals(signum).name
    except ValueError:
        return "signal %d" % signum


def _pidname(name, pid):
    return "%s (%d)" % (name, pid)


def _gone_detail(target):
    return "Not sent — PID %d has exited (starttime guard)" % target.pid


def _reused_detail(target):
    return ("Not sent — PID %d exited and the PID was reused (starttime guard)"
            % target.pid)


def _strerror(err):
    if err is None:
        return "error"
    try:
        return os.strerror(err)
    except (ValueError, OverflowError):
        return "error"


def _errno_code(results):
    codes = {r.err for r in results}
    if len(codes) == 1:
        (code,) = codes
        return _errno.errorcode.get(code, "error")
    return "errors"


def has_failure(results):
    """True if any result needs a warn icon (failed / guard / no_effect)."""
    if isinstance(results, Result):
        results = [results]
    return any(r.kind != "sent" for r in results)


def render_signal(action, results, signum=None):
    """Render a signal batch: one line for a single target, a count-plus-names
    summary for a bulk selection."""
    if signum is None:
        signum = SIGNAL_ACTIONS.get(action)
    sn = signame(signum)
    verb = _FAIL_VERB.get(action, "signal")
    if len(results) == 1:
        return _render_signal_single(results[0], sn, verb)
    return _render_signal_bulk(results, sn, verb)


def _render_signal_single(r, sn, verb):
    who = _pidname(r.name, r.pid)
    if r.kind == "sent":
        return "%s sent to %s" % (sn, who)
    if r.kind == "failed":
        return "Failed to %s %s: %s" % (verb, who, _strerror(r.err))
    if r.kind == "no_effect":
        return "No %s sent to %s — no effect on a defunct process" % (sn, who)
    return r.detail  # guard


def _render_signal_bulk(results, sn, verb):
    sent = [r for r in results if r.kind == "sent"]
    failed = [r for r in results if r.kind == "failed"]
    guarded = [r for r in results if r.kind == "guard"]
    defunct = [r for r in results if r.kind == "no_effect"]

    noun = "process" if len(sent) == 1 else "processes"
    segments = ["%s sent to %d %s" % (sn, len(sent), noun)]
    if failed:
        names = ", ".join(_pidname(r.name, r.pid) for r in failed)
        segments.append("%d failed (%s): %s" % (
            len(failed), _errno_code(failed), names))
    if guarded:
        names = ", ".join(_pidname(r.name, r.pid) for r in guarded)
        segments.append("%d not sent (PID reused/exited): %s" % (
            len(guarded), names))
    if defunct:
        names = ", ".join(_pidname(r.name, r.pid) for r in defunct)
        segments.append("%d skipped (defunct): %s" % (len(defunct), names))
    return " · ".join(segments)


def command_line(key, *, proc_root=PROC):
    """Full command line for a selection key, joined with spaces.

    The kernel read lives here (never in the page — boundary law): the page
    hands us the key and shows what we return. Empty for kernel threads,
    zombies, or a restricted ``cmdline`` (procfs collapses those to None/[]).
    """
    argv = procfs.read_cmdline(key[0], proc_root=proc_root)
    return " ".join(argv) if argv else ""


def exe_dir(key, *, proc_root=PROC):
    """Directory of the process's executable (readlink /proc/<pid>/exe).

    None when the process is gone, the link is unreadable (kernel thread,
    other-user under Yama), or the exe vanished — the page renders "—".
    Kernel read stays in the actions layer (boundary law).
    """
    target = probe(key, proc_root=proc_root)
    if target is None or target.status != "OK":
        return None
    try:
        exe = os.readlink("%s/%d/exe" % (proc_root, target.pid))
    except OSError:
        return None
    return os.path.dirname(exe) or "/"


def dependencies(key, *, proc_root=PROC, cap=12):
    """Linked-library basenames for a selection key (deduped, capped) + total.

    The ``/proc/<pid>/maps`` read stays in this core layer (boundary law — the
    preview pane hands us the key and renders what we return), mirroring
    :func:`command_line`. Returns ``([], 0)`` when restricted/absent.
    """
    return procfs.read_maps_basenames(key[0], proc_root=proc_root, cap=cap)


def _fmt_cpus(cpus):
    ordered = sorted(cpus)
    return "{%s}" % ", ".join(str(c) for c in ordered) if ordered else "{}"


def render_renice(result, value):
    who = _pidname(result.name, result.pid)
    if result.kind == "sent":
        return "Niceness of %s set to %d" % (who, value)
    if result.kind == "failed":
        return "Failed to renice %s: %s" % (who, _strerror(result.err))
    return result.detail  # guard


def render_affinity(result, cpus):
    who = _pidname(result.name, result.pid)
    if result.kind == "sent":
        return "CPU affinity of %s set to %s" % (who, _fmt_cpus(cpus))
    if result.kind == "failed":
        return "Failed to set CPU affinity of %s: %s" % (
            who, _strerror(result.err))
    if result.kind == "no_effect":
        return "CPU affinity of %s unchanged — no effect on a defunct process" % who
    return result.detail  # guard


# ---------------------------------------------------------------------------
# Confirmation-dialog copy (the page shows these before mutating).
# ---------------------------------------------------------------------------

def _names_block(targets):
    return "\n".join("• %s" % _pidname(t.name, t.pid) for t in targets)


def confirm_message(action, targets):
    n = len(targets)
    if action == "kill":
        if n == 1:
            return ("Kill %s?\n\nSIGKILL cannot be caught or ignored — the "
                    "process is terminated immediately and unsaved work is "
                    "lost." % _pidname(targets[0].name, targets[0].pid))
        return ("Kill %d processes?\n\nSIGKILL cannot be caught — unsaved work "
                "is lost.\n\n%s" % (n, _names_block(targets)))
    if action == "end":
        if n == 1:
            return ("End %s?\n\nSIGTERM asks the process to exit; it may run "
                    "cleanup first." % _pidname(targets[0].name, targets[0].pid))
        return ("End %d processes?\n\nSIGTERM asks each to exit.\n\n%s"
                % (n, _names_block(targets)))
    return "Proceed?"


def renice_message(target, value):
    """Dialog copy for renice — states the permission rule before attempting."""
    head = "Set niceness of %s to %d?" % (
        _pidname(target.name, target.pid), value)
    allowed, reason = renice_permission(target, value)
    if allowed:
        return head + ("\n\nA higher niceness means lower scheduling priority. "
                       "This cannot be undone without root (niceness can only "
                       "be increased).")
    return head + "\n\n" + reason + "\n\nThe attempt will fail with EPERM."


def affinity_message(target, cpus):
    head = "Pin %s to CPUs %s?" % (
        _pidname(target.name, target.pid), _fmt_cpus(cpus))
    enabled, reason = feasibility("affinity", target)
    if enabled:
        return head + "\n\nThe process will run only on the selected CPUs."
    return head + "\n\n" + (reason or "") + "\n\nThe attempt will fail."


# ---------------------------------------------------------------------------
# Group (subtree) termination — r074. The tree is collected from the newest
# snapshot BEFORE any signal flies (once the parent dies, children reparent
# and ppid edges go stale), leaves-first; every member is guard-checked at
# send time, liveness-verified afterwards, and survivors past the grace
# window are escalated SIGTERM -> SIGKILL. "Ensure killed accordingly" is
# the verification loop, not the signal itself.
# ---------------------------------------------------------------------------

def probe_many(keys, probe_func=None):
    """Fresh guarded probe for each selection key."""
    probe_func = probe_func or probe
    return [probe_func(key) for key in keys]


def descendant_keys(root_key, procs):
    """Descendant keys of ``root_key`` in the snapshot ``procs`` mapping,
    children-first (leaves before parents), root NOT included. Pure BFS
    over ppid edges; guards against cycles via seen-pid set."""
    by_ppid = {}
    for key, rec in procs.items():
        ppid = rec.get("ppid")
        if ppid is not None:
            by_ppid.setdefault(ppid, []).append(key)
    out, queue, seen = [], [root_key[0]], {root_key[0]}
    while queue:
        pid = queue.pop(0)
        for key in sorted(by_ppid.get(pid, [])):
            if key[0] in seen:
                continue
            seen.add(key[0])
            out.append(key)
            queue.append(key[0])
    return out


def _alive(target, stat_reader):
    """True when the SAME process (pid + starttime) still exists."""
    try:
        st = stat_reader(target.pid)
    except FileNotFoundError:
        return False
    except PermissionError:
        return True  # exists, but we cannot compare — treat as alive
    if st is None:
        return False
    return st.get("starttime") == target.key_starttime


def verify_gone(targets, stat_reader, poll, attempts=6):
    """Poll until every target is gone. Returns (gone, survivors)."""
    gone, survivors = [], list(targets)
    for _ in range(max(1, attempts)):
        poll()
        still = []
        gone = []
        for t in survivors:
            if _alive(t, stat_reader):
                still.append(t)
            else:
                gone.append(t)
        survivors = still
        if not survivors:
            break
    return gone, survivors


def escalate(targets, kill_func=None):
    """SIGKILL survivors (r074 escalation step). Returns Result list."""
    kill_func = kill_func or os.kill
    results = []
    for t in targets:
        try:
            kill_func(t.pid, 9)
            results.append(Result(t.pid, t.name, "sent",
                                  detail="escalated to SIGKILL"))
        except OSError as exc:
            results.append(Result(t.pid, t.name, "failed", err=exc.errno))
    return results


def group_overview(root_key):
    """Fresh tree census for the confirm dialog: (count, names)."""
    procs = procfs.snapshot_procs()
    keys = [root_key] + descendant_keys(root_key, procs)
    names = sorted({procs[k].get("comm", "?") for k in keys})
    return len(keys), names


def group_terminate(action, root_key, root_name, procs, *, signum,
                    grace_attempts=6, poll=None, probe_func=None,
                    kill_func=None, stat_reader=None, live_reader=None):
    """Collect the subtree of ``root_key`` and terminate it.

    1. Collect descendants (children-first) + root from the snapshot.
    2. Probe each member fresh (recycle guard).
    3. Signal all probeable members with ``signum``.
    4. Verify liveness; escalate survivors to SIGKILL.
    5. Verify again.

    ``poll`` (called between verification attempts) is injected so tests run
    without sleeping. Returns a dict summary for the status line.
    """
    poll = poll or (lambda: None)
    reader = probe_func or probe  # fresh guarded read per member
    live_reader = live_reader or procfs.parse_stat
    if procs is None:
        # fresh collection at action time — a cached snapshot can predate the
        # tree's newest members (r074 lesson: children born after the last
        # tick would be missed)
        procs = procfs.snapshot_procs()
    keys = [root_key] + descendant_keys(root_key, procs)
    targets = [reader(key) for key in keys]  # plain positional call: test
    # fakes and procfs-style readers both work (kwargs are probe-specific)
    results = signal_results(action, targets, signum=signum,
                             kill_func=kill_func)
    sent = [t for t, r in zip(targets, results) if r.kind == "sent"]
    gone, survivors = verify_gone(sent, live_reader, poll, grace_attempts)
    escalated = []
    if survivors:
        escalated = escalate(survivors, kill_func=kill_func)
        gone2, survivors = verify_gone(survivors, live_reader, poll,
                                       grace_attempts)
        gone += gone2
    return {
        "action": action,
        "root": root_name,
        "total": len(keys),
        "results": results + escalated,
        "terminated": len(gone),
        "escalated": len(escalated),
        "survivors": survivors,
    }


def group_summary_text(summary):
    """Status-line contract for group actions."""
    verb = "SIGKILL" if summary["action"] in ("kill", "kill-group") else "SIGTERM"
    base = ("Tree of %s: %d/%d terminated (%s)"
            % (summary["root"], summary["terminated"], summary["total"], verb))
    if summary["escalated"]:
        base += " · %d escalated to SIGKILL" % summary["escalated"]
    if summary["survivors"]:
        base += " · %d SURVIVED (restricted)" % len(summary["survivors"])
    return base
