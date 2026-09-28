# Module doc — Disks capacity reporting (`src/pages/page_disks.py`, Phase 6)

Part of the linprocman modular docs. Siblings:
[disks-filesystems.md](disks-filesystems.md) (I/O rates + mount enumeration —
companion doc; this one owns CAPACITY) · [procfs-data.md](procfs-data.md) ·
[sysfs-data.md](sysfs-data.md) · [perf-thresholds.md](perf-thresholds.md) ·
[persistence-config.md](persistence-config.md). Overview:
[../process-manager-concept.md](../process-manager-concept.md).

Closes the capacity half of the concept-§3 orphan: what "how full is my
drive" means on this page, and exactly how it is drawn. Visual language
follows the shipped spec (mockup N, `docs/mockups/mockup-disks.html`).

## 1. Data standard

Per MOUNTED FILESYSTEM (capacity is a property of the filesystem, not the
device — one device with two mounts shows two rows):

| Quantity | Source | Report as |
|---|---|---|
| Total | `f_blocks × f_bsize` (statvfs) | bytes, human-scaled (B/KB/MB/GB/TB) |
| Used | `(f_blocks − f_bfree) × f_bsize` | bytes |
| Free (system) | `f_bfree × f_bsize` — includes the root reserve | bytes |
| Available (to you) | `f_bavail × f_bsize` — what THIS user can still write | bytes; the number the operator cares about |
| Usage % | `used / (used + f_bavail)` — df-style, not `used/total` | percent, 1 decimal |
| Inodes used % | `1 − f_ffree/f_files` | percent; shown as a secondary bar or column |
| Fs type / device / mount | `/proc/self/mounts` parse (reuses the linfilesearch mount model) | text |

Rules carried over: read-only (no mount/eject actions — elevation is
forbidden); `statvfs` runs off the critical path (a stale NFS mount can hang
the call — sample in the sampler thread with the per-entry try pattern);
bind-mount/duplicate-filesystem dedup by `st_dev`; pseudo/squashfs/loop
filesystems hidden by default with a "N hidden — show" count row (the
kernel-threads pattern); unmounted devices still listed but FLAGGED, not
hidden; empty/unknown values render "—", never 0 (r039 taxonomy). Values are
sampled on the existing sampler cadence — no second timer. USB plug/unplug
refreshes via `Gio.UnixMountMonitor`.

## 2. Thresholds and color

Usage % maps through the SAME zone machinery as every other gauge —
`mr.capacity_zone(pct)` with the r071 baseline provider consulted first
(this machine's derived disk thresholds: yellow 42, red 60), fixed 60/85
defaults when absent. Zone colors are the only colors: nominal/yellow/red
per `_ZONE_RGB` (r056 convention). No new colors, no per-device palettes.

## 3. Visualizations (all under bounding-box policy §5b)

1. **Per-row usage bar** — fixed 160×8 box, trough `#1b1b1b`, fill =
   usage fraction in the ZONE color, threshold TICKS drawn at the yellow/red
   crossings (Variant-2 language from the metric band). The bar never
   resizes; the fill fraction is the only variable.
2. **Inode bar** — same geometry, half height, only when inodes exceed 60%
   (otherwise the column shows the percentage alone; inode exhaustion kills
   writes even when bytes are free — it is a first-class capacity signal).
3. **Summary band cards** (page top, fixed 4-card row): Devices (mounted /
   flagged), Total capacity (sum over UNIQUE filesystems — deduped),
   Used total, Available total. Pinned value/caption widths per §5b.
4. **Spreadsheet table** — columns Device, Mount, Type, Total, Used,
   Available, Usage (bar), Inodes, Read/s, Write/s, Busy %; header-click
   sort with unknowns-last; widths persisted via the settings `columns`
   pattern; right-margin area and header right-click follow the r081
   chooser conventions.
5. **v2 (deferred, spec'd now): per-mount capacity sparkline** — 5-minute
   `manager_history` ring per mount, same ring law as Basics (gaps are
   gaps), drawn only when `basics.show_sparklines`-equivalent key is on.

## 4. Tests

statvfs fixture → percent/bytes math (incl. the bavail-vs-bfree
distinction); inode math; zone mapping incl. baseline-provider override;
filesystem dedup; hidden-count behavior; bar geometry pinned by pixel test
(§5b); "—" taxonomy. Live gate: populate table from the real mounts on
`:0`, plug/unplug a USB stick, confirm row add/remove without a restart.
