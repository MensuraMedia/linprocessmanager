# Module doc — process table & tree (`src/pages/page_processes.py` + model helpers)

Part of the linprocman modular docs. Siblings: [procfs-data.md](procfs-data.md) ·
[sampling-pipeline.md](sampling-pipeline.md) · [actions-permissions.md](actions-permissions.md) ·
[resource-graphs.md](resource-graphs.md) · [persistence-config.md](persistence-config.md) ·
[logs-journal.md](logs-journal.md) · [disks-filesystems.md](disks-filesystems.md) ·
[sysfs-data.md](sysfs-data.md). Overview: [../process-manager-concept.md](../process-manager-concept.md).

## Purpose

The Processes page model layer: flat list and tree, filter, live update
without flicker, selection identity, keyboard operation, and the details
fold-out pane.

## Interface

Consumes: `Snapshot` objects from [sampling-pipeline.md](sampling-pipeline.md)
(rates precomputed); selection handed to
[actions-permissions.md](actions-permissions.md) as `(pid, starttime)`
**lists** — multi-select is first-class (bulk actions).

Provides:
- `Gtk.ListStore` (flat) / `Gtk.TreeStore` (tree) with **typed** columns
  (PID int, CPU float, mem bytes int, nice int). Absent rate values are
  stored as a `-1` sentinel **plus a `has_data` bool column**; sort places
  unknowns last; cell data funcs render "—". (None in a float column is a
  PyGObject marshaling hazard; NaN breaks numeric sort.)
- `Gtk.TreeModelFilter` wrapping the store once; the `visible_func` is
  re-pointed on query/scope change, not rebuilt per keystroke. Substring
  default, regex toggle (stdlib `re`).
- Details pane: 290px fold-out (caret fold, the r028 square-toggle pattern);
  cheap fields every snapshot, `smaps_rollup` only for the selected PID —
  read by the **sampler on request** (consumers never read the kernel; the
  pane flags a pid-of-interest and the next snapshot carries its rollup).

## Update logic — diff-in-place with an explicit move op

One snapshot arrives → diff keyed by `pid → Gtk.TreeRowReference` (raw
TreeIters are invalidated by row removals — never cached across batches).
Operations, in order:

1. **Move** — children whose parent vanished this snapshot are relocated to
   their nearest live ancestor first (TreeStore cannot re-parent in place
   once sorted: remove+reinsert, expansion restored via row reference).
2. **Update** — changed rows in place.
3. **Insert / Remove** — new pids appended; gone pids removed (parents
   after their children were relocated).

Sorting is blocked around the whole batch (`set_sort_column_index`
save/restore) so it runs once per refresh. The `TreeModelFilter` is also
suspended around batches (refilter once at the end) — per-row-changed
refiltering is O(n²) and is exactly what freezes a GUI during a fork bomb.

**Row budget (adversarial fix):** above ~5k visible rows, the page shows the
top N (current sort) + a "showing 5,000 of 23,412 — refine filter" notice,
and the sampler interval is offered to coarsen. The manager must stay
responsive during the incident it exists to manage.

Selection survives via `(pid, starttime)` keys, never row index.

## Tree building

- Edges from PPid; orphans attach to the nearest live ancestor, else PID 1 —
  applied at build **and** at every diff (the move op above).
- Kernel threads (empty cmdline **and** state ≠ Z) group under `kthreadd`,
  dimmed, **hidden by default** with a count row (mockup B).

## Columns & keyboard

Flat: Process (icon+name+unit badge), User, CPU %, Memory, Swap, Disk r/w,
Nice, PID, State. Tree drops disk columns for hierarchy width. Visible
columns/widths persist with enforced minimums (linfilesearch r025 lesson).

Keyboard: Ctrl+F focuses filter; ↑/↓ move; Enter opens details; Space
toggles multi-select mark; Delete = End (with confirm); Ctrl+K = Kill;
Ctrl+R refresh now; F5 toggles pause.

## Tests

Tree builder units (orphans, cycles guard, kthread grouping, zombie
exclusion), diff behavior (update/insert/remove/move preserves selection
and expansion), filter suspension, row-budget notice, unknown-value sort
placement, keyboard map.
