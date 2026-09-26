# Task 006 — Phase 3: actions & safety (the app becomes controllable)

Phase: 3 (concept §9; docs/modules/actions-permissions.md)   Branch: task/006-actions (cut from main)
Dispatcher: ZCode (r058)  Executor: Claude Code, headless, acceptEdits

## Goal

Wire the action surface: end/kill/stop/continue/hangup/custom-signal,
renice, and the process context menu — all guarded, confirmed, and
error-contracted exactly per the module doc. After this task the app can
actually manage processes, not just watch them.

## Read first (binding)

- docs/modules/actions-permissions.md — THE SPEC (fresh-stat guard, confirm
  matrix, corrected renice rule, errno contract, "signal sent" wording).
- docs/modules/process-preview.md §3 — context menu item list + disabled-
  with-reason pattern.
- docs/modules/process-table.md — selection key lists (multi-select).

## Scope (touch nothing else)

- NEW  src/modules/manager_actions.py — all actions per spec
- EDIT src/pages/page_processes.py — context menu (compat menu seam),
  action handlers, confirm dialogs (compat dialogs seam), bulk selection
  support, status-line result rendering
- EDIT tests/ — guard/confirm/errno/bulk/zombie units + fixture tests
- EDIT .zcode/tasks/BACKLOG.md items only where scope naturally touches

## Rules (verbatim)

1. Guard: read /proc/<pid>/stat fresh at click time via procfs.parse_stat;
   compare starttime; mismatch → "Not sent — PID <n> exited and the PID
   was reused" (never send). Snapshot fallback only if fresh read fails.
2. Wording: "SIGTERM sent to <name> (<pid>)" — NEVER "Ended". Bulk:
   "SIGTERM sent to N processes · M failed (EPERM): <names>".
3. Confirm: Kill always; End always by default (settings key
   `end_confirm_own`, default true); bulk shows ONE summary dialog.
4. renice: own processes may only INCREASE niceness; others' always EPERM —
   pre-check and say so in the dialog before attempting.
5. affinity: os.sched_setaffinity, own processes; others → disabled item
   with reason.
6. zombies: items disabled with "no effect on a defunct process".
7. All dialogs via compat/dialogs (window-based, close() only); menus via
   compat/menu (Gio.Menu model); accels via compat/events. NO gi import,
   NO pack/add/destroy outside compat (gates are live).
8. Errors: errno text verbatim in the status strip (existing markup
   helpers); never a crash, never silent.
9. No Bash. Write code + Report.

## Acceptance (ZCode verifies)

1. pytest green incl. new action units (guard mismatch → no send + message;
   confirm matrix; renice permission table; bulk summary; zombie disable).
2. Gates green; live tier green.
3. LIVE on :0 (ZCode drives): select own process → End → confirm dialog →
   accept → process exits (ZCode verifies PID gone); EPERM path on a root
   process → exact errno text in strip. Screenshot evidence.
4. git diff touches only Scope.

## Report

Markdown: file map; guard/confirm flow notes; menu wiring; deviations;
open questions.

## Out of scope

Preview pane, tree view, Frequency, journal-for-unit wiring (Phase 4/7 —
menu items may appear grayed with "Phase 4" reason), telemetry.
