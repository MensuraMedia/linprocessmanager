# Task 008 — Phase 5: Graphs hub + detail pages (with signed data prerequisites)

Phase: 5 (docs/modules/graphs-hub.md — THE SPEC; resource-graphs.md = ring law)
Branch: task/008-graphs (checked out)
Dispatcher: ZCode (r061)  Executor: Claude Code, headless, acceptEdits

## Goal

Build the Graphs sidebar feature: hub grid of seven live mini-charts,
per-metric detail pages (CPU/Memory/Swap/Disk/Network/Pressure; Load gated
but scaffolded), the signed loadavg reader, and the shared manager_history
ring store. Swap and Load charting lands HERE; the Resources sidebar entry
retires per the graphs-hub §3 checklist.

## Read first (binding)

- docs/modules/graphs-hub.md — THE SPEC (hub grid, detail skeleton, window
  selector capped 1m/5m, honest empty-states, Resources-retirement checklist).
- docs/modules/resource-graphs.md — ring law ((ts,value), backoff-excluded,
  gaps as gaps) + sensors-chip ownership note.
- docs/modules/metric-band-basics.md §3 — Basics consumes the same rings.
- SIGN-OFF (C-review r061): loadavg SIGNED with decode/read split +
  never-raise None guards; rings SIGNED lock-free (main-thread writes only).

## Scope (touch nothing else)

- EDIT src/modules/procfs.py — decode_loadavg(raw) + system_loadavg(proc_root)
  per sign-off (split pattern, len<5 or missing '/' → None fields, no raise)
- EDIT src/modules/manager_sampler.py — Readers + default_readers +
  _build_system: system.load added (NO _RawState/delta carry — instantaneous)
- NEW  src/modules/manager_history.py — ring store: insert(series, ts,
  value, from_backoff=False) skipping backoff at insert; slice(series,
  window_s); last(series); maxlen from period (~5 min); main-thread-writes-
  only documented
- NEW  src/pages/page_graphs.py — hub grid (7 mini-charts, zone-tinted
  values, click-through); Resources entry retired per checklist §3
- NEW  src/pages/graph_details.py — GraphDetailPage base + CPU/Memory/
  Swap/Disk/Network/Pressure pages (+ Load scaffolded, gated "—" until
  schema lands — per spec it does NOT ship this task: loadavg reader IS in
  this task, so Load page DOES ship with real data. Build it.)
- EDIT src/pages/page_basics.py — sparklines consume manager_history rings
  (replace interim deque; same contract)
- EDIT src/ui/sidebar.py, src/ui/content_area.py, src/pages/__init__.py,
  src/pages/page_settings.py — per graphs-hub §3 checklist
- EDIT src/pages/page_processes.py + page_basics.py — repoint the two
  "interface totals on Resources" cross-refs at the Network hub card
- EDIT resources/css/style.css — hub/detail styles (mockup L)
- EDIT tests/ — loadavg fixtures (normal/short/no-slash), ring units
  (insert/slice/backoff-exclusion/eviction), hub render, detail stats
  (min/avg/max over slice), breakdown rows, click-through, retirement
  assertions (no Resources nav entry; Graphs present)

## Rules (verbatim)

1. Boundary law: pages consume snapshots/rings only.
2. Ring law: (ts,value), backoff-excluded at insert, gaps render as gaps;
   window selector offers 1 m / 5 m ONLY.
3. All GTK via compat; raw-import + banned-API + deprecation gates LIVE.
4. Zone colors via shared capacity helper; arrows per r056; Network drill
   empty-state text verbatim from spec.
5. Settings: no new keys beyond existing patterns (window selection is
   per-session, not persisted).
6. Offline, no subprocess, no pip, no claude-named files. No Bash.
7. sampling-pipeline.md §Interface line: append `load` to the system dict
   enumeration (doc edit IN scope for this task, one line).

## Acceptance (ZCode verifies)

1. pytest + live tier green; gates green.
2. LIVE: Graphs hub renders 7 mini-charts with real values (xwd pixel
   proof); CPU detail page shows big chart + stats + contributors +
   per-core rows; Load page renders real load1 vs ncpu.
3. Resources entry gone; Basics sparklines still render across a restart+
   10s run (rings populated).
4. git diff touches only Scope.

## Report

Markdown: file map; ring API as built; hub/detail notes; deviations;
open questions.

## Out of scope

Per-process network attribution (backlog I9), telemetry, preview pane
(task 009), 15m/session windows (needs designed long-ring tier).
