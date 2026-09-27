# Task 007 — Phase 4.5: Variant-2 metric band + top-10 drill-downs + Basics page

Phase: 4.5 (docs/modules/metric-band-basics.md — THE SPEC, operator-approved
Variant 2)   Branch: task/007-band-basics (checked out)
Dispatcher: ZCode (r059)  Executor: Claude Code, headless, acceptEdits

## Goal

Build the operator-selected metric band on the Processes page (six
continuous-bar gauges below the title, replacing the text strip), the
click-through top-10 contributors popover with drill-downs, and the new
read-only Basics sidebar page. The strip's information moves into the
band; the band's numbers are clickable.

## Read first (binding)

- docs/modules/metric-band-basics.md — THE SPEC (gauge table incl. honest
  Network/Disk drill language, drill model, Basics page, ring law).
- docs/modules/process-table.md — metric-band section + existing strip code
  you replace.
- docs/modules/sampling-pipeline.md — frozen schema/system section.
- docs/build-principles.md + AGENTS.md (auto).

## Scope (touch nothing else)

- EDIT src/pages/page_processes.py — replace the text strip with the
  six-gauge band (six compat ChartArea DrawingAreas + a values row);
  gauge click → top-10 popover (compat menu); keep text strip class as
  the compact fallback behind `settings["basics.compact_strip"]=false`
  default false → band shown. Scroll-to-select for drill rows.
- NEW  src/pages/page_basics.py + registration (sidebar "Basics", above
  About; content_area wiring) — large gauges + top-contributor lists.
- NEW  src/modules/manager_rank.py — pure ranking/roll-up functions:
  top-N per metric, ancestry roll-up (walk ppid within snapshot),
  unit roll-up. UI-import-free, fixture-tested.
- EDIT tests/ — ranking/roll-up/gauge-zone units, click→select round-trip,
  empty/degraded states (Network empty-state, Load "—"), band layout test.
- EDIT resources/css/style.css — band/gauge styles per mockup K variant 2.

## Rules (verbatim)

1. Data only from snapshots (boundary law); ranking in manager_rank is
   pure and fixture-tested; no new sampling, no extra threads.
2. Honest empty-states verbatim from the spec: Network drill
   ("per-process network not available from /proc…"), Load gauge "—"
   until loadavg joins the readers; Disk drill labeled "top
   writers/readers by throughput (bytes/s) — not device %".
3. Zone colors via the page's `_cap_zone`; arrows per r056; ticks at
   60/85 (Variant 2). Network bar auto-scale ceiling = 2× trailing max,
   floor 1 MB/s, ceiling shown in caption.
4. Sparklines (Basics): `(ts, value)` + `from_backoff` exclusion + gap
   rendering — the ring law; interim local deque implements the same.
5. All GTK via compat seams (raw-import + banned-API gates are LIVE);
   popovers via compat/menu; cairo via compat/charts ChartArea.
6. Offline, no subprocess, no pip, no claude-named files. No Bash —
   write code + Report; ZCode runs everything.
7. Keep the r058 close-review fixes intact (debounced width saves,
   visible_count strip semantics — strip semantics now live in the band).

## Acceptance (ZCode verifies)

1. pytest + live tier green; gates green.
2. LIVE on :0: band renders six gauges with real values (screenshot
   pixel-verified); clicking CPU gauge opens the top-10 popover with real
   process names; clicking a row selects it in the table.
3. Basics page navigates from the sidebar, shows large gauges + top lists.
4. Network drill shows the honest empty-state; Load gauge "—" (or real
   value if you also add the loadavg reader — out of scope, "—" expected).
5. git diff touches only Scope.

## Report

Markdown: file map; gauge↔schema mapping table; drill/breadcrumb notes;
Basics build notes; deviations; open questions.

## Out of scope

loadavg reader addition (ZCode/sign-off gate), per-process network
research (backlog I9), actions wiring on Basics, telemetry, tree view.
