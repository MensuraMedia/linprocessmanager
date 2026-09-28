# Implementation plan — Disks build-out, Peripherals, Logs engine

Planning doc (r090, operator request). Supersedes the one-line queue rows in
`.zcode/tasks/QUEUE.md` for these features; the queue remains the execution
ledger. Collaboration pattern per task, as everywhere in this project:
**Z** drafts the contract → **C** executes headless on the contract →
**Z** verifies (scope diff → pytest → gates → pixels on `:0` → journal) →
**C** reviews phase closes. Executor economics from history: small feature
$3–5, large $6–11.

## State at planning

| Feature | Assets ready | Code ready | Gap |
|---|---|---|---|
| Disks (Phase 6) | mockup N (`mockup-disks.png/html`), module docs `disks-filesystems.md` + `disks-capacity.md` | page placeholder only | everything |
| Peripherals | mockup P (`mockup-peripherals.png/html`), concept `sysfs-data.md` (readers EXIST since r039) | no sidebar entry, no page | page + chips |
| Logs (Phase 7) | mockups E/F/G/H (`docs/mockups/index.html`), concept `logs-journal.md` + `log-frequency.md` | page placeholder only | engine + views + frequency |

Disks and Peripherals mockups are rendered and served (port 8931) — BOTH
await the operator's pick before their contracts freeze. Logs mockups were
reviewed earlier; confirm before task 013.

## Task 011 — Disks build-out (Phase 6) · small/medium, one dispatch

- Contract inputs: `disks-filesystems.md` (I/O rates, mount enumeration,
  plug/unplug) + `disks-capacity.md` (capacity standard + visualizations).
- Scope: `procfs.system_diskstats()` reader + per-mount `statvfs` sampler
  (off critical path), `page_disks.py` table + summary band + usage/inode
  bars, hidden-count row, flagged unmounted rows, UnixMountMonitor refresh.
- Gates: fixture units for statvfs/dedup/zone math; pixel test pinning bar
  boxes (§5b); live USB plug/unplug on `:0`; settings untouched.
- Estimate: $6–8, one executor run + one review pass.
- Prerequisite: operator picks mockup N.

## Task 012 — Peripherals page · small, one dispatch

- Contract inputs: `sysfs-data.md` (hwmon temps/fans, cpufreq, amdgpu busy —
  readers already exist and are fixture-tested), mockup P.
- Scope: sidebar entry BETWEEN Disks and Logs (mockup P placement), page of
  self-hiding chips per the universality mandate (absent hwmon → chip
  hidden, VM shows an empty page that works), zone coloring via the r071
  provider, no new sampling cadence.
- Gates: chip hide/show fixture tests, sysfs tree fixtures, banned-API +
  boundary gates, live capture on this machine (has k10temp + amdgpu).
- Estimate: $3–4. Prerequisite: operator picks mockup P.

## Tasks 013–015 — Logs engine (Phase 7) · LARGE — size like Phases 1–2

- 013 **engine**: `journalctl` argv-contract reader (never shell strings —
  argv lists, gate-enforced), four presets, follow/tail, time-jump, cursor
  bookmarking; offline mandate intact (journalctl is a local binary).
- 014 **views + menu**: page UI per mockups E/F/G/H — priority coloring,
  unit/priority filters, search-as-you-type, saved views + flags persisted
  via the settings pattern.
- 015 **frequency analysis**: pattern counting, windowed rates, top-talkers
  (concept `log-frequency.md`).
- Gates per task: argv allowlist tests FIRST (the r048 schema-freeze lesson —
  freeze the engine seam before views build on it), fixture journals, pixel
  passes, journal read-back.
- Estimate: 013 ≈ $8–11, 014 ≈ $5–7, 015 ≈ $4–6; three dispatches with
  phase-close reviews between.

## Sequencing recommendation

1. **011 Disks** — both docs and the mockup are ready; closes the oldest
   orphan; visible win.
2. **012 Peripherals** — readers already exist; cheapest dispatch; gives the
   sidebar its missing entry.
3. **013–015 Logs** — largest surface; keep the three-dispatch split with a
   phase-close review after 013 so the seam freeze is verified before UI
   builds on it.
Task 010 (preview pane + chart double-click pages) is already queued ahead
of these — the operator chooses its position; it does not conflict with 011
(touches Processes/table, not Disks).
