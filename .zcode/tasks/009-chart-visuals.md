# Task 009 — Phase 5b: chart visual upgrade (legends, multi-series) + Basics split cards

Phase: 5b (docs/modules/graphs-hub.md §2b/§3 — THE SPEC; mockup M = the visual contract)
Branch: task/009-chart-visuals (checked out)
Dispatcher: ZCode (r068)  Executor: Claude Code, headless, acceptEdits

## Goal

Upgrade the chart renderer from single-polyline sparklines to proper
multi-series charts with legends, fills, and crosshair — and rebuild the
Basics page as split cards (gauge left, contributing processes right).
This addresses the operator's live feedback: "no legend markers, missing
lines for different metrics."

## Read first (binding)

- docs/modules/graphs-hub.md §2b/§3 — rendering + Basics split spec.
- docs/mockups/mockup-m-visuals.html + .png — THE VISUAL CONTRACT.
- src/pages/graph_details.py (DetailSpec/series plumbing),
  src/pages/page_graphs.py (hub sparks), src/pages/page_basics.py,
  src/ui/compat/charts.py — the code you upgrade.

## Scope (touch nothing else)

- EDIT src/ui/compat/charts.py — shared render helper:
  `render_series(cr, w, h, points_list, colors, *, fill_primary=True,
  gridlines=True, crosshair=None)` where points_list = ordered series of
  (ts, value) with None as gap markers; zone-band variant for pct charts.
- EDIT src/pages/page_graphs.py — hub cards: legend row + multi-series
  (Network rx/tx; Disk read/write) via the helper.
- EDIT src/pages/graph_details.py — per-page series sets:
  CPU = total bold + per-core thin (shade-stepped palette, click-to-isolate
  via legend); Network = rx + tx; Disk = read + write; Memory = used +
  swap line; Pressure = cpu/mem/io trio (already multi — migrate to helper).
- EDIT src/pages/page_basics.py — split cards per spec §3: left = fixed
  gauge (bar + zone + caption), right = top-4 contributor rows (rank,
  name, mini-bar proportional to leader, value; click → select on
  Processes). Uses manager_rank rankings.
- EDIT resources/css/style.css — legend/row styles.
- EDIT tests/ — render-helper units (gap handling, zone mapping, series
  colors), Basics card structure, hub legends present.

## Rules (verbatim)

1. All drawing via cairo through the charts seam; no GDK pixbuf churn in
   draw callbacks; no new timers.
2. Legends: color chip + label + live value, updated per snapshot; per-core
   legend entries toggle series visibility (no rebuild).
3. Colors: primary from theme accent; series palette shade-stepped
   (r042 rule — no hardcoded 4-color list); rx/down green-family, tx/up
   amber-family per mockup M.
4. Gap honesty: None points break the line (no interpolation) — ring law.
5. Boundary law, offline, no subprocess, no claude-named files, no Bash.
6. Crosshair: motion controller via compat/events; readout drawn on-chart
   (time + value); hidden when pointer leaves.

## Acceptance (ZCode verifies)

1. pytest + live green; gates green.
2. LIVE: Network detail shows TWO labeled lines + legend; CPU detail shows
   total + per-core lines + legend; hub Network card shows two mini-lines
   + legend; Basics cards show bar-left + processes-right (screenshot
   pixel-verified against mockup M structure).
3. Hover crosshair renders on detail pages (screenshot with synthetic
   pointer position via drive script).
4. git diff touches only Scope.

## Report

Markdown: helper API as built; per-page series table; deviations; open
questions.

## Out of scope

New data sources (no new readers), 15m windows, exporters, preview pane.
