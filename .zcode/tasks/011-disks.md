# Task 011 — Disks page build-out (Phase 6)

Executor task in /home/user/projects/linprocman (you are in an isolated
worktree — commit nothing, run no git commands; ZCode integrates).

## Binding specs (read all three first)

1. `docs/modules/disks-capacity.md` — capacity data standard + visualizations.
2. `docs/modules/disks-filesystems.md` — I/O rates, mount enumeration,
   plug/unplug, hidden-pseudo rules.
3. `docs/modules/disks-implementation.md` — build order (your stage list),
   gates, execution split.
4. Mockup N: `docs/mockups/mockup-disks.png` (+ .html).

## Scope

- `procfs.system_diskstats()` reader + fixture (parse /proc/diskstats;
  counter-reset clamp shared with the network delta machinery).
- Per-mount `statvfs` capacity math helper (pure; the bavail-vs-bfree and
  inode rules from disks-capacity.md §1).
- `src/pages/page_disks.py` — replace the placeholder: summary band cards
  (Devices / Read / Write / Busiest), spreadsheet (Device, Mount, Type,
  Total, Used, Free, Usage bar, Inodes %, Read/s, Write/s, Busy %),
  zone-colored usage bars with threshold ticks (bounding-box §5b: fixed
  boxes), flagged unmounted rows, hidden pseudo/loop count row.
- Data flow: page consumes readers directly at its own refresh cadence
  (manual Refresh button + a bounded periodic refresh via GLib timeout);
  statvfs calls wrapped per-entry try + must never run on the UI thread in
  a way that can hang on a stale NFS mount (run the scan in a short-lived
  thread, post results via idle_add — the r071 recalibrate pattern).
- No mount/eject actions. Read-only page.

## Constraints

- stdlib only in core readers (procfs.py stays UI-free, allowlist-gated).
- No gi outside ui/compat. No .add()/.show_all()/.get_children() in page
  code (gate-banned — use compat layout seams, tracked children, per-widget
  show()).
- "—" taxonomy for unknowns. Never crash on a missing/odd mount.
- Tests for every pure piece (diskstats parse + reset clamp, statvfs math,
  zone mapping, dedup by st_dev, hidden count); page build test in the UI
  tier (skips without DISPLAY).

## Report

Files written, test counts, interpretation calls. ZCode verifies: scope
diff → pytest → gates → live capture with real mounts.
