# Module doc — actions & permissions (`src/modules/manager_actions.py`)

Part of the linprocman modular docs. Siblings: [procfs-data.md](procfs-data.md) ·
[sampling-pipeline.md](sampling-pipeline.md) · [process-table.md](process-table.md) ·
[resource-graphs.md](resource-graphs.md) · [persistence-config.md](persistence-config.md) ·
[logs-journal.md](logs-journal.md) · [disks-filesystems.md](disks-filesystems.md) ·
[sysfs-data.md](sysfs-data.md). Overview: [../process-manager-concept.md](../process-manager-concept.md).

## Purpose

The only code that mutates the system: signals, niceness, CPU affinity.
Owns the safety rules — identity guard, confirmation, error surfacing, and
the no-elevation policy. All APIs take a **list** of `(pid, starttime)`
keys; multi-select bulk actions are the same code path with a summary
dialog.

## Interface

Consumes: selection key lists from the table layer; `procfs.parse_stat` for
the click-time guard (module rules allow it — actions may read the kernel
through procfs readers).

Provides: `end(keys)` (SIGTERM), `kill(keys)` (SIGKILL), `stop`/`continue`
(SIGSTOP/SIGCONT), `hangup`, `signal(keys, num)`, `renice(key, value)`,
`set_affinity(key, cpus)` — via `os.kill` / `os.setpriority` /
`os.sched_setaffinity`; each returns a result the status line renders.

## Safety logic

- **PID-recycle guard (fresh-read, r039):** at click time, read
  `/proc/<pid>/stat` directly and compare `starttime`. Mismatch → "process
  ended, PID reused", nothing sent. This **narrows** the race to
  microseconds (a check-then-kill window always exists); the snapshot alone
  (1–2 s stale) is only the fallback if the fresh read fails.
- **Confirmation:** Kill always confirms; **End confirms for all targets by
  default** (one misclick must not lose an editor's unsaved state) with a
  settings opt-out for own processes; bulk actions show one summary dialog
  naming the count and targets.
- **Failure contract:** `EPERM`/`EACCES` → status line with the exact errno
  text, warn icon. Never silent, never a dialog storm, never a crash.
- **No elevation, ever (v1):** no pkexec/sudo paths wired. An opt-in is a
  later operator decision that changes build-principles.md first.
- **Renice rule (corrected r039):** unprivileged users may only **increase**
  niceness of their **own** processes; any other change — other users'
  processes at all, or any decrease including back to a former value on
  your own — requires CAP_SYS_NICE and raises EPERM here. The dialog states
  this before the attempt.
- **Affinity:** `os.sched_setaffinity` is unprivileged for own processes —
  same dialog family as renice.
- **Zombies:** display as `name (defunct)`; details pane explains they exit
  when the parent reaps them; signals to a zombie are marked "no effect"
  rather than reported as success.

## Status-line contract (wording matters)

`os.kill` returning 0 means **delivered/permission-granted**, not ended — a
process may ignore or mask the signal (SIGTERM stays pending on a SIGSTOPped
target until SIGCONT). Wording:

- "SIGTERM sent to firefox (4182)" — never "Ended firefox"
- "Failed to kill systemd (1): Operation not permitted"
- "Not sent — PID 3997 exited and the PID was reused (starttime guard)"
- Bulk: "SIGTERM sent to 6 processes · 1 failed (EPERM): systemd (1)"

## Tests

Guard unit (fresh-read mismatch → no send), confirmation trigger matrix,
corrected renice permission table (own/others × increase/decrease), errno
mapping, bulk summary, zombie no-effect path, affinity EPERM path.
