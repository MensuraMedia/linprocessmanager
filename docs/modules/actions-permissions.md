# Module doc — actions & permissions (`src/modules/manager_actions.py`)

Part of the linprocman modular docs. Siblings: [procfs-data.md](procfs-data.md) ·
[sampling-pipeline.md](sampling-pipeline.md) · [process-table.md](process-table.md) ·
[resource-graphs.md](resource-graphs.md) · [persistence-config.md](persistence-config.md).
Overview: [../process-manager-concept.md](../process-manager-concept.md).

## Purpose

The only code that mutates the system: signals and niceness. Owns the
safety rules — identity guard, confirmation, error surfacing, and the
no-elevation policy.

## Interface

Consumes: selection `(pid, starttime)` from the table layer; latest snapshot
for the guard check.

Provides: `end(pid_key)` (SIGTERM), `kill(pid_key)` (SIGKILL), `stop`/`continue`
(SIGSTOP/SIGCONT), `hangup`, `signal(pid_key, num)`, `renice(pid_key, value)`
— all via `os.kill` / `os.setpriority`, all returning a result the status
line renders.

## Safety logic

- **PID-recycle guard:** before acting, verify the latest snapshot still has
  the same `(pid, starttime)`. Mismatch → "process ended, PID reused",
  nothing sent. Closes the milliseconds race for free.
- **Confirmation:** Kill (and End on processes not owned by the user) confirm
  with a dialog naming process and PID (mockup D). Custom signals go through
  the signal picker.
- **Failure contract:** `EPERM`/`EACCES` → status line with the exact errno
  text ("Operation not permitted"), warn icon. Never a silent no-op, never a
  dialog storm, never a crash.
- **No elevation, ever (v1):** no pkexec/sudo paths wired. A pkexec opt-in is
  a later operator decision that would change this doc first.
- **Zombies:** display as `name (defunct)`; details pane explains they exit
  when the parent reaps them — the UI says killing a zombie is meaningless
  instead of pretending.
- **Renice:** decreasing niceness below current needs privileges for
  processes you don't own — surfaced through the same failure contract.

## Status-line result examples

- ok: "Ended firefox (4182) with SIGTERM" (check icon, green)
- eperm: "Failed to kill systemd (1): Operation not permitted" (prohibit, red)
- guard: "Not sent — PID 3997 exited and the PID was reused (starttime guard)"

## Tests

Guard unit (mismatched starttime → no send, correct message), confirmation
trigger matrix, errno-string mapping.
