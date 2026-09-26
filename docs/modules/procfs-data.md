# Module doc — procfs data layer (`src/modules/procfs.py`)

Part of the linprocman modular docs. Sibling docs: [sampling-pipeline.md](sampling-pipeline.md) ·
[process-table.md](process-table.md) · [actions-permissions.md](actions-permissions.md) ·
[resource-graphs.md](resource-graphs.md) · [persistence-config.md](persistence-config.md).
Overview: [../process-manager-concept.md](../process-manager-concept.md).

## Purpose

Pure readers that turn `/proc` bytes into plain dicts. No UI imports, no
state, no globals beyond a uid→name cache. Everything downstream consumes
these shapes, so this is the only file that knows kernel file layouts.

## Interface

Provides (all pure, all return plain dicts or raise `FileNotFoundError`):

| Function | Source |
|---|---|
| `parse_stat(pid)` | `/proc/<pid>/stat` — comm, state, ppid, utime, stime, starttime, nice, threads, rss |
| `parse_status(pid)` | `/proc/<pid>/status` — VmRSS/VmSize/shared, PPid cross-check |
| `parse_io(pid)` | `/proc/<pid>/io` — read/write bytes (may be unreadable → `None`, never error past caller) |
| `parse_smaps_rollup(pid)` | Pss/Rss/Pss_Anon — selected-process use only |
| `read_cmdline(pid)` | NUL-split argv list; `[]` for kernel threads — this is the kthread detector |
| `readlink_target(pid, what)` | exe/cwd; EACCES → `None` (caller shows `lock`) |
| `parse_cgroup(pid)` | v2 `0::…` line → unit name (last segment) |
| `system_stat()` | `/proc/stat` — per-CPU + total jiffies |
| `system_meminfo()` | MemTotal/Available/Cached/SwapTotal/SwapFree |
| `system_net_dev()` | per-iface rx/tx bytes |
| `system_pressure()` | `/proc/pressure/{cpu,memory,io}` — some avg10/60/300 (+full for mem/io) |

Consumes: nothing from the app; the kernel only.

## Parsing rules (the traps)

- **comm** is everything between the first `(` and the **last** `)` of the
  stat line — comm may contain spaces and parentheses. Fields after that are
  1-indexed post-comm: state 3, ppid 4, utime 14, stime 15, nice 19,
  threads 20, starttime 22, rss 24.
- Truncated/short stat lines → skip the PID this sample, never crash.
- `FileNotFoundError` at any read = the process exited; caller drops the row.
- `parse_io` returning `None` (permission) renders as "—" — the permission
  model for io varies by kernel config; degrade, don't error.

## Verified on this machine (2026-09-26, kernel 7.0.0-31-generic)

- `/proc/pressure/{cpu,memory,io}` present and readable.
- `smaps_rollup` readable for own processes.
- `CLK_TCK = 100` (`os.sysconf`) — read at startup regardless, never hard-coded.
- psutil 5.9.8 installed — dev-time cross-check only, not a runtime dep.

## Tests

Fixture files under `tests/fixtures/proc/` (same pattern as linfilesearch's
matcher tests): normal stat, comm-with-spaces, comm-with-parens, empty
cmdline (kthread), truncated stat, missing PID, restricted io, pressure
files. Every parser is tested against bytes, not the live kernel.
