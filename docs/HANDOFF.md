# linprocman — Handoff (2026-09-27 machine restart)

## 1. State at handoff

- **HEAD:** `a27198e` on `main`, working tree clean. All work through r079 is committed.
- **Tests:** **239 + 5 green** (239 unit/fixture + 5 opt-in `-m live` tier), passing on `main` throughout the last cycle.
- **Phases shipped:** Phases **1–5** complete and live-verified.
  - Phase 1 — data core (`procfs.py`, `sysfs.py`, launcher, nav shell) — merged `7e9e05a`.
  - Phase 2 — sampler + live flat table (diff-in-place, sort/filter/scope, settings skeleton) — merged `ad3279d`, phase-2 close `9bb8496` + backup `20260926-194655`.
  - Phase 3 — actions & safety (signals, renice, affinity, group termination) — merged `3ee141d` (+ r074 group terminate, r075 corrections).
  - Phase 4 — tree/details plus the 4.5 metric band + Basics page.
  - Phase 5 — Graphs hub (supersedes Resources), 7 mini-charts + per-metric detail pages, multi-series charts, first-run performance-threshold baseline.
- **Packaging/desktop integration:** `install.sh` (git-checkout install, `--uninstall`), program-menu `.desktop` entry, hicolor icon set 16–512, window `_NET_WM_ICON`, and system-tray icon are all in place and live-verified.
- **Not yet started:** Phase 6 (Disks build-out), Phase 7 (Logs engine — large), Phase 8 (ship/installer tag). Preview pane / extended column set (process-preview module), Peripherals, and Telemetry Watch remain design-only.

## 2. Everything since the last backup (verbose, per-item)

Backups taken so far: phase-2 close `20260926-194655`, chart-upgrade `r070-era`,
r071 baseline fixes, and r074 group termination. Everything after the r074
backup (r075 corrections, r079 layout fixes) is in git on `main` but not yet
in a tar backup — the restart-close backup below covers it.

- **r059 — Metric band + Basics shipped.** Operator selected Variant 2 (continuous bars, threshold ticks, scale captions — mockup K). Six-gauge band replaces the text strip (compact strip kept behind a settings key). CPU gauge click → ranked top-10 popover with Group-by-parent-tree / Group-by-unit drill-downs + breadcrumb. New Basics page (large gauges, top contributors, click-to-jump). Spec `docs/modules/metric-band-basics.md` adversarially reviewed ($0.47); Network drill re-scoped to permanent empty-state (no /proc per-PID source), Disk drill relabeled "top writers/readers by throughput." Task 007 executor $6.37; 178+5 tests. Deviations accepted: popover rows as menu items (seam limit → backlog D6), gauge-click on ChartArea only.
- **r060 — Graphs feature spec + card-fix + Swap/Load move.** `docs/modules/graphs-hub.md` authored. **Band card pulsing defect fixed at root** — pinned value/caption text widths so requisition no longer drives card size; Pango re-exported via compat `gtk_env`. Swap+Load removed from the Processes band (Basics keeps six). Mockup L added (twelve total). Live journal caught the Pango import gap the tests missed.
- **r061 — Graphs feature shipped.** Sign-off gate SIGNED the loadavg reader (decode/read split, None guards) and `manager_history` rings (lock-free, main-thread writes). Task 008 executor $10.57: Graphs sidebar + hub grid of 7 live mini-charts (CPU/Memory/Swap/Disk/Network/Pressure/Load), per-metric detail pages (window selector 1m/5m, zone bands, current/min/avg/max, top contributors → Processes selection, breakdowns), Basics sparklines on shared rings. **Resources page retired** per checklist; cross-refs repointed to the Network graph. 219+5 tests; hub + CPU detail live-verified. Load shipped with real data (contract override of doc gating).
- **r062 — Graphs submenu + Basics relocation.** Sidebar restructured: Graphs is a group row (navigates to hub) with Basics as an indented submenu child (SUBMENUS map + nav-sub indent styling). Standalone Basics button removed. 214+5 green. **Probe lesson:** a second `LinprocmanApplication` with the same application_id hands off to the running primary and exits immediately — stop the service before in-process drives (the single-instance handoff trap; see §6).
- **r064 — Native logging.** `src/log.py`: stdlib logging bootstrap (offline, mandate-safe) — rotating file handler at `~/.local/state/linprocman/linprocman.log` (1 MiB × 3), severity copy to stderr so journalctl still works for the systemd unit, namespaced child loggers. `log_exception()` writes the traceback AND appends a one-line entry to `.zcode/memory/issues.md`; `issue()` records non-exception observations. `main.py` bootstraps logging before other imports and wraps `do_activate` with exception capture. 214+5 green.
- **r065 — Operator hang incident resolved (logging verified in the fire).** Right-click → Kill hung the app. Root cause: floating modal confirm window mapped BEHIND the active window (GNOME focus-stealing prevention) while holding a modal grab — input-blocked, looked frozen. Fixed with an **inline confirmation bar inside the page** (no second window; cannot be stacked away); floating dialogs keep DIALOG type-hint + center-on-parent for other uses. First live exercise of r064 logging — it captured the exact failure path. Live proof: inline bar → confirm → real SIGKILL → PID gone. Recorded RESOLVED in issues.md.
- **r067 — Sort-order defect resolved.** Sorting by name reshuffled every tick: the "process" header key was unknown to `set_sort` and silently fell back to a live CPU sort; the visible Process cell also holds Pango markup. Fix: "process" now maps to a hidden stable `COL_NAME_SORT` (casefolded name) with its own comparator; regression test proves alphabetical order holds under CPU/state churn.
- **r068–r070 — Chart visual upgrade + Basics split cards.** Task 009 executor $8.62: shared multi-series render helper in the charts seam (legends with live values, area fills, gridlines, hover crosshair via motion controller, gap-honest None handling); Network rx/tx + CPU total/per-core + Disk read/write multi-series; per-core legend click-to-isolate; Basics split cards (fixed gauge left; top contributing processes right with proportional mini-bars, click-to-select). **r070 operator refinement:** gauge delta arrows (▲▼·) removed — threshold-colored values only; trend lives in the charts. 234+5 green; merged; backup at phase close.
- **r071 — Performance thresholds + first-run baseline.** `docs/modules/perf-thresholds.md` + `src/modules/manager_baseline.py`: first-run capture (specs — 12 cores / 12.58 GB / SSD measured here; idle CPU noise floor p90 over ~6 s) feeds `derive()` formulae producing machine-specific alert thresholds (this box: cpu 20.2/55, mem 59.6/84.6, swap 5/10, disk 42/60, load_red 18). Thresholds provider consulted by zone helpers (fixed 60/85 defaults when absent); stored in settings.json; Settings ▸ Recalibrate re-runs capture in a background thread. **Bounding-box policy codified** in build-principles §5b (recurred r060 band, r071 Basics): the box is fixed; only the visual inside moves. Adversarial review ($1.70) caught a P0 pair pre-live — idle sampling read nonexistent procfs keys (every machine would derive identical thresholds) and the persisted baseline was never re-applied after first run; both fixed. 234+5 green; baseline live-captured on this machine.
- **r072 — Packaging + tray + window icon.** `install.sh` (run from git checkout): dependency check, `~/.local/bin` launcher, program-menu entry (`linprocman.desktop`, `StartupWMClass=linprocman`, Categories System/Monitor), hicolor icon set 16–512 rendered from the pulse mark with PIL (deterministic, librsvg-independent), `--uninstall` preserving config+logs. **Tray icon:** `src/ui/compat/tray.py` fallback chain **XApp → AyatanaAppIndicator3 → Gtk.StatusIcon** (all optional; absent → logged, never fatal). Window `_NET_WM_ICON` 128×128 via GdkPixbuf (ALT+Tab/taskbar). Both verified live on the session bus and via xprop. Tray lives in the compat layer per the import law.
- **r073 — Launcher data-flow + submenu fixes.** ROOT CAUSE of "no performance metrics": the r072 tray refactor swallowed `sampler.start()` into the tray's `_toggle_window`, so every menu/launcher launch produced a live tray icon but NO data flow. Gate restored in `_do_activate`; `_toggle_window` is now a pure visibility toggle. Second defect: r073 CSS used web-only properties (`margin-left:auto`, `transition`) — invalid in GTK3 CSS, the parse failure disabled all component styling on launcher launches. Both fixed. Submenu: group click expands children downward (caret rotates), second click collapses, child click expands parent. 234+5 green; launcher-path live-verified.
- **r074 — Group termination.** End group / Kill group in the process context menu — terminates a process's ENTIRE descendant tree. `manager_actions.descendant_keys` (BFS children-first over fresh `procfs.snapshot_procs`, cycle-guarded) + `group_terminate` (probe-fresh guard per member, SIGTERM batch → liveness verify with grace polls → SIGKILL escalation → final verify) returning a summary dict; page renders via `group_summary_text`. Boundary law held (page never touches procfs). Live drive on a real 3-process tree: 3/3 terminated. 239+5 green.
- **r075 — Operator corrections cycle.** (1) Graphs submenu indicator: group buttons rebuilt with an HBox child so the caret sits right-aligned persistently (`Gtk.Image.set_pixel_size` does not scale SVG-file images — pixbuf-at-size used, matching the logo path); expansion persists across navigation. (2) Header columns regained right-click column-chooser popover (checkbutton per column, persisted) via `get_path_at_pos` None-discrimination; row right-click keeps the process menu. Live-verified corrected dark palette with live data. 239+5 green.
- **r079 (HEAD `a27198e`) — layout/persistence fixes.** `max_width_chars` conversion on the band + Basics cards (fixes the operator overflow screenshot), proportional column-fit on window resize (debounced), and settings persistence of column widths.

## 3. Run and verify after restart (exact commands)

Run all from the repo root `~/projects/linprocman`.

```bash
# 1. Confirm state
cd ~/projects/linprocman
git status                 # expect: clean
git rev-parse HEAD         # expect: a27198e...

# 2. Full test suite (offline; system python3)
python3 -m pytest tests/ -q
#   expect 239 passing

# 3. Opt-in live tier (touches the real kernel; +5)
python3 -m pytest tests/ -q -m live
#   expect 5 passing

# 4. Launch the app on the live display
python3 src/main.py
#   verify: populated process table, six-gauge band with live values,
#   Graphs hub + Basics submenu, dark palette with contrast.

# 5. Runtime journal check (logging is part of verification since r057/r064)
journalctl --user -u linprocman-app        # systemd unit path
#   OR read the rotating file log directly:
#   ~/.local/state/linprocman/linprocman.log

# 6. Backup (s009 wrapper, operator command)
bash ~/projects/Zai-ZCode/s009_backup_project.sh /home/user/projects/linprocman -m "post-restart verify" 
```

**Before any in-process GUI drive:** stop the running service first (single-instance handoff, §6), otherwise a second launch silently hands off to the primary and exits.

**No-raise window capture** (GNOME focus-stealing-prevention blocks `wmctrl` raises): `xwd -id <win>` + the in-repo XWD parser (PIL lacks XWD; no `convert`/netpbm on this box).

## 4. Open defects and watch items

- **Sidebar highlight desync on programmatic nav** (r061/r062) — pre-existing limitation, logged to backlog; the nav path itself verifies True.
- **GTK3 row-hover limitation** (r054) — per-row hover unavailable by default (whole-widget `:hover` flashes); deliberately omitted. Do not re-add.
- **librsvg is optional on Debian family** (r054) — every SVG asset needs a png fallback chain; installer icons already render via PIL for this reason. `Gtk.Image.set_pixel_size` does NOT scale SVG-file images — use pixbuf-at-size (r075).
- **GTK3 CSS is not web CSS** (r073) — `margin-left:auto`, `transition`, and similar web-only properties silently break the ENTIRE stylesheet parse. Never add them.
- **Runtime-only bug class** (r057, r073) — several NameError/AttributeError defects (`log`, `Gtk`, `css`, `GLib`, `os`, `procfs`, `set_child`, `set_xalign`) surfaced only at first live snapshot / `do_activate`, never in tests (see issues.md tail). Always launch the app and read the journal after import-touching edits; tests alone do not catch startup crashes because the executor cannot run the app.
- **issues.md tail** carries recent NameError/AttributeError entries from the r072–r075 launcher/submenu churn — all resolved by r073/r075, but keep the ledger in mind when triaging.
- **Dead-code deletions** are ZCode's job (`git rm -f`) — the executor's acceptEdits mode has no Bash and cannot remove files. Check "dead code" for SIDE EFFECTS before deleting (the r052 ThemeManager loader lesson).

## 5. Queued work with precedence

1. **Task 010 — preview pane + chart double-click pages (Phase 4 remainder, next up).** The `process-preview` module (`docs/modules/process-preview.md`): extended 22-column chooser, process preview pane (mockup J), row context menu extensions, and per-process network attribution via the r053 socket-owner-attribution design (exact for own processes, proportional attribution, "—" under Yama, still no eBPF/root). Pair with **chart double-click → detail pages** so a gauge/mini-chart opens its per-metric page directly. Same pattern per module doc (Z contract → C execute → Z verify pixels). This is the immediate next executor dispatch.
2. **Disks build-out (Phase 6).** `docs/modules/disks-filesystems.md` → `page_disks.py`: per-device diskstats I/O rates, per-mount usage, live plug/unplug events. `statvfs` hang risk on stale mounts is a known trap (handle off the critical path).
3. **Peripherals feature.** Sensors/hardware surfacing via `sysfs.py` (hwmon temperatures, cpufreq, AMD GPU chip, fan chips) — the sysfs-data module; fold in the promoted r042 innovations (fan chips, temperature/frequency chips) that Phase 5 did not fully surface.
4. **Telemetry Watch (Phase 5/7 surfacing).** `docs/modules/telemetry-watch.md` → `manager_telemetry.py` (concept only): unattended-egress scoring from /proc-only signals, fingerprint rules, allow/deny persistence, transparent 0–100 scoring with named contributing signals. Verdict axis is measured reality (Quiet / Chatty / Unattended-egress / Telemetry-fingerprinted) — reserve the word "telemetry" for rule matches (r055 adversarial correction). Mint's own agents pre-seeded allow-listed.

Beyond these: **Phase 7 — Logs engine** (large, size like phases 1–2: journalctl argv-contract engine, four presets, follow/tail, search + time-jump, priority coloring, saved views + flags, frequency analysis, export) and **Phase 8 — Ship** (version stamp, `.deb` spec via dh_python3, v1 tag).

## 6. Operational notes

- **Single-instance handoff trap.** `LinprocmanApplication` uses a fixed `application_id`. Launching a second instance while one is running hands off to the primary and exits immediately with empty output — it does NOT start a fresh process. **Stop the running service before any in-process drive or probe** (r062).
- **Tray via Ayatana.** Tray icon resolves through the compat chain XApp → **AyatanaAppIndicator3** → Gtk.StatusIcon; all optional, absence is logged not fatal. Tray lives in `src/ui/compat/tray.py` per the import law. Do NOT let the tray refactor swallow the `sampler.start()` gate again — it belongs in `_do_activate`, and `_toggle_window` must stay a pure visibility toggle (r073 root cause).
- **Backups: `s009`** — operator command, run at every phase/feature close. Backups on record: phase-2 close 20260926-194655, chart-upgrade, r071 fixes, r074 group termination. Run one after the post-restart verify.
- **Logging paths.** File log `~/.local/state/linprocman/linprocman.log` (rotating, 1 MiB × 3) is the authoritative record; stderr copy feeds `journalctl --user -u linprocman-app`. Exceptions also append a line to `.zcode/memory/issues.md`.
- **Executor collaboration.** ZCode plans/verifies; Claude Code executes on task branches via `.zcode/tasks/NNN-*.md` contracts under `--permission-mode acceptEdits` (every dispatch AND follow-up needs the flag or writes silently deny). Executor never merges, never edits binding docs, never records ledger entries, cannot `rm`/run Bash. Each dispatch needs its own session — `--session-id` resume fails ('already in use') on held sessions; fallback is a fresh session with prior conclusions embedded. Co-draft contracts in a consult session before dispatch.
- **Verification chain (standing):** scope diff → `pytest` → AST import-allowlist + subprocess argv-allowlist + banned-API gates → no-claude-path sweep → pixel verification on `:0` (with no-raise XWD capture) + runtime journal read. Banned-API sweep is scoped to UI trees (plain `set.add` is legitimate there — union it to avoid the false positive).
- **Mandates that gate every change:** offline (no network imports under `src/`, grep-gated), assets only from `~/projects/assets/icons` (copied in, never referenced), system packages + direct `python3` launcher (no pip/venv), core modules (procfs/sysfs/sampler/actions) stay UI-import-free and headlessly testable, raw `from gi.repository import Gtk` banned outside `gtk_env.py`. changelog.md is append-only (old_string = the last line; the append-mistake has happened three times).