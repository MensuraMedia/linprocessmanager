# linprocman — optimization & innovation backlog

Work items that are NOT on the mainline phases but get pulled in when an
executor has spare capacity in a task's scope, or when the operator picks.
Each item names its type (OPT = optimization, INNOV = innovation, DEBT =
debt/prevention) and the phase where it naturally fits.

## Optimizations

| ID | Item | Type | Fits | Notes |
|---|---|---|---|---|
| O1 | Diff engine: batch store updates inside `freeze_child_notify` + `set_sort_func` suspension is done — next: skip `_visible_func` calls entirely during batch via `filter.refilter()` only at end (verify current code does refilter-once, not per-row) | OPT | 4+ | measure first: `time.perf_counter` around apply_snapshot in a bench test |
| O2 | Sampler: read `/proc` dir listing once per tick and reuse entries across all readers (one scandir, not per-reader) | OPT | 6 | saves ~30% syscalls on big hosts |
| O3 | Icon tint cache keyed by (name, size, theme-accent) — invalidate on theme switch only | OPT | 5 | avoids Pillow re-tint per row draw |
| O4 | Settings save coalescing: single 500 ms debounce for ALL mutating keys (widths already debounced; apply to sort/scope too) | OPT | done for widths | extend |
| O5 | Startup: lazy-build non-visible pages (Disks/Logs/Resources build on first navigate) | OPT | 6 | shaves ~200 ms launch |

## Innovations

| ID | Item | Type | Fits | Notes |
|---|---|---|---|---|
| I1 | **Telemetry Watch** — operator-mandated r055; concept ready (modules/telemetry-watch.md); blocked on Phase 5 attribution data | INNOV | 5 | scoring engine + chip + preview section |
| I2 | **Metric band** — mockup K; r058; replaces text strip; cairo gauges | INNOV | 4.5 | pick variant after operator look |
| I3 | **Frequency for processes** — reuse log-frequency charting over per-process metric history (the "why is firefox spiking" view) | INNOV | 7 | engine shared |
| I4 | **Process ancestry minimap** — preview pane's ancestry tree as a collapsible mini-tree with live CPU heat coloring | INNOV | 4 | cheap once pane exists |
| I5 | **Snapshot export** — one-click JSON/CSV of the current table (incident reporting) | INNOV | 6 | sanctioned export path exists |
| I6 | **Watch mode** — pin a process; strip sparkline follows it even when scrolled away; notify-on-exit (GLib.Notification, offline) | INNOV | 6 | operator gate for the notification part |
| I7 | **Zombie reaper assistant** — lists zombie orphan sets, names the parent that must reap, offers parent SIGCHLD ping | INNOV | 6 | niche but loved |
| I8 | **Compact single-window mode** — hide sidebar, icons-only nav (netbook/tiling users) | INNOV | 8 | pure layout |

## Debt / prevention

| ID | Item | Type | Notes |
|---|---|---|---|
| D1 | `_cap_zone` thresholds + r056 arrow convention: move to one shared module constant block imported by pages + docs cite it | DEBT | r057 ad-hoc methods |
| D2 | bench test harness (`tests/test_bench.py`, live marker): apply_snapshot over 5k synthetic rows, assert < budget ms | DEBT | guards the row budget promise |
| D3 | GUI walk: add per-page pixel-hash diff assertion (catches accidental blank pages) | DEBT | uses r051 harness |
| D4 | settings.json version key + migration stub | DEBT | forward compat |
| D5 | Strip/`status-strip` CSS: move magic colors into config_themes accent derivation | DEBT | 7-theme correctness |
| D6 | `compat/dialogs` entry/spin seam (`entry_window`): renice + affinity + custom-signal ship as presets in Phase 3 because `confirm_window` has no input field; a free numeric renice value and an arbitrary CPU-mask picker need a portable entry dialog added to the dialogs seam | DEBT | task 006 deferral; dialogs.py was out of task-006 scope |
