# Module doc — procfs data layer (`src/modules/procfs.py`)

Part of the linprocman modular docs. Siblings: [sampling-pipeline.md](sampling-pipeline.md) ·
[process-table.md](process-table.md) · [actions-permissions.md](actions-permissions.md) ·
[resource-graphs.md](resource-graphs.md) · [persistence-config.md](persistence-config.md) ·
[logs-journal.md](logs-journal.md) · [disks-filesystems.md](disks-filesystems.md) ·
[sysfs-data.md](sysfs-data.md). Overview: [../process-manager-concept.md](../process-manager-concept.md).

## Purpose

Pure readers that turn `/proc` bytes into plain dicts. No UI imports, no
state, no globals beyond a uid→name cache. Together with `sysfs.py` this is
the only code that reads kernel interfaces, so this is the only file that
knows kernel file layouts.

## Interface

Provides (all pure, all return plain dicts; per-PID readers raise
`FileNotFoundError` for exit, return `None`-marked minimal data for
`PermissionError` — see Error taxonomy):

| Function | Source |
|---|---|
| `parse_stat(pid)` | `/proc/<pid>/stat` — comm, state, ppid, utime, stime, starttime, nice, threads, rss(pages) |
| `parse_status(pid)` | `/proc/<pid>/status` — VmRSS/VmSize/VmSwap, shared = RssFile+RssShmem, PPid cross-check |
| `parse_statm(pid)` | `/proc/<pid>/statm` — shared pages fallback (mem display source of truth is VmRSS) |
| `parse_io(pid)` | `/proc/<pid>/io` — read/write bytes (may be unreadable → `None`, never error past caller) |
| `parse_smaps_rollup(pid)` | Pss/Rss/Pss_Anon — selected-process use only |
| `read_cmdline(pid)` | NUL-split argv list; empty for kernel threads AND zombies — see detector rule |
| `readlink_target(pid, what)` | exe/cwd; EACCES → `None` (caller shows `lock`) |
| `parse_cgroup(pid)` | v2 `0::…` line → unit name with fallbacks |
| `system_stat()` | `/proc/stat` — per-CPU + total jiffies **and `btime`** (boot wall-clock) |
| `system_meminfo()` | MemTotal/Available/Cached/SwapTotal/SwapFree |
| `system_net_dev()` | per-iface rx/tx bytes, **`lo` excluded at parse time** |
| `system_diskstats()` | per-device reads/writes/io_ticks — feeds the Disks page |
| `system_pressure()` | `/proc/pressure/{cpu,memory,io}` — some avg10/60/300 (+full for mem/io) |

Consumes: nothing from the app; the kernel only.

## Parsing rules (the traps)

- **comm** is everything between the first `(` and the **last** `)` of the
  stat line — comm may contain spaces and parentheses. Fields after that are
  1-indexed post-comm: state 3, ppid 4, utime 14, stime 15, nice 19,
  threads 20, starttime 22, rss 24. **rss is in pages** — convert with
  `os.sysconf("SC_PAGE_SIZE")`; the table's memory column uses status VmRSS
  (bytes) as source of truth, stat rss as cross-check.
- **Kernel-thread detector:** empty cmdline **AND state ≠ Z**. A zombie's
  cmdline also reads empty; zombies are user processes in terminal state and
  must never be grouped under kthreadd.
- **Started-time formula:** wall = `btime + starttime / CLK_TCK` (btime from
  `system_stat`; CLK_TCK read at startup — verified 100 here, never
  hard-coded).
- **cgroup fallbacks:** `0::/` (kernel threads) → "—"; `init.scope` stays
  as-is; a sub-cgroup leaf that is not a unit → strip `.scope`/`.service`
  suffix, else raw path tail.
- Truncated/short stat lines → skip the PID this sample, never crash.

## Error taxonomy (r039 adversarial fix)

| Condition | Result | Row story |
|---|---|---|
| `FileNotFoundError` | process exited | row drops |
| `PermissionError` (hidepid ≥ 1, other users) | minimal locked row: pid + `lock` + "—" | row stays, visibly restricted — **distinct from exit** |
| `parse_io` unreadable | `None` | "—" cells, never an error |

No other exception may escape a reader.

## System math (owned here, fixture-tested)

- **Busy time per CPU** = user+nice+system+irq+softirq+iowait (+steal shown
  separately); guest is already inside user — never add it twice.
- **Memory used** = MemTotal − MemAvailable (not the naive free−buffers).
- **ncpu** = count of per-CPU lines in `/proc/stat` (self-consistent divisor
  for both CPU % normalizations — not `os.cpu_count()`, which disagrees with
  /proc when CPUs are offline).

## Verified on this machine (2026-09-26, kernel 7.0.0-31-generic)

- `/proc/pressure/{cpu,memory,io}` present and readable; `smaps_rollup`
  readable for own processes; CLK_TCK = 100; /proc mounted no-hidepid.
- psutil 5.9.8 installed — dev-time cross-check only, not a runtime dep.

## Tests

Fixture files under `tests/fixtures/proc/`: normal stat, comm-with-spaces,
comm-with-parens, empty cmdline (kthread), zombie with empty cmdline,
truncated stat, missing PID, **hidepid EACCES stat/status**, restricted io,
pressure files, diskstats, cpu-offline /proc/stat variant. Every parser is
tested against bytes, not the live kernel.
