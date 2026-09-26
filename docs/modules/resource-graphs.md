# Module doc — resource graphs & PSI (`src/pages/page_resources.py` + `src/modules/manager_history.py`)

Part of the linprocman modular docs. Siblings: [procfs-data.md](procfs-data.md) ·
[sampling-pipeline.md](sampling-pipeline.md) · [process-table.md](process-table.md) ·
[actions-permissions.md](actions-permissions.md) · [persistence-config.md](persistence-config.md) ·
[logs-journal.md](logs-journal.md) · [disks-filesystems.md](disks-filesystems.md) ·
[sysfs-data.md](sysfs-data.md). Overview: [../process-manager-concept.md](../process-manager-concept.md).

## Purpose

System-level history and its cairo rendering: per-core CPU, memory+swap,
network, pressure chips, sensor chips. Pure display of accumulated samples —
this module samples nothing itself.

## Interface

Consumes: the `system` section of every `Snapshot` (rates precomputed) from
[sampling-pipeline.md](sampling-pipeline.md); sensor values from
[sysfs-data.md](sysfs-data.md).

Provides:
- Ring buffers holding **`(ts, value)` tuples** — never positional values —
  sized for ~5 min at the current period. Gaps (backoff, pause, counter
  resets) render as gaps; a 3-minute hidden window must not masquerade as
  18 seconds of activity. Per-core series are **pinned to a fixed max core
  index** so CPU hotplug/offline shifts a series rather than scrambling
  them.
- `DrawingArea` draw callbacks per chart; no timers beyond the sampler.

## Charts

- **CPU — stacked per-core areas** (gnome-system-monitor style): cumulative
  polygons bottom-up, core colors `#0078D7 → #2ea6ff → #00b3a4 → #7c5cff`
  derived from the active starter theme so all 7 themes work with no
  per-theme assets. Gridlines at 25/50/75%.
- **Memory — area + line:** used (area) with swap (dashed line), labeled
  against MemTotal.
- **Network — two lines with soft fills:** rx/tx rates (reset-aware).
- **PSI — numeric chips** (`gauge`): some avg10/avg60/avg300 for cpu; some
  and full for memory and io. Numbers, not charts.
- **Sensors — chips only in v1** (`waveform`): hwmon temperatures, CPU
  frequency min/avg/max, AMD gpu_busy_percent when present; chips hide
  themselves when the source is absent.

## Rules

- Y-scales: CPU fixed 0–100% per-core-normalized; memory fixed 0–total;
  network auto-scaled with the current ceiling shown.
- History is not persisted across restarts.
- Series palette derives from the theme accent at runtime; nothing
  hardcoded per theme.

## Tests

Ring semantics (maxlen eviction, gap rendering, backoff exclusion), per-core
pinning under CPU offline, reset-aware rate feeding, theme-color derivation
smoke against all 7 starter themes.
