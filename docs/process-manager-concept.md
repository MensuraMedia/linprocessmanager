# linprocman — Technical Concept

Status: draft for operator review (r036, 2026-09-26)
Base framework: mikesdatawork/gtk-python-dashboard-starter (GTK3 + Python, to be vendored into `src/`)
Icon set: Phosphor (MIT), master library `~/projects/assets/icons`, project subset in `resources/icons/` (54 icons, manifest inside)

## 1. What this is

A native Linux desktop process manager: live process table, process tree,
CPU/memory/network history, and the traditional control actions — end, kill,
stop/continue, renice, custom signals. Target platform is Linux Mint 22.x /
Debian (X11 or Wayland), running as an unprivileged user process. Feature
parity reference: gnome-system-monitor (installed on this machine) and htop;
scope is process monitoring and control, not system administration.

Everything the app needs is in `/proc`. v1 has **zero runtime dependencies
beyond the starter's** (PyGObject, pycairo, Pillow) — no psutil at runtime.

## 2. Foundation: the starter framework

| Starter element | Use here |
|---|---|
| `src/ui/dashboard_window.py`, `sidebar.py`, `content_area.py` | app shell: 150px sidebar, page routing |
| `src/pages/page_base.py` + page registry | new pages: Processes, Resources, Disks, About, Settings |
| `src/config/config_themes.py` (7 dark themes) | unchanged; graphs derive series colors from the theme accent |
| `src/modules/manager_navigation.py`, `manager_theme_applicator.py` | unchanged |
| `resources/css/style.css` | extended with table/tree/graph/statusbar classes |
| `resources/images/` + `resources/icons/` | logo (`pulse`); icon subset staged by this document |

New modules under the starter's conventions:

```
src/modules/procfs.py            /proc readers: stat, status, io, smaps_rollup, cgroup, system-wide
src/modules/manager_sampler.py   background snapshot loop (thread, queue, cadence)
src/modules/manager_actions.py   signals, renice, PID-recycle guard, permission UX
src/modules/manager_history.py   ring buffers for CPU/mem/net/PSI samples
src/pages/page_processes.py      table + tree + filter + details pane
src/pages/page_resources.py      cairo graphs + PSI chips
src/pages/page_disks.py          per-mount usage (statvfs, reuse of linfilesearch mount model)
src/config/config_processes.py   columns, refresh cadence, defaults
```

## 3. Feature set (traditional inventory)

**Table** — one row per process: name (+ icon), user, CPU %, memory (RSS and %),
VMSize, shared, disk read/write total, nice value, PID, state (R/S/D/Z/T with
color), started time, CPU time, cgroup unit (Mint is systemd; optional column,
off by default). Columns sortable both ways, choose which are visible, widths
remembered.

**Tree** — parent/child hierarchy from PPID, twisty-expandable, same columns as
the flat table. Kernel threads grouped under `kthreadd`, dimmed, and hidden by
default (toggle). Orphans (parent already reaped) attach to their nearest live
ancestor.

**Filtering** — instant substring filter over name / PID / user / command line
(matches the `magnifying-glass` entry). Scope chips like linfilesearch's mount
chips: **All processes / My processes / User X / System / Active (CPU or I/O in
last sample)**.

**Actions** — End process (SIGTERM), Kill (SIGKILL), Stop (SIGSTOP), Continue
(SIGCONT), Hangup (SIGHUP), custom signal picker, renice (−20…19). Kill and
renice confirm with a dialog. Failed actions surface the exact `errno` message
("Operation not permitted") in the status line — never a silent no-op, never a
crash.

**Details pane** — selected process, refreshed every sample: status, PID/PPID,
threads, CPU time, started, RSS/VMSize/shared + PSS, disk I/O counters, niceness,
command line (monospace), executable path, working directory, cgroup unit.
Unreadable fields (other users' `environ`, hardened `/proc`) show a `lock` icon
instead of an error.

**Resources** — total CPU history + per-core stacked areas, memory + swap
history, network up/down history, load average, uptime, and PSI
(`/proc/pressure/{cpu,memory,io}`) as numeric chips with `gauge`.

**Live control** — refresh interval selector (0.5/1/2/5 s, default 2 s table /
1 s graphs), pause/resume (`pause-circle`/`play`), refresh now
(`arrow-clockwise`). Sampling backs off automatically while the window is
hidden.

## 4. Data acquisition: /proc, read directly

Verified on this machine (2026-09-26, kernel 7.0.0-31-generic): `/proc/pressure/*`
present, `smaps_rollup` readable for own processes, psutil 5.9.8 installed
(dev-time cross-check only — it does not expose PSI, and its
`cpu_percent(interval=…)` blocks, both reasons to stay on direct reads).

| Data | Source | Notes |
|---|---|---|
| per-PID basics | `/proc/<pid>/stat` | comm parsed after the **last** `)` — comm may contain spaces and parens; utime(14) stime(15) starttime(22) nice(19) threads(20) rss(24), fields 1-indexed after the pid field |
| state, PPid, VmRSS/VmSize/shared | `/proc/<pid>/status` | cheaper to trust for memory fields; includes human-readable state letter |
| PSS | `/proc/<pid>/smaps_rollup` | **selected process only** — walking smaps for every PID every tick is the classic freeze mistake |
| disk I/O | `/proc/<pid>/io` | read/write bytes; readable for own processes, often restricted for others → render "—" when unreadable (permission model varies by kernel config; verify at implementation) |
| command line | `/proc/<pid>/cmdline` | NUL-separated; kernel threads have none — that is the kthread detector |
| exe, cwd | `readlink /proc/<pid>/exe|cwd` | EACCES for other users → `lock` |
| user | `pwd.getpwuid` (stdlib) | cache uid→name |
| cgroup unit | `/proc/<pid>/cgroup` | v2 line `0::/user.slice/…/x.scope` → last segment |
| system CPU | `/proc/stat` | per-CPU jiffies + total |
| memory | `/proc/meminfo` | MemTotal/Available/Cached/SwapTotal/SwapFree |
| network | `/proc/net/dev` | rx/tx bytes per iface, summed, deltas between samples |
| PSI | `/proc/pressure/{cpu,memory,io}` | `some avg10/avg60/avg300` (+`full` for memory/io) |

Every reader is a pure function `bytes → dict` so it can be unit-tested against
fixture files (same pytest pattern as linfilesearch's matcher tests), including
hostile fixtures: comm with spaces, comm with parens, empty cmdline, truncated
stat lines, disappeared PID (`FileNotFoundError` → row simply drops).

## 5. Rates: CPU % math

CPU % is computed from **jiffy deltas between consecutive snapshots**, never
from a blocking interval call:

```
cpu% = Δ(utime + stime) / (CLK_TCK × Δwallclock) × 100        # 100% = one core (htop default)
cpu%_total = cpu% / ncpu                                        # 100% = whole machine
```

- First sample after launch shows "—" (no delta yet).
- A per-core-normalized default with a settings toggle for whole-machine
  normalization (the two tools we mirror disagree; offering both removes the
  argument).
- Process vanished between samples → drop the row, keep the delta window clean.
- `CLK_TCK` read via `os.sysconf("SC_CLK_TCK")` at startup — **verified 100** on this
  machine (2026-09-26).

## 6. UI architecture (GTK3)

**Models.** Flat mode: `Gtk.ListStore`; tree mode: `Gtk.TreeStore`. Columns are
**typed** (PID int, CPU float, mem bytes int, nice int) — sorting on typed
columns is free and correct; display formatting (2.4 MB, 01:23:45) is done in
`set_cell_data_func`, not stored as strings. This generalizes the hidden-epoch
trick linfilesearch needed for dates.

**Filtering.** `Gtk.TreeModelFilter` with a `visible_func` over the current
query + scope chip. The filter wraps the store once and is re-pointed, not
rebuilt per keystroke.

**Update without flicker.** One snapshot arrives → the model is **diffed in
place** keyed by PID (dict of PID→TreeIter): update changed rows, append new,
remove gone. Sorting is blocked around the batch (`tree_sortable.set_sort_column_id` /
restore) so it happens once per refresh, not per row. Diffing preserves
selection, sort position, and tree expansion — the three things a full rebuild
breaks. Selection is restored by `(pid, starttime)` key, not row index.

**Sampler thread.** `threading.Thread` reads /proc at 1 s cadence, publishes
immutable `Snapshot` objects to a `queue.Queue`; the GTK main thread drains via
`GLib.idle_add`. Table applies every 2nd snapshot, graphs every snapshot,
details pane every snapshot. Same streaming pattern as the linfilesearch engine
— /proc reads for a few hundred processes are milliseconds warm (assumed;
measure in implementation step 2 and raise cadence if wrong).

**Details pane.** Right-hand fold-out (290px, `caret-left`/`caret-right` fold —
the r028 square-toggle pattern from linfilesearch transfers directly). Cheap
fields refresh every sample; `smaps_rollup` only for the selected PID.

**Graphs.** `cairo` `DrawingArea`s, ring buffers (`collections.deque`
maxlen=300 ≈ 5 min at 1 s), stacked per-core CPU polygons, memory area + swap
line, network two-line. Redraw happens in the `draw` callback; no timers beyond
the sampler. Series colors derive from the active starter theme so all 7 themes
work without new assets.

## 7. Actions & permissions

- All signals via `os.kill(pid, sig)`; renice via `os.setpriority`.
- **PID-recycle guard**: rows carry `(pid, starttime)`; before acting, the
  sampler's latest snapshot is checked — if `starttime` changed, the action
  aborts with "process ended, PID reused" in the status line. The window is
  milliseconds; the guard closes it.
- Killing your own processes always works; system processes raise `EPERM` →
  status-line message with the exact errno text. v1 never elevates; a pkexec
  path is a possible later opt-in, deliberately not wired in.
- SIGKILL/SIGTERM confirm with a dialog naming the process and PID (mockup D).
- Zombies display as `name (defunct)`; the details pane explains they exit when
  the parent reaps them — killing a zombie directly is meaningless and the UI
  says so instead of pretending.
- niceness: lowering nice value (more priority) raises `EACCES` for normal
  users unless the process is ours — surfaced the same way.

## 8. UI direction (see docs/mockups/)

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

## 9. Data flow

```
/proc  ──1s──► sampler thread ──Snapshot──► queue ──GLib.idle_add──► main thread
                                                          │
              ┌───────────────────────────────────────────┤
              ▼                       ▼                   ▼
        ListStore/TreeStore      history rings        details pane
        (diff-in-place,          (CPU/mem/net/PSI)    (smaps_rollup for
         TreeModelFilter,             │                selected pid only)
              │                        ▼
              ▼                  cairo DrawingAreas
        row selected ──(pid, starttime)──► manager_actions
                                            │ os.kill / setpriority
                                            ▼
                                     status line (result / errno text)
```

## 10. Configuration & persistence

`~/.config/linprocman/settings.json`: refresh interval, view mode (flat/tree),
visible columns + widths + sort, scope chip, kernel-thread visibility, CPU
normalization, theme choice, window geometry. Nothing else writes outside the
XDG dir. No secrets, no telemetry, no root.

## 11. Non-goals (v1)

- No root mode, no polkit/pkexec elevation
- No per-thread view (`/proc/<pid>/task/*`) — v2 candidate
- No open-files/socket inspector (lsof territory)
- No "run new task" launcher — v2 candidate
- No cgroup/systemd unit management (column is read-only display)
- No GTK4 port (starter is GTK3)

## 12. Risks

| Risk | Mitigation |
|---|---|
| /proc parse edge cases (comm with spaces/parens, truncated lines) | parse-after-last-`)` rule, fixture unit tests incl. hostile samples |
| PID recycling mid-action | `(pid, starttime)` guard before every signal |
| `/proc/<pid>/io` unreadable for other users | "—" cells + `lock`; degrade, never error |
| UI jank on sort-heavy refresh | block-sort around diff batches; typed columns |
| Huge processes (thousands of threads) | v1 never walks tasks/; smaps_rollup only for selection |
| Hardened /proc (hidepid) | detection + `lock` styling; app stays read-only-useful |
| Freeze from walking smaps for all PIDs | forbidden by design (§4) |

## 13. Roadmap

1. Vendor starter into `src/`, wire Processes page shell.
2. `procfs.py` readers + fixture unit tests (incl. `CLK_TCK`, hostile stat lines).
3. Sampler thread → flat table end-to-end, diff-in-place updates.
4. Sort, filter, scope chips, selection stability.
5. Actions + PID guard + permission UX (mockup D flows).
6. Tree view with kernel-thread grouping.
7. Details pane incl. PSS/IO/cmdline.
8. Resources page graphs + PSI.
9. Settings/persistence, installer (linfilesearch `install.sh` pattern), v1 tag.
