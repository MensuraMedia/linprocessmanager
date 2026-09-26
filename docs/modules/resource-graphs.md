# Module doc — resource graphs & PSI (`src/pages/page_resources.py` + `src/modules/manager_history.py`)

Part of the linprocman modular docs. Siblings: [procfs-data.md](procfs-data.md) ·
[sampling-pipeline.md](sampling-pipeline.md) · [process-table.md](process-table.md) ·
[actions-permissions.md](actions-permissions.md) · [persistence-config.md](persistence-config.md).
Overview: [../process-manager-concept.md](../process-manager-concept.md).

## Purpose

System-level history and its cairo rendering: per-core CPU, memory+swap,
network, and pressure (PSI) chips. Pure display of accumulated samples —
this module samples nothing itself.

## Interface

Consumes: the `system` section of every `Snapshot` (cpu jiffies, meminfo,
net counters, pressure values) from
[sampling-pipeline.md](sampling-pipeline.md).

Provides:
- Ring buffers — `collections.deque(maxlen=300)` ≈ 5 min at 1 s — one per
  series: per-core totals, mem used, swap used, net rx/tx, PSI avg10s.
- `DrawingArea` draw callbacks per chart; no timers beyond the sampler
  (redraw rides the snapshot-apply + window expose).

## Charts

- **CPU — stacked per-core areas** (gnome-system-monitor style): cumulative
  polygons bottom-up, core colors `#0078D7 → #2ea6ff → #00b3a4 → #7c5cff`
  derived from the active starter theme so all 7 themes work with no
  per-theme assets. Gridlines at 25/50/75%.
- **Memory — area + line:** used (area) with swap (dashed line), labeled
  against MemTotal.
- **Network — two lines with soft fills:** rx/tx byte deltas per interval.
- **PSI — numeric chips** (`gauge`): some avg10/avg60/avg300 for cpu; some
  and full for memory and io. Numbers, not charts — pressure is a rate, and
  numbers don't lie at a glance.

## Rules

- Y-scale choices: CPU fixed 0–100%×ncore-normalized; memory fixed 0–total;
  network auto-scaled with the current ceiling shown.
- History depth is fixed (5 min) in v1 — no persistence of buffers across
  restarts.
- Colors: series palette derives from the theme accent at runtime; nothing
  is hardcoded per theme.

## Tests

Ring-buffer semantics (maxlen eviction), delta→rate math for net series,
theme-color derivation smoke test against all 7 starter themes.
