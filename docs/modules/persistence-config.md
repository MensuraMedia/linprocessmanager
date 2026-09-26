# Module doc — persistence & configuration (`src/config/config_processes.py`)

Part of the linprocman modular docs. Siblings: [procfs-data.md](procfs-data.md) ·
[sampling-pipeline.md](sampling-pipeline.md) · [process-table.md](process-table.md) ·
[actions-permissions.md](actions-permissions.md) · [resource-graphs.md](resource-graphs.md).
Overview: [../process-manager-concept.md](../process-manager-concept.md).

## Purpose

One settings file, written in one place, read at startup. Everything the app
remembers between runs lives here — nowhere else.

## Interface

Path: `~/.config/linprocman/settings.json` (XDG base dir respected via
`GLib.get_user_config_dir()`). Loaded once at startup; saved on Settings-page
apply and window close. Missing/corrupt file → defaults + a status notice,
never a crash.

## Schema (v1)

| Key | Type | Default |
|---|---|---|
| `refresh_interval_s` | float | 2.0 (table; graphs fixed 1.0) |
| `view_mode` | "flat" \| "tree" | "flat" |
| `columns.visible` | list | [process, user, cpu, memory, disk_rw, nice, pid, state] |
| `columns.widths` | {name: px} | minimums per process-table.md |
| `sort` | {column, direction} | cpu desc |
| `scope_chip` | string | "all" |
| `show_kernel_threads` | bool | false |
| `cpu_normalized` | "per_core" \| "total" | "per_core" |
| `theme` | string | starter default |
| `window` | {w, h, maximized} | 1200×800 |

## Rules

- Nothing but this file writes outside the XDG dir. No secrets, no
  telemetry, no history file (there is no query history to keep).
- Graph ring buffers are deliberately **not** persisted — 5 minutes of
  history restarts with the app.
- Unknown keys survive save round-trips (forward compatibility).
- Settings changes apply live where cheap (cadence, normalization) and on
  restart where structural (nothing foreseen in v1).

## Tests

Round-trip load/save with injected tmp config dir, corrupt-file fallback,
unknown-key preservation.
