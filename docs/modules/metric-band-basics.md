# Module doc — Metric Band & Basics drill-down (`page_processes.py` band + `src/pages/page_basics.py`)

Part of the linprocman modular docs. Siblings: [process-table.md](process-table.md) ·
[process-preview.md](process-preview.md) · [sampling-pipeline.md](sampling-pipeline.md) ·
[resource-graphs.md](resource-graphs.md) · [telemetry-watch.md](telemetry-watch.md).
Overview: [../process-manager-concept.md](../process-manager-concept.md).

Status: spec approved for build (r059). Operator selected **Variant 2 —
continuous bars with threshold ticks and scale captions**
([mockup-k-metricbars.html](../mockups/mockup-k-metricbars.html), variant 2
in the render); variants 1 and 3 remain documented alternatives, not
scheduled. New operator requirement on top: **click a gauge → top-10
processes responsible for that metric → subsequent drill-downs**, housed in
a new **Basics** sidebar page when a full-page view is warranted.

## 1. The band (Processes page, below title — Variant 2)

Six gauges, equal width, one cairo DrawingArea each (via
[compat/charts](compat) `ChartArea`), fed by the existing snapshot stream —
no new sampling, no timers beyond the sampler:

| Gauge | Value | Bar source (frozen schema) | Scale |
|---|---|---|---|
| CPU | system %, delta arrow | `system.cpu.pct` | fixed 0–100; ticks at 60/85 |
| Memory | % used | `system.mem` total/available | fixed 0–total; caption "x GB used / total" |
| Swap | % used | `system.mem` swap fields | fixed 0–total |
| Disk I/O | device util % (busiest) | `system.disks` max util | fixed 0–100; caption "busiest: <dev>" |
| Network | ↓+↑ MB/s | `system.net` summed rx/tx rates | **auto-scale ceiling** (2× trailing max, floor 1 MB/s), caption shows ceiling |
| Load | 1-min loadavg* | — *not in the frozen schema* | fixed 0–ncpu; caption "cores: N" |

\* Load needs `btime`-style addition: `/proc/loadavg` joins the reader
table (procfs-data.md) through the sign-off gate with Phase-5 schema
batch — until then the Load gauge renders "—" (probe-first rule).
Threshold ticks at 60/85 with zone coloring per `_cap_zone`; delta arrows
per r056 (▲red up · ▼green down · gray flat). Click behavior in §2.

## 2. Click-through (current: double-click → Basics; r090 restatement)

The documented design was: single-click → Top-10 popover, double-click →
Basics. History: the r059 popover shipped; r070 removed the delta arrows;
r081 replaced the popover with direct navigation but on SINGLE click (a
deviation — too easy to fire while scanning the table) and deleted the
popover machinery; r090 restored the documented DOUBLE-click trigger — a
double-click on any gauge now navigates to the Basics page (the Graphs
submenu auto-expands; sidebar highlight moves). The r059 popover machinery
remains deleted (git history preserves it). Baseline per gauge:

| Gauge | "Responsible" ranking | Source |
|---|---|---|
| CPU | top 10 by current `cpu_pct` | snapshot records (existing) |
| Memory | top 10 by `mem_rss` (+ swap shown) | records |
| Swap | top 10 by `mem_swap` | records |
| Disk I/O | top 10 **writers/readers by throughput (bytes/s)** — explicitly NOT the gauge's device-util metric (they are orthogonal: small random IO drives util at low bytes; pagecache writes may never touch the device). Drill caption states the distinction; the two must not be summed | records |
| Network | **no per-process drill** — /proc exposes no per-PID bandwidth; honest permanent empty-state ("per-process network not available from /proc — interface totals on Resources") | adversarial r059: this is not a deferred schema batch (no reader exists to back it); socket-attribution research is a separate backlog item (process-preview §4) before any promise is made |
| Load | top 10 by cpu_pct (same as CPU, caption notes it) | records |
| Processes | not clickable (informational) | — |

Each row: rank, process name (+unit badge), owner, contribution value
(color-coded by that gauge's zone scale), and **drill-down affordances**:

1. **→ parent set:** "show with parent tree" — re-ranks the contribution
   **aggregated by ancestry** (child rolled into its nearest visible
   ancestor: firefox + Web Content + RDD = one firefox line). This is the
   first drill-down: raw → grouped-by-tree, because that answers "which
   *app* is responsible".
2. **→ single process:** click a row → selects it in the table (scroll-to
   via `(pid, starttime)`), opens the preview pane section for it.
3. **→ unit view:** rows with a cgroup unit offer "aggregate by unit" —
   the same roll-up keyed by unit (systemd's own grouping).

Drill state is a breadcrumb in the popover header
(`CPU ▸ by process ▸ firefox tree`) with click-to-previous. All rankings
are computed in the model layer from the CURRENT snapshot (pure function,
fixture-tested); nothing new is sampled.

## 3. The Basics cards (now the TOP of the Graphs hub)

r092 (operator): the standalone Basics page and the sidebar submenu are
RETIRED — this section's cards render at the top of the Graphs hub page
(`GraphsHubPage.add_basics_section`), above the chart grid. The spec below
still governs the cards themselves.

A calm, glanceable summary page for the "am I OK?" question — the drill
destination when a popover is too small:

- The same six gauges, large, stacked with 5-minute mini-sparklines —
  **full ring law from day one** (r059 review): `(ts, value)` tuples,
  `from_backoff` samples excluded, gaps rendered as gaps (a hidden window
  must not masquerade as history). Rings are shared via manager_history
  when Phase 5 lands; any interim local deque implements the same
  contract, not a flat value list.
- **Per-gauge "Top contributors" list** (the §2 ranking, persistent view,
  click a row → jump to Processes with that row selected).
- No editing, no actions — Basics is read-only by design (the one-stop
  "system health" page; power features stay on Processes).

## 4. Rules

- Boundary law: the band and Basics consume snapshots only.
- Empty/degraded data: "—" values, never zeros (r039 taxonomy); Network
  pre-Phase-5 shows its landing-note empty state.
- Zone colors + arrows: `_cap_zone` + r056 convention only (no new
  colors).
- Settings: `basics.show_sparklines` (default true) — nothing else new.
- Gates: all live (raw-import, banned-API, deprecation tiers).

## 5. Tests

Gauge value/zone mapping units (per gauge, incl. auto-scale math for
Network), top-10 ranking correctness + tie behavior, ancestry roll-up
(firefox tree collapse), unit roll-up, breadcrumb state machine, Basics
empty/degraded states, click→select round-trip.
