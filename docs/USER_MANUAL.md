# LinProcessManager — User Manual

*LinProcessManager (linprocman) is a native Linux process manager for the
desktop: a live process table with signals and priorities, per-app network
traffic, disk capacity and I/O, hardware sensors, system dashboards, and a
journal viewer — in one dark, fast window.*

Version: covers the build as of 2026-09-28 (r133+). Menu entries marked
*(Phase 4)* are placeholders that arrive with upcoming releases.

**How to read this manual**

| Convention | Meaning |
|---|---|
| **Bold** | UI labels, buttons, and column names as they appear on screen |
| `Ctrl+F` | Keyboard shortcuts (hold the first key, press the second) |
| Right-click | Press the right mouse button |
| "—" | A dash cell means *no data* — the app never guesses |

---

## Contents

1. [Getting started](#1-getting-started)
2. [The window at a glance](#2-the-window-at-a-glance)
3. [Processes — the live table](#3-processes--the-live-table)
4. [The right-click menu on Processes](#4-the-right-click-menu-on-processes)
5. [Sorting and choosing columns](#5-sorting-and-choosing-columns)
6. [Graphs (with the Basics cards)](#6-graphs-with-the-basics-cards)
7. [Disks](#7-disks)
8. [Network](#8-network)
9. [Peripherals](#9-peripherals)
10. [Logs](#10-logs)
11. [Settings](#11-settings)
12. [The system tray icon](#12-the-system-tray-icon)
13. [Understanding the colors](#13-understanding-the-colors)
14. [Keyboard shortcuts](#14-keyboard-shortcuts)
15. [Where your data lives](#15-where-your-data-lives)
16. [How the numbers are made (honesty notes)](#16-how-the-numbers-are-made-honesty-notes)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. Getting started

### Install

From the project folder run:

```bash
./install.sh
```

This installs the program-menu entry ("LinProcessManager"), the icon set,
and the `linprocman` launcher. Required packages (`python3-gi`,
`gir1.2-gtk-3.0`, `python3-cairo`, `python3-pil`) are checked for you.
`./install.sh --uninstall` removes the menu entry, icons, and launcher
while **keeping** your settings, marks, and tracking history.

### Launch

- From the menu: **LinProcessManager**, or
- from a terminal: `linprocman`, or
- `linprocman --version` prints the installed revision.

Starting a second instance while one is running simply brings the running
one forward (single-instance by design).

### Quit

Sidebar → **About** has app information; the **tray icon** menu offers
Show/Hide and Quit. Closing the window hides it to the tray — the app keeps
running so its history keeps filling.

---

## 2. The window at a glance

The left sidebar selects the page; the rest of the window is that page:

| Sidebar entry | What it shows |
|---|---|
| **Processes** | the live process table, filter, signals, priorities |
| **Graphs** | system dashboards — the Basics cards on top, the chart hub below |
| **Disks** | per-mount capacity, usage bars, per-device I/O rates |
| **Network** | per-process network traffic with a Tx/Rx bar per app |
| **Peripherals** | connected USB devices and hardware sensor chips |
| **Logs** | the systemd journal viewer |
| **About** | app information and license |
| **Settings** (bottom) | refresh interval, scope, calibration |

---

## 3. Processes — the live table

The main page. Every running process appears within a second; the table
updates in place (rows don't jump while you read them).

### The toolbar, left to right

| Control | What it does |
|---|---|
| **Filter by name (Ctrl+F)** | type to narrow the table by process name |
| **.\*** | toggles regular-expression matching for the filter |
| **All / My processes / System / Active** | scope chips — which processes to list |
| **Pause** | freezes the table (F5); the sampler keeps running |
| **⟳ Refresh (Ctrl+R)** | forces an immediate refresh of mounts and data |
| **2s ▾** | refresh interval (0.5–5 s) |
| **Kernel threads** | shows kernel worker threads (hidden by default) |
| **Preview ▾** | opens/closes the process preview sidebar |

### Reading a row

- **Process** shows the name (bold) with its systemd unit in small gray
  text; **State** shows R (running), S (sleeping), D (disk wait), Z (zombie).
- Column headers **sort**: first click descending, second click ascending.
  Values that are unknown sort last in both directions.
- Rate columns (Reads, Writes, ↓, ↑) are per-refresh-interval rates.
- Green/yellow/red fills in the mini-bars are the **zone system** — see
  [Understanding the colors](#13-understanding-the-colors).

### The band on top

Six cards (CPU, Memory, Swap, Disk I/O, Network, Load) summarize the whole
machine with the same zone coloring. **Double-click a card** to jump to the
Basics view for that metric.

### Selecting rows

Click selects; the selection drives the context menu and any preview. The
right-click menu is described in the next section.

---

## 4. The right-click menu on Processes

Right-click a row. The row is selected first — the menu acts on the
selection. Items that don't apply to the selected process are grayed with
the reason on hover.

| Menu item | What it does |
|---|---|
| **Show in tree** *(Phase 4)* | tree grouping — arriving in a future release |
| **Copy PID** | copies the process ID to the clipboard |
| **Copy command line** | copies the full command line |
| **Open executable location** | opens the folder containing the program file |
| **Stop (SIGSTOP)** | pauses the process — it stays in memory |
| **Continue (SIGCONT)** | resumes a stopped process |
| **End (SIGTERM)** | asks the process to exit (graceful) |
| **Kill (SIGKILL)** | terminates it immediately |
| **Hang up (SIGHUP)** | the traditional "re-read config" signal |
| **End group — children too** | graceful end of the process **and its whole child tree**, with verification |
| **Kill group — children too** | forceful version, same tree, SIGKILL escalation |
| **Send signal ▸** | any signal from a picker (HUP, INT, QUIT, USR1, USR2, TERM, KILL) |
| **Change priority (renice) ▸** | niceness 1 / 5 / 10 / 19 (unprivileged users can only lower priority — the dialog states the rule first) |
| **Set CPU affinity ▸** | All CPUs / First CPU only |
| **Frequency…** *(Phase 4)* | per-process activity pattern view — arriving |
| **View journal for unit…** *(Phase 4)* | journal filtered to this service — arriving |

**Destructive items confirm first.** Kill and the group operations show an
inline confirmation bar inside the page (never a popup that can hide behind
the window), and after the signal the app **verifies the outcome** and
reports it in the status line: "KILL confirmed — process N terminated",
"terminated — awaiting parent reap" (a zombie whose parent hasn't collected
it yet), or "still running: N".

Unprivileged users can only signal and renice their own processes; anything
not permitted is grayed, and failures are reported verbatim (e.g. EPERM).

---

## 5. Sorting and choosing columns

- **Sort**: click any column header. The active column shows a ▼/▴ marker.
- **Choose columns**: **right-click the column headers** to open the column
  chooser — 25 columns in five groups (Identity, CPU, Memory, I/O & Network,
  Diagnostics). Tick what you want; the set and widths are remembered.
  Useful picks beyond the defaults: **Command line**, **Threads**,
  **CPU time**, **↓ Net**, **↑ Net**, **Started**, **OOM score**.
- Column widths persist; a column can never shrink below a readable floor.

---

## 6. Graphs (with the Basics cards)

The **Graphs** page has two parts:

### Basics — the cards on top

Six cards (CPU, Memory, Swap, Disk I/O, Network, Load): the **performance
bar on top** shows the current level in its zone color; below it, the
**top contributing processes** with their own mini usage bars — click a
contributor to jump to it in the Processes table.

- Memory at 67% renders **yellow** (it crossed the 60% warning threshold);
  a disk over 60% or CPU over its calibrated threshold renders **red**.
- **Swap** and cards with nothing to report show "—" honestly.

### The chart hub

Below the cards, one mini-chart per metric (CPU, Memory, Swap, Disk I/O,
Network, Pressure, Load) drawn from a rolling ~5-minute window. **Click a
chart** to open its detail page: larger time windows (1 m / 5 m), min/avg/
max, per-core and per-direction breakdowns, and the top contributors.

The **Graphs sidebar entry** opens this hub with the Basics cards above it.

---

## 7. Disks

Per-filesystem capacity and per-device I/O in one table:

- **Usage** bars are zone-colored with threshold ticks; the fill moves, the
  bar never changes size.
- **Inodes %** is shown because a filesystem can run out of inodes while
  having bytes free.
- Unmounted devices (install media, spare partitions) are **flagged**, not
  hidden; pseudo/loop filesystems are hidden behind a "N hidden — show"
  count row.
- **Refresh** re-scans; plugging a USB stick updates the list.
- Read-only by design — no mount/eject actions.

---

## 8. Network

Every process that is **actively sending or receiving packets** — internet
or local network — with live per-second rates.

### Reading the traffic bar

Each row's **Tx ← → Rx** bar is a train of small colored blocks measuring
traffic in fixed byte steps (64 B/s doubling — Bytes/KB increments):

- **Yellow (Tx)** grows from the **left edge toward the center**;
  **blue (Rx)** grows from the **right edge toward the center**.
- The **center line is zero**: uneven traffic opens a gap around the middle;
  balanced traffic (equal in and out) reads as two halves meeting at the
  center.
- Each side is scaled to the busiest process on its side, so the bar always
  uses the full range.

### Summary cards

↓ Total received · ↑ Total sent · Active apps · Busiest app.

### Marking importance

**Right-click a row → Mark importance: High / Medium / Low / Clear.**
Marks are shown as a colored dot on the process (red = high, yellow =
medium, gray = low) and persist across restarts. Use them to keep an eye on
the programs you care about.

### Tracking a process

**Right-click → Track network activity** begins recording that process's
traffic history. The **properties sidebar** (select the row to open it)
then shows:

- live ↓/↑ rates and open connections,
- a **connection-frequency chart** — one bar per sample, height = that
  interval's total traffic,
- a **pattern verdict** with its evidence, e.g.
  *regular-intervals — active in 20 of 24 samples at a steady 4 s cadence*,
  *telemetry-like — steady small uploads (median 2.1 KB/s) — pattern, not
  proof*, or *irregular-spikes — 4 of 20 samples, bursts ≥ 3× median*.

**Stop tracking** from the same menu when you're done. Categories are
heuristics computed from the tracked window — they describe measured
behavior and are never proof of intent.

---

## 9. Peripherals

Everything connected: **USB device cards** (name, manufacturer, USB ID,
bus/port, speed, removable badge) and **sensor chips** (temperatures, fan
speeds, CPU frequency span, GPU busy). **Refresh** re-scans after plugging
new hardware. Chips for sensors a machine doesn't have simply don't appear
(a VM shows an empty page — that is normal).

---

## 10. Logs

The systemd journal viewer: pick a **preset** (system, auth, applications,
kernel), optionally filter by unit or priority, set the line count, and
**Load**. Entries render with severity coloring; an empty result states
"no entries match" plainly. Saved views and frequency analysis arrive with
the next Logs releases.

---

## 11. Settings

| Setting | What it controls |
|---|---|
| Refresh interval | sampler cadence (0.5–5 s; default 2 s) |
| Scope chip (Processes) | which processes the table lists by default |
| Kernel threads | show/hide kernel worker threads |
| Sort + column widths | persisted per session |
| **Recalibrate baseline (~6 s)** | re-measures this machine's idle noise floor and refreshes the performance thresholds the zone colors use |

Settings live in `~/.config/linprocman/` and are validated on load — a
corrupt file falls back to defaults rather than crashing.

---

## 12. The system tray icon

Closing the window **hides it to the tray** — the app keeps sampling so its
history keeps filling. The tray menu offers **Show / Hide** and **Quit**
(Quit is the real exit). Left-click toggles the window. If no tray backend
is available the app logs it and runs without the icon — everything else
works.

---

## 13. Understanding the colors

Color is **always a threshold statement**, never decoration:

- **Green** — nominal: the metric is within its healthy range.
- **Yellow** — elevated: crossed the warning threshold.
- **Red** — high: crossed the critical threshold.
- **Blue/yellow in the Network bars** — the classic traffic code:
  blue = received (Rx, right side), yellow = sent (Tx, left side).

Thresholds are **calibrated to your machine**: on first run the app measures
your idle noise floor and derives the warning/critical points (Settings ▸
**Recalibrate baseline (~6 s)** re-runs it). This box is fixed — only the
fill inside a bar or card ever moves.

---

## 14. Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+F` | focus the process filter box |
| `Ctrl+R` | refresh now |
| `F5` | pause/resume live updates |
| Double-click (Processes band card) | open the Basics view |
| Click (Graphs mini-chart) | open that metric's detail page |

---

## 15. Where your data lives

| Path | Contents |
|---|---|
| `~/.config/linprocman/settings.json` | preferences, column set, calibration |
| `~/.config/linprocman/netwatch.json` | your importance marks |
| `~/.local/state/linprocman/linprocman.log` | rotating app log (1 MiB × 3) |

All offline: the app reads `/proc`, `/sys` and the local journal and makes
**no network connections of its own**.

---

## 16. How the numbers are made (honesty notes)

- **Process CPU/memory** come from `/proc` — kernel-exact.
- **Per-process network rates** are *socket-owner attribution*: the app
  watches which processes hold network sockets and splits each interface's
  measured traffic proportionally. The kernel cannot report per-process
  bytes without root/eBPF, so the page labels it as an estimate. Restricted
  processes (other users, sandboxed) show lock + "—".
- **Pattern verdicts** (regular-intervals, telemetry-like, …) are
  *heuristics computed from the tracked window* — they describe measured
  behavior and are never proof of intent.
- **Disks** reads `/proc/diskstats` and `statvfs` — kernel-exact.

---

## 17. Troubleshooting

| Symptom | Explanation / fix |
|---|---|
| A killed process stays listed as "Z" | it's a zombie — its parent hasn't collected it yet. The status line says so; it disappears when the parent reaps. |
| Network rates show "— 🔒" for some apps | their fd table is restricted (Yama). The app never guesses. |
| Network page lists many idle rows | any process holding sockets lists; sort by Total/s descending to see the talkers. |
| Bars all show "—" right after launch | the first samples land within a second or two. |
| Tray icon missing | a tray backend was unavailable at launch — the app logs it and continues; all other features work. |
| The window seems frozen | it isn't the r065 bug — confirmations are inline bars now. If a modal ever appears stuck, press Esc. |
| Something else | check `~/.local/state/linprocman/linprocman.log` — the app logs every failure with context. |

---

*LinProcessManager — LinProcessManager is released under its repository
license; see the About page. This manual covers the application as of
2026-09-28.*
