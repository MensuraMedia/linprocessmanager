# Implementation guide — Disks feature (Phase 6, task 011)

Supporting technical document for the Disks portion: HOW to build it,
file by file, gate by gate. The WHAT lives in the two specs this guide
binds together:

- `disks-filesystems.md` — I/O rates (diskstats deltas), mount enumeration,
  plug/unplug, hidden-pseudo rules.
- `disks-capacity.md` — the capacity standard (statvfs quantities incl.
  bavail-vs-bfree and inodes, df-style usage %, zone thresholds, bar/tick/
  band-card visualizations).

Mockup: `docs/mockups/mockup-disks.html/.png` (sidebar reflects the r092
flat structure: Processes · Graphs · Disks · Peripherals · Logs · About).

## Build order (each step lands with its tests)

1. **Reader first** (`src/modules/procfs.py`): `system_diskstats()` — parse
   `/proc/diskstats` into per-device {reads, writes, sectors_read,
   sectors_written, io_ticks_ms}; pure, fixture-tested; counter-reset clamp
   shared with the network rate machinery (a reset is a gap, not a
   negative spike).
2. **Sampler integration** (`manager_sampler.py`): extend the system-level
   snapshot with `diskstats` + per-mount `statvfs` — computed OFF the
   critical path (a stale NFS mount can hang statvfs: per-entry try +
   thread/timeout pattern per HANDOFF). The sampler schema gains fields
   through the SCHEMA-FREEZE gate (sign-off before any UI consumes them —
   the r048 lesson).
3. **Capacity math** (pure helper, `modules/`): totals/used/available from
   statvfs fields, df-style usage % (`used / (used + bavail)`), inode %,
   human scaling; zone mapping via the r071 thresholds provider (yellow 42 /
   red 60 derived on this box).
4. **Page** (`src/pages/page_disks.py`): summary band cards (Devices,
   Total, Used, Available — pinned labels §5b) + spreadsheet (Device,
   Mount, Type, Total, Used, Available, Usage bar, Inodes, Read/s, Write/s,
   Busy %) with header-click sort (unknowns-last), persisted widths, and
   the r081 header/row right-click conventions. Usage bar: fixed 160×8,
   zone fill, threshold ticks (Variant-2 language).
5. **Behaviors**: unmounted devices listed + flagged (amber "— flagged");
   pseudo/squashfs/loop hidden with "N hidden — show" count row;
   dedup bind mounts by st_dev; `Gio.UnixMountMonitor` refresh on
   plug/unplug (mount events only — device hotplug reuses the same monitor
   post-v1, see peripherals.md).
6. **Settings**: none new in v1 (column persistence already generic);
   `disks.show_hidden` toggle may reuse the kernel-threads pattern.

## Gates (all standing, plus this feature's specifics)

- pytest: diskstats fixture parse, reset clamp, statvfs fixture math,
  dedup, zone override, hidden-count; UI tier builds the real page.
- Banned-API/raw-import sweeps; boundary law (procfs.py + sampler stay
  UI-free).
- Pixel pass on `:0`: populated table from the REAL mounts, bars pinned
  (two captures, edges identical), zone fill matches thresholds.
- Live gate: plug/unplug a USB stick → row appears/disappears without
  restart; journal (`~/.local/state/linprocman/linprocman.log`) clean.

## Execution split

Z drafts the contract (this guide + the two specs, step list above) →
C executes headless (`--permission-mode acceptEdits`, no Bash) → Z verifies
the full chain → C reviews at phase close. Estimate $6–8 (one dispatch +
review), per the plan in `roadmap-disks-logs-peripherals.md`.
