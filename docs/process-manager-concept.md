# linprocman — Technical Concept

Status: draft for operator review (r036–r037, 2026-09-26)
Base framework: mikesdatawork/gtk-python-dashboard-starter (GTK3 + Python, to be vendored into `src/`)
Icon set: Phosphor (MIT), master library `~/projects/assets/icons`, project subset in `resources/icons/` (69 files: 57 regular + 12 fill, 60 names, manifest inside)
Build rules: [build-principles.md](build-principles.md) — binding

Modular docs: each area of logic lives in its own document under
[modules/](modules/) (modularity mandate). This file is the overview and index.

## 1. What this is

A native Linux desktop process manager: live process table, process tree,
CPU/memory/network history, and the traditional control actions — end, kill,
stop/continue, renice, custom signals. Target platform is Linux Mint 22.x /
Debian (X11 or Wayland), running as an unprivileged user process. Feature
parity reference: gnome-system-monitor (installed on this machine) and htop;
scope is process monitoring and control, not system administration.

Everything the app needs is on the local machine: kernel interfaces —
`/proc` and `/sys` — plus the local `journalctl` binary for logs. v1 has
**zero runtime dependencies beyond the starter's** (PyGObject, pycairo,
Pillow) — no psutil, no python3-systemd, no network.

**Binding mandates (r036, see build-principles.md):** fundamentals from
MensuraMedia/universal-instruction-set v2026.04; modularity and universality
are product mandates; assets strictly from the local Phosphor master
`~/projects/assets/icons` (copied in, never referenced); the app is fully
self-reliant — no web-based resources at build or runtime, ever.

## 2. Module documents (the grouped logic)

| Doc | Maps to | Owns |
|---|---|---|
| [modules/procfs-data.md](modules/procfs-data.md) | `procfs.py` | every /proc reader, parse traps, fixture tests |
| [modules/sampling-pipeline.md](modules/sampling-pipeline.md) | `manager_sampler.py` | cadence, snapshot schema, rate math, backoff |
| [modules/process-table.md](modules/process-table.md) | `page_processes.py` | flat/tree models, diff-in-place, filter, details pane |
| [modules/actions-permissions.md](modules/actions-permissions.md) | `manager_actions.py` | signals, renice, (pid,starttime) guard, error contract |
| [modules/resource-graphs.md](modules/resource-graphs.md) | `page_resources.py` + `manager_history.py` | ring buffers, cairo charts, PSI chips |
| [modules/persistence-config.md](modules/persistence-config.md) | `config_processes.py` | settings.json schema, XDG rules |
| [modules/disks-filesystems.md](modules/disks-filesystems.md) | `page_disks.py` | per-device I/O rates, per-mount usage |
| [modules/logs-journal.md](modules/logs-journal.md) | `manager_logs.py` + `page_logs.py` | journal engine, sidebar submenu, search, row context menu, saved views |
| [modules/log-frequency.md](modules/log-frequency.md) | `manager_frequency.py` | right-click Frequency: pattern histogram, incident bands, related events, export |
| [modules/process-preview.md](modules/process-preview.md) | preview pane + columns + menu | extended 22-column chooser, process preview, context menu, per-process net attribution |
| [modules/telemetry-watch.md](modules/telemetry-watch.md) | `manager_telemetry.py` (concept) | Telemetry Watch: unattended-egress scoring, fingerprint rules, allow/deny — Phase 5 |
| [modules/sysfs-data.md](modules/sysfs-data.md) | `sysfs.py` | hwmon temperatures, cpufreq, AMD GPU chip |

Module boundaries are load-bearing: only `procfs.py` and `sysfs.py` read
kernel interfaces; only `manager_logs.py` spawns local binaries (journalctl,
dmesg) under the argv contract; only `manager_actions.py` mutates the
system; UI pages consume snapshots and never reach sideways.

## 3. Foundation: the starter framework

| Starter element | Use here |
|---|---|
| `src/ui/dashboard_window.py`, `sidebar.py`, `content_area.py` | app shell: 150px sidebar, page routing |
| `src/pages/page_base.py` + page registry | new pages: Processes, Resources, Disks, About, Settings |
| `src/config/config_themes.py` (7 dark themes) | unchanged; graphs derive series colors from the theme accent |
| `src/modules/manager_navigation.py`, `manager_theme_applicator.py` | unchanged |
| `resources/css/style.css` | extended with table/tree/graph/statusbar classes |
| `resources/images/` + `resources/icons/` | logo (`pulse`); icon subset staged by this document |

## 4. Feature set (traditional inventory)

**Table** — name, user, CPU %, memory (RSS + swap VmSwap), VMSize/shared,
disk r/w, nice, PID, state, started, CPU time, optional cgroup unit;
sortable, columns choosable, widths remembered; full keyboard operation
(Ctrl+F filter, arrows, Enter details, Delete end). **Tree** — PPID
hierarchy, kernel threads grouped/dimmed/hidden by default, orphans
re-parented. **Filtering** — instant substring over name/PID/user/cmdline
(regex toggle) + scope chips (All / Mine / System / Active / Containers).
**Actions** — end, kill, stop/continue, hangup, custom signals, renice, CPU
affinity; multi-select bulk actions; confirmed where destructive; exact
errno text on refusal. **Details pane** — identity, memory
(RSS/PSS/shared/virtual/swap), time, I/O, cmdline, exe/cwd; locked fields
shown as `lock`, never errors. **Resources** — stacked per-core CPU,
memory+swap, network, PSI chips, load/uptime summary, temperature/frequency
chips. **Disks** — per-device rates, per-mount usage, live plug events.
**Logs** — sidebar submenu (Journal / Kernel / Auth / Applications / Saved
Views), journalctl-backed, substring+regex search, time-jump, follow mode,
priority coloring, row context menu (copy/flag/filter/focus),
**Frequency analysis** (error-over-time histogram per message pattern with
incident bands, related events plotted before/after, PNG/CSV export),
saved views + cursor flags, export. **Live control** —
interval selector, pause/resume, refresh now; sampling backs off when
hidden.

## 5. UI direction (see docs/mockups/)

Four mockups on the real starter palette (`#2d2d2d` window, `#353535` sidebar,
`#0078D7` accent, hairline `#1a1a1a`, Ubuntu) with the real icon subset:

| Mockup | Layout | Best for |
|---|---|---|
| A — Dashboard + Details | starter sidebar + process table + fold-out details pane | continuity with linfilesearch A+; the primary candidate |
| B — Process Tree | same page, tree mode, kernel threads grouped | verifying hierarchy affordances |
| C — Resources | per-core stacked CPU, memory+swap, network, PSI chips | the cairo graph targets |
| D — Action Dialogs | kill confirm + renice + signal picker over dimmed table | the permission/safety UX |
| E — Logs: Journal | sidebar submenu, search bar, priority coloring, follow | the mandated logs feature, primary look |
| F — Logs: Saved Views | saved views management + flags | the organize model |
| G — Logs: Context + Frequency | right-click menu + frequency analysis view | the r040 controls |
| H — Sidebar width study | 150/170/190px variants, left-aligned nav, natural submenu indent | shell concept (r040) |

Sidebar shell direction (mockup H): nav buttons share one left-aligned icon
column; submenu rows indent one level from the parent's text, never from the
icon; width expansion (150 → 170/190px) is studied as a concept — the
starter's `config_layout.py` makes it a constant change if adopted.

Open decisions for the operator (module docs carry **provisional**
defaults until you freeze them — a freeze lands here and the module docs in
one change):
1. Is A (sidebar + details fold-out) the primary direction, as it was for linfilesearch?
2. CPU % default: per-core normalized (100% = one core) or whole-machine?
3. Default refresh 2 s table / 1 s graphs — aggressive enough?
4. Kernel threads hidden by default — correct call?
5. Brand mark: `pulse` (activity) — or `gauge`?

## 6. Data flow

```
/proc ──1s──► sampler thread ──Snapshot──► queue ──GLib.idle_add──► main thread
                                                                   │
              ┌────────────────────────────────────────────────────┤
              ▼                        ▼                           ▼
        ListStore/TreeStore      history rings                 details pane
        (diff-in-place,          (CPU/mem/net/PSI)             (smaps_rollup for
         TreeModelFilter)              │                        selected pid only)
              │                        ▼
              ▼                  cairo DrawingAreas
        row selected ──(pid, starttime)──► manager_actions
                                            │ os.kill / setpriority
                                            ▼
                                     status line (result / errno text)
```

## 7. Non-goals (v1)

- No root mode, no polkit/pkexec elevation
- No per-thread view (`/proc/<pid>/task/*`) — v2 candidate
- No open-files/socket inspector (lsof territory)
- No "run new task" launcher — v2 candidate
- No cgroup/systemd unit management (column is read-only display)
- No GTK4 port (starter is GTK3) — the sanctioned path and its
  portability seams are defined in [gtk4-port.md](gtk4-port.md); the port
  itself stays a post-v1 operator decision

## 8. Risks (cross-cutting; per-module risks live in the module docs)

| Risk | Mitigation |
|---|---|
| /proc parse edge cases | parse-after-last-`)` rule + hostile fixtures (procfs-data.md) |
| PID recycling mid-action | fresh-stat (pid, starttime) check at click time (actions-permissions.md) |
| UI jank on sort-heavy refresh | block-sort around diff batches; typed columns (process-table.md) |
| Freeze from walking smaps for all PIDs | selected-process only, by design (procfs-data.md) |
| Hardened /proc (hidepid) / restricted io | minimal locked rows, distinct from exit-drop (procfs-data.md) |
| Fork-bomb PID flood freezes the manager | row budget + filter suspension + cadence coarsening (process-table.md) |
| Sampler thread dies silently | loop watchdog + "sampling stalled" banner (sampling-pipeline.md) |
| Journal flood / huge initial read | -n cap, cursor paging, coalesced drop-oldest appends (logs-journal.md) |
| Journal access varies by user group | startup probe, locked sources with remedy text, never elevate (logs-journal.md) |

## 9. Roadmap — phased precedence (adversarially reviewed, r039)

Docs are amended before code (the binding-doc rule); each phase lands with
its module doc's tests green.

- **Phase 1 — Data core.** Vendor starter, page shells, direct system-python
  launcher; `procfs.py` + `sysfs.py` readers with hostile fixtures,
  hidepid/EACCES taxonomy, system-math formulas (btime, busy fields,
  memory-used, ncpu, counter resets, lo exclusion).
- **Phase 2 — Live table.** Sampler (watchdog, queue drop-oldest, interval
  semantics settled) → flat table diff-in-place (RowReference keys, explicit
  move op designed now for the later tree), sort/filter/scope, selection
  stability, VmSwap column, keyboard operation, settings.json skeleton
  persisting sort/columns/interval now.
- **Phase 3 — Control & safety.** Actions (fresh-stat PID guard, corrected
  renice rule, affinity), dialogs, multi-select bulk actions, status
  contract ("signal sent", not "ended").
- **Phase 4 — Tree & details.** TreeStore tree with kthread grouping,
  orphan relocation; details pane incl. PSS/IO/cmdline/swap.
- **Phase 5 — Resources + sensors.** Timestamped ring buffers, per-core
  stacked charts, memory/network, PSI chips, temperature/frequency/GPU chips
  (sysfs).
- **Phase 6 — Disks.** diskstats rates + mount usage page.
- **Phase 7 — Logs (large — size like phases 1–2).** journalctl engine under
  the argv contract, four presets, follow/tail, search + time-jump,
  priority coloring, saved views + flags, export.
- **Phase 8 — Ship.** Installer, version stamp, v1 tag.

Post-v1 backlog (respects §7): memory maps, AppArmor context, regex filter
port, CSV table export, watch/pin rows, container scope grouping,
window-finder (X11 only), threshold notifications (operator gate), battery
chip (operator gate), per-cgroup aggregate rows (operator gate).
Promoted into v1 modules by the r042 collaborator review: oom_score in the
details pane, fan chips, D-state badge, spawn/exit flash, details
sparkline, PSI memory banner, process-table saved presets, journal-for-unit
from a process row. Per-process network: the r053 socket-owner-attribution design
(modules/process-preview.md §4) replaces the blunt rejection — exact for
own processes, proportional attribution, "—" under Yama, still no
eBPF/root.
