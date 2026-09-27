# Module doc — Graphs hub (`src/pages/page_graphs.py` + per-metric pages)

Part of the linprocman modular docs. Absorbs the rendering half of
[resource-graphs.md](resource-graphs.md) (which remains the data/ring
spec). Siblings: [metric-band-basics.md](metric-band-basics.md) ·
[sampling-pipeline.md](sampling-pipeline.md) · [sysfs-data.md](sysfs-data.md).
Overview: [../process-manager-concept.md](../process-manager-concept.md).

Status: concept approved for build (r060). Operator-mandated: a
**Graphs** entry in the sidebar holding ALL performance charting — a hub
of live mini-charts where **every chart is clickable into its own
dedicated page** for that metric. Swap and Load move here from the
Processes band (r060).

## 1. Sidebar & hub page

Sidebar gains **Graphs** (`chart-line-up` icon, between Resources and
Disks — Resources page is superseded by this feature when it lands; the
sidebar entry for Resources is removed at the same commit). The hub is a
grid of **live mini-charts** (2×3 on ≥1200 px, stacking narrower):

| Chart | Renders | Clicks through to |
|---|---|---|
| CPU | total % area + per-core stacked, 5-min ring | Graphs ▸ CPU |
| Memory | used area + swap line | Graphs ▸ Memory |
| Swap | swap-used area | Graphs ▸ Swap |
| Disk I/O | busiest-device util + r/w rates | Graphs ▸ Disk I/O |
| Network | rx/tx rate lines, auto-scale | Graphs ▸ Network |
| Pressure (PSI) | cpu/mem/io avg10 triple | Graphs ▸ Pressure |

Each mini-chart: title + current value + threshold-zone coloring on the
value (r057 `_cap_zone`), sparkline-class rendering from the shared
rings (manager_history, Phase-5 ring law: `(ts, value)`, backoff-excluded,
gaps as gaps).

## 2. Per-metric detail pages (Graphs ▸ X)

One page per metric, common skeleton (mockup L):

- **Large chart** (the ring, ~40% of page height) with zone-tinted
  background bands (green/amber/red by threshold), hover crosshair with
  exact `(time, value)` readout.
- **Window selector**: 1 m / 5 m only in v1 — the rings hold ~5 min, so
  longer options would be dishonest slices (r059 review). A 15 m tier
  requires a spec'd downsampled long-ring tier with a memory budget;
  "session" is dropped unless persistence is designed.
- **Stat strip**: current / min / avg / max over the selected window.
- **"Top contributors" panel**: the same ranking component as the
  metric-band drill ([metric-band-basics.md](metric-band-basics.md) §2) —
  for CPU/Memory/Swap/Disk the top processes for that metric, click →
  select in Processes. Network again shows its honest empty-state until
  backlog I9 lands.
- **Per-core / per-device / per-iface breakdown** where applicable:
  CPU page shows per-core mini-rows; Disk page per-device; Network
  per-interface (all from the existing system-section schema).

Page inventory: CPU · Memory · Swap · Disk I/O · Network · Pressure.
**Load is gated**: loadavg is not in the frozen schema, so there is no
Load chart/page until that reader passes the sign-off gate — the band's
"—" gauge stays honest meanwhile (r059 review: no dead nav). Swap moves
here now; the Processes band carries only CPU / Memory / Disk I/O /
Network, and Basics keeps its six-gauge summary role.

## 3. Architecture

- New `page_graphs.py` (hub) + one detail page module per metric sharing a
  `GraphDetailPage` base (window selector + stat strip + contributors +
  breakdown slots) — additive, page-registry as usual.
- All charts are compat `ChartArea` widgets; rings come from
  manager_history (built in Phase 5 — the hub ships with whatever ring
  depth exists and states it).
- Boundary law: pages consume snapshots/rings only; no /proc reads.
- Sidebar/registry changes ride the same commit — and the Resources
  retirement is a **checklist, not a one-liner** (r059 review):
  content_area import/stack/register, pages/__init__ export, sidebar
  entry, page_settings "Navigation Pages" string, and the two
  "interface totals on Resources" cross-refs in page_processes/page_basics
  (they must repoint at the Network hub card — that is where the
  empty-state sends users). Sensors chips (hwmon/freq/GPU) and the r042
  memory-pressure banner move to the hub as their owning surfaces — the
  hub ships with those or Resources stays until they do.

## 4. Tests

Hub grid renders all seven charts with current values; click-through
navigates to the right detail page; window-selector changes ring slice;
stat strip math (min/avg/max over slice); zone tinting bounds; breakdown
rows match snapshot counts; Network empty-state; Load "—" until schema.

## 5. Phasing

Ships as **Phase 5 body** (with manager_history rings + sysfs sensors):
this document replaces resource-graphs.md's rendering section; the
Resources sidebar entry is retired in the same change.
