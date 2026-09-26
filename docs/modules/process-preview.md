# Module doc — process preview pane & extended columns (`page_processes.py` + `manager_sampler.py` extensions)

Part of the linprocman modular docs. Siblings: [process-table.md](process-table.md) ·
[logs-journal.md](logs-journal.md) · [log-frequency.md](log-frequency.md) ·
[sampling-pipeline.md](sampling-pipeline.md) · [procfs-data.md](procfs-data.md) ·
[actions-permissions.md](actions-permissions.md) · [resource-graphs.md](resource-graphs.md) ·
[persistence-config.md](persistence-config.md). Overview: [../process-manager-concept.md](../process-manager-concept.md).

Operator-mandated (r053): industry-standard process-management depth —
selectable metric columns (I/O, reads/writes, and beyond), a right-side
**process preview** (name, parent chain, dependencies, resource
consumption, per-process/children/combined network traffic, owning app),
and a right-click context menu (Frequency, stop/pause/kill, and the full
action surface). Mockups: [mockup-i-extended-columns.html](../mockups/mockup-i-extended-columns.html)
(extended columns + chooser) and
[mockup-j-preview-context.html](../mockups/mockup-j-preview-context.html)
(preview pane + context menu). This document supersedes the phase-4
"details pane" bullet in the concept doc where they overlap.

## 1. Extended columns (column chooser, persistent)

Chooser popover (`sliders-horizontal`), grouped, click-to-toggle, choices
persist to settings.json (`columns.visible`/`widths`). **22 columns in
four groups** — every column has a typed store field and a no-data
representation ("—", never a guess):

| Group | Columns | Source (all /proc, no elevation) |
|---|---|---|
| Identity | Process (icon+name+unit badge), User, PID, State (R/S/D/Z color+badge), Command line, cgroup unit | existing readers |
| CPU | CPU %, CPU time, Nice, Threads, CPU affinity | stat/status (affinity: `sched_getaffinity`, own + readable others; else "—") |
| Memory | Memory (RSS), Memory % (bar), Swap, Shared, PSS (selected-only via rollup) | status/smaps_rollup |
| I/O | Disk read / write (totals), Disk read/s, Disk write/s, Disk % (bar, device util share), **IO priority** (`ioprio_get`; needs same-user or CAP_SYS_NICE → "—") | `/proc/<pid>/io` (r039 taxonomy) |
| Network | Net ↓ / ↑ per process (see §4) | fd→socket attribution (r053 design below) |
| Diagnostics | oom_score, Started, Parent PID | `/proc/<pid>/oom_score`, btime formula, stat |

Schema impact: the **frozen record gains optional keys** (`cpu_time,
mem_pct, io_read_rate, io_write_rate, io_prio, net_rx_rate, net_tx_rate,
oom_score, affinity` …) — every addition goes through the C-review
sign-off gate again before task dispatch (r048 precedent).

## 2. Process preview pane (right sidebar, fold-out)

290–330 px fold-out (r028 caret-toggle pattern), tracks selection, refreshes
every snapshot; `smaps_rollup` rides `request_rollup` for the selected row
only (already built). Sections, top to bottom (mockup J):

1. **Identity** — name, exe path, badges (unit, thread count, state).
2. **KPI row** — CPU %, RSS, Swap, Net ∑tree (four cells).
3. **Sparkline** — 60 s cpu% from the sampler's per-selected-pid history
   (ring owned by the preview, fed by snapshots; no new sampling).
4. **Ancestry — click to jump** — parent chain rendered
   root→selected from PPid edges (data the table already has), each
   ancestor clickable to select it; children listed under the selected
   process with their CPU%/mem.
5. **Resource consumption** — CPU time/started, RSS/shared/virt, PSS,
   disk totals + rates, net self+tree, nice, oom_score.
6. **Networking — attribution** — self / each child / **combined tree**
   rows (see §4); restricted rows show `lock` + "—".
7. **Dependencies** — linked libraries (`/proc/<pid>/maps` dedup'd by
   basename, capped at ~12 + count), socket families in use (from the
   attribution pass), netns identity, cgroup unit.
8. **Action row** — End, Kill, Stop, Renice, Journal (Phase 3 wires the
   handlers; Phase 4 ships the pane).

## 3. Right-click context menu on process rows

Items (mockup J; all act on `(pid, starttime)`, destructive ones confirm
per actions-permissions.md):

Show in tree · Copy PID/command line — *—* Stop (SIGSTOP) · Continue
(SIGCONT) · End (SIGTERM) · Kill (SIGKILL) · Send signal… (picker) — *—*
Change priority (renice)… · Set CPU affinity… — *—* **Frequency…**
(per-process resource-pattern view — reuses the log-frequency charting
engine over the sampler's history; spec in log-frequency.md §Frequency,
process-side extension noted there) · View journal for unit… (existing
r042 item) · Open executable location.

Menu-key parity. Items are disabled (grayed, with reason on hover) rather
than hidden when not feasible (e.g. affinity on other users' processes
under Yama).

## 4. Per-process network — feasibility-true design (no eBPF, no root)

The concept doc rejects eBPF/root approaches; r053 adds the **socket-owner
attribution** design that fits the mandates:

- **Own processes (exact):** read `/proc/<pid>/fd/*` → socket inodes
  (`socket:[12345]`), match against `/proc/net/{tcp,tcp6,udp,udp6,unix}`
  inode tables; per-process rx/tx bytes are then **attributed from the
  per-interface deltas proportional to each process's open-socket
  lifetime share** (kernel has no per-socket byte counters without
  eBPF — the honest model is attribution, labeled as such in the UI).
- **Children/tree:** sum attribution over the process subtree (edges
  already exist); the preview shows self / children / combined.
- **Other users under Yama ptrace_scope=1:** fd listing is EACCES →
  `lock` + "—" (existing degrade taxonomy). Best-effort where readable.
- **Cadence:** attribution pass runs at the sampler cadence but scans
  fd tables incrementally (cache socket-inode→pid map; only re-scan
  changed PIDs) — bounded cost, watchdog-safe.
- **Honesty rule:** column header tooltip and preview note state
  "socket-owner attribution (proportional), not kernel accounting."

## 5. Competitive parity table (r053 landscape check)

| Feature | gnome-system-monitor | htop | btop | Mission Center | linprocman |
|---|---|---|---|---|---|
| Column chooser w/ persistence | ✓ | partial | fixed set | ✓ | **22 cols, spec'd** |
| Per-process I/O + rates | ✓ | ✓ | ✓ | ✓ | spec'd (r039 io readers) |
| Per-process network | – | – | partial | ✓ (eBPF) | **attribution design (no root)** |
| Preview/details pane | dialog | minimal | pane | **rich pane** | **mockup J pane** |
| Parent chain / tree nav | ✓ | tree | tree | ✓ | ancestry click-to-jump |
| Dependencies (libs/sockets) | – | – | – | partial | spec'd |
| Context menu w/ signals/renice/affinity | partial | ✓ | limited | ✓ | **spec'd** |
| Frequency/incident analytics | – | – | – | – | **unique (r040 engine)** |
| Logs integrated | – | – | – | – | **unique (Phase 7)** |
| PSI pressure chips | – | – | ✓ | – | spec'd (r036) |
| Offline / no-root mandate | n/a | n/a | n/a | ✗ (eBPF) | **by design** |

## 6. Phasing

- **Phase 3** (actions) gains: context menu skeleton + signal/renice/
  affinity handlers (menu items active as handlers land).
- **Phase 4** (tree & details) becomes **preview pane** per §2 + column
  chooser + CPU-time/Mem%/Started/Threads columns.
- **Phase 5** (resources) gains io-rate/net-attribution columns (§4) and
  oom_score/affinity/ioprio columns.
- Schema additions to the frozen record: batched per phase, each batch
  through sign-off.

## 7. Tests

Column toggling round-trip (settings), no-data "—" for restricted io/net,
attribution proportionality unit (synthetic fd/net fixtures), ancestry
rendering (deep chains, orphans), menu disable-reasons, bars render
0–100 bounds.
