# Module doc — persistence & configuration (`src/config/config_processes.py`)

Part of the linprocman modular docs. Siblings: [procfs-data.md](procfs-data.md) ·
[sampling-pipeline.md](sampling-pipeline.md) · [process-table.md](process-table.md) ·
[actions-permissions.md](actions-permissions.md) · [resource-graphs.md](resource-graphs.md) ·
[logs-journal.md](logs-journal.md) · [disks-filesystems.md](disks-filesystems.md) ·
[sysfs-data.md](sysfs-data.md). Overview: [../process-manager-concept.md](../process-manager-concept.md).

## Purpose

One settings file, written in one place, read at startup. Everything the app
remembers between runs lives here — nowhere else.

## Interface

Path: `~/.config/linprocman/settings.json` (XDG base dir via
`GLib.get_user_config_dir()`). Loaded once at startup; saved atomically
(**write tmp + rename**, never truncate-in-place) on Settings apply and
window close.

**Validation (adversarial fix):** every key is validated and clamped to its
schema range at load — a hand-edited `refresh_interval_s` of 0 or −1 must
fall back to default + a status notice, not drive a busy /proc hammer.
Unknown enum values → per-key default. Missing/corrupt file → defaults +
notice, never a crash.

## Schema (v1)

| Key | Type | Default |
|---|---|---|
| `refresh_interval_s` | float, clamped 0.5–5.0 | 2.0 |
| `view_mode` | "flat" \| "tree" | "flat" |
| `columns.visible` | list | [process, user, cpu, memory, swap, disk_rw, nice, pid, state] |
| `columns.widths` | {name: px} | minimums per process-table.md |
| `sort` | {column, direction} | cpu desc |
| `scope_chip` | string | "all" |
| `show_kernel_threads` | bool | false |
| `cpu_normalized` | "per_core" \| "total" | "per_core" |
| `end_confirm_own` | bool | true (confirm End on own processes) |
| `theme` | string | starter default |
| `window` | {w, h, maximized} | 1200×800 |
| `logs.saved_views` | list of view dicts | [] |
| `logs.flags` | list of {cursor, label} | [] |

## Rules

- App runtime writes nothing outside this file's XDG dir. Sanctioned
  exceptions live in build-principles §5 (installer, user-directed export).
- Graph ring buffers are deliberately **not** persisted.
- Saved log views and flags round-trip with the logs module
  ([logs-journal.md](logs-journal.md)); unknown keys survive save round-trips
  (forward compatibility).
- Settings changes apply live where cheap (cadence, normalization) and on
  restart where structural (nothing foreseen in v1).

## Tests

Round-trip load/save with injected tmp config dir, corrupt-file fallback,
**hostile-value clamping table** (0, −1, 999, wrong types, bogus enums),
unknown-key preservation, atomic-write (no partial file on interrupted save).
