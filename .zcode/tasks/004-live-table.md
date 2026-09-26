# Task 004 — Phase 2c: the live process table (the app becomes visible)

Phase: 2c (concept §9; docs/modules/process-table.md)   Branch: task/004-live-table (cut from main)
Dispatcher: ZCode (r052)  Executor: Claude Code, headless, acceptEdits

## Goal

Turn page_processes.py into the real thing: a live, sortable, filterable
process table fed by the sampler — the first user-visible functionality.
This is the payoff task; everything since 001 has been its foundation.

## Read first (binding)

- docs/modules/process-table.md — THE SPEC (typed columns, diff-in-place
  with TreeRowReference keys + move/update/insert/remove order, filter
  suspension, row budget, None→(-1, has_data) translation at the boundary).
- docs/modules/sampling-pipeline.md — Snapshot schema (FROZEN, 20 fields,
  r048 sign-off) + drain_latest()/set_activity_state() contract. The idle
  source that drains is YOURS to install (r046 ruling: table layer owns it).
- docs/modules/persistence-config.md — settings skeleton (schema table).
- src/modules/manager_sampler.py + tests/test_sampler.py — the API you consume.

## Scope (touch nothing else)

- EDIT src/pages/page_processes.py — full build: search entry, scope chips
  (All/My processes/System/Active), typed TreeView columns (Process w/icon+
  unit badge, User, CPU %, Memory, Swap, Disk r/w, Nice, PID, State incl.
  D-state badge), toolbar (pause/resume, refresh-now, interval selector
  0.5–5s), statusbar (N processes, load, kernel-threads-hidden count,
  updated time), keyboard map (Ctrl+F filter, arrows, Enter selects/
  details-placeholder, Ctrl+R refresh, F5 pause).
- NEW  src/ui/process_model.py (or src/modules/manager_table.py — pick the
  starter-consistent location) — ListStore, diff-in-place engine, filter
  wrapper, selection restore by (pid, starttime), row budget ≥5k notice.
- NEW  src/config/app_settings.py — persistence skeleton per module doc:
  load/save with clamping + atomic tmp+rename, XDG path, keys:
  refresh_interval_s, columns.visible/widths, sort, scope_chip,
  show_kernel_threads(false), cpu_normalized(per_core), view_mode.
- EDIT src/ui/dashboard_window.py — wire set_activity_state to window
  is-active/iconified signals (sampler backoff input).
- EDIT src/main.py — construct the Sampler and pass it through (start on
  activate, stop on shutdown).
- EDIT tests/ — process_model units (diff/move/sort/filter/budget/
  translation), settings round-trip + clamping; extend tests/live_gui_walk.py:
  keep-above during walk + assert process ROWS present (count visible rows
  in the model ≥ 10 after 2s on a real system — live check, live marker).

## Rules (verbatim)

1. Consume snapshots ONLY via drain_latest() in ONE GLib idle/timeout
   source you install (per r046 ruling); apply diff-in-place per the spec;
   never read /proc from UI code (raw-import ban + boundary law).
2. None → (-1, has_data) translation happens at your model boundary ONLY.
3. All GTK through ui.compat (raw-import ban is live; banned-API sweep is
   live and scoped to UI trees — pack/add/destroy go through compat
   adapters).
4. Row budget: >5000 visible rows → show top-N under current sort + notice
   row; filter suspended around diff batches (refilter once).
5. Kernel threads hidden by default (toggle chip row); D-state badge;
   zombie rows show "(defunct)" styling — all per spec.
6. Offline mandates, no subprocess, no pip, no claude-named files. No Bash —
   write code + Report; ZCode tests and sends failures back.
7. Details pane is NOT in this task (phase 4) — Enter just selects.
8. Icons: only names from resources/icons/manifest.txt (e.g. magnifying-
   glass, pause-circle, play, arrow-clockwise, clock, user-circle,
   shield-warning, pulse, warning) loaded via the compat icons helper.

## Acceptance (ZCode verifies)

1. python3 -m pytest tests/ -q green (existing + your new units).
2. Gates green (raw-import, banned-API, deprecation tiers).
3. LIVE: app launches on :0 and the Processes page shows REAL process rows
   within 3 s (ZCode screenshots + pixel-verifies; walk's live row-count
   check passes with ≥10 rows).
4. Diff-in-place proven: selection survives a refresh (unit test) and no
   full-rebuild flicker (row-identity test).
5. Settings round-trip: interval/sort/columns persist across restart
   (unit test with tmp XDG).
6. git diff touches only Scope.

## Report

Markdown: file map; how the idle drain is wired; diff engine notes;
keyboard map; deviations (none expected); open questions.

## Out of scope

Details pane, tree view, actions/signals, resources/disks/logs pages,
renice dialogs, PSI banner, sparkline.
