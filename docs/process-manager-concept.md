# linprocman — Technical Concept

Status: draft for operator review (r036–r037, 2026-09-26)
Base framework: mikesdatawork/gtk-python-dashboard-starter (GTK3 + Python, to be vendored into `src/`)
Icon set: Phosphor (MIT), master library `~/projects/assets/icons`, project subset in `resources/icons/` (54 icons, manifest inside)
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

Everything the app needs is in `/proc`. v1 has **zero runtime dependencies
beyond the starter's** (PyGObject, pycairo, Pillow) — no psutil at runtime.

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

Module boundaries are load-bearing: nothing but `procfs.py` reads the kernel;
nothing but `manager_actions.py` mutates the system; UI pages consume
snapshots and never reach sideways.

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

**Table** — name, user, CPU %, memory, VMSize/shared, disk r/w, nice, PID,
state, started, CPU time, optional cgroup unit; sortable, columns
choosable, widths remembered. **Tree** — PPID hierarchy, kernel threads
grouped/dimmed/hidden by default, orphans re-parented. **Filtering** —
instant substring over name/PID/user/cmdline + scope chips (All / Mine /
System / Active). **Actions** — end, kill, stop/continue, hangup, custom
signals, renice; confirmed where destructive; exact errno text on refusal.
**Details pane** — identity, memory (RSS/PSS/shared/virtual), time, I/O,
cmdline, exe/cwd; locked fields shown as `lock`, never errors.
**Resources** — stacked per-core CPU, memory+swap, network, PSI chips,
load/uptime summary. **Live control** — interval selector, pause/resume,
refresh now; sampling backs off when hidden.

## 5. UI direction (see docs/mockups/)

Four mockups on the real starter palette (`#2d2d2d` window, `#353535` sidebar,
`#0078D7` accent, hairline `#1a1a1a`, Ubuntu) with the real icon subset:

| Mockup | Layout | Best for |
|---|---|---|
| A — Dashboard + Details | starter sidebar + process table + fold-out details pane | continuity with linfilesearch A+; the primary candidate |
| B — Process Tree | same page, tree mode, kernel threads grouped | verifying hierarchy affordances |
| C — Resources | per-core stacked CPU, memory+swap, network, PSI chips | the cairo graph targets |
| D — Action Dialogs | kill confirm + renice + signal picker over dimmed table | the permission/safety UX |

Open decisions for the operator:
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
- No GTK4 port (starter is GTK3)

## 8. Risks (cross-cutting; per-module risks live in the module docs)

| Risk | Mitigation |
|---|---|
| /proc parse edge cases | parse-after-last-`)` rule + hostile fixtures (procfs-data.md) |
| PID recycling mid-action | (pid, starttime) guard (actions-permissions.md) |
| UI jank on sort-heavy refresh | block-sort around diff batches; typed columns (process-table.md) |
| Freeze from walking smaps for all PIDs | selected-process only, by design (procfs-data.md) |
| Hardened /proc (hidepid) / restricted io | "—" cells + `lock`; degrade, never error |

## 9. Roadmap

1. Vendor starter into `src/`, wire Processes page shell; replace the
   starter's venv/pip `run.sh` with a direct system-python launcher
   (build-principles.md §4).
2. `procfs.py` readers + fixture unit tests (hostile stat lines, CLK_TCK).
3. Sampler thread → flat table end-to-end, diff-in-place updates.
4. Sort, filter, scope chips, selection stability.
5. Actions + PID guard + permission UX (mockup D flows).
6. Tree view with kernel-thread grouping.
7. Details pane incl. PSS/IO/cmdline.
8. Resources page graphs + PSI.
9. Settings/persistence, installer (linfilesearch `install.sh` pattern), v1 tag.
