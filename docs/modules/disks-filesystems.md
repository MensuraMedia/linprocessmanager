# Module doc — disks & filesystems (`src/pages/page_disks.py`)

Part of the linprocman modular docs. Siblings: [procfs-data.md](procfs-data.md) ·
[sampling-pipeline.md](sampling-pipeline.md) · [process-table.md](process-table.md) ·
[actions-permissions.md](actions-permissions.md) · [resource-graphs.md](resource-graphs.md) ·
[persistence-config.md](persistence-config.md) · [logs-journal.md](logs-journal.md) ·
[sysfs-data.md](sysfs-data.md). Overview: [../process-manager-concept.md](../process-manager-concept.md).

Closes the concept-§3 orphan (a Disks page was promised with no owning
module) and gnome-system-monitor's File Systems parity.

## Purpose

Per-device I/O rates and per-mount usage — read-only, all from
`/proc/diskstats` and `statvfs`.

## Interface

Consumes: `system_diskstats()` (added to [procfs-data.md](procfs-data.md)'s
reader table) and `os.statvfs` per mountpoint; mount enumeration reuses the
linfilesearch mount model (`/proc/self/mounts` parse, fs-type
classification, `Gio.UnixMountMonitor` for USB plug events).

Provides: one row per device/mount — device, mount, fs type, total/used/free
(usage bar, theme accent), read/write **rates** (deltas between snapshots,
same counter-reset rules as network), busy % where diskstats gives it.

## Rules

- Devices with no mountpoint still show (install media, swap) — flagged, not
  hidden. Pseudo/squashfs snap loops hidden by default with a count row
  (same pattern as kernel threads).
- Rates share the sampler's delta machinery — no second timer.
- No mount/umount/eject actions in v1 (read-only page; a mount action would
  need elevation, which the mandates forbid).

## Tests

diskstats parse fixture, rate+reset-clamp units, mount classification
(borrowed linfilesearch fixtures).
