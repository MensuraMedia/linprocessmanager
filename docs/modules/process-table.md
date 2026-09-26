# Module doc — process table & tree (`src/pages/page_processes.py` + model helpers)

Part of the linprocman modular docs. Siblings: [procfs-data.md](procfs-data.md) ·
[sampling-pipeline.md](sampling-pipeline.md) · [actions-permissions.md](actions-permissions.md) ·
[resource-graphs.md](resource-graphs.md) · [persistence-config.md](persistence-config.md).
Overview: [../process-manager-concept.md](../process-manager-concept.md).

## Purpose

The Processes page model layer: flat list and tree, filter, live update
without flicker, selection identity, and the details fold-out pane.

## Interface

Consumes: `Snapshot` objects from [sampling-pipeline.md](sampling-pipeline.md);
selection handed to [actions-permissions.md](actions-permissions.md) as
`(pid, starttime)`.

Provides:
- `Gtk.ListStore` (flat) / `Gtk.TreeStore` (tree) with **typed** columns
  (PID int, CPU float, mem bytes int, nice int) — sorting on typed columns is
  correct for free; display formatting (2.4 MB, 01:23:45) lives in
  `set_cell_data_func`, never stored as strings. Generalizes the hidden-epoch
  trick linfilesearch needed for dates.
- `Gtk.TreeModelFilter` wrapping the store once; the `visible_func` is
  re-pointed on query/scope change, not rebuilt per keystroke.
- Details pane: 290px fold-out (caret fold, the r028 square-toggle pattern);
  cheap fields every snapshot, `smaps_rollup` only for the selected PID.

## Update logic — diff-in-place, never rebuild

One snapshot arrives → diff keyed by a `pid → TreeIter` dict: update changed
rows, append new, remove gone. Sorting is blocked around the batch
(`set_sort_column_index` save/restore) so it runs once per refresh, not once
per row. This preserves the three things a full rebuild breaks: selection,
sort position, tree expansion. Selection is restored by `(pid, starttime)`,
not row index.

## Tree building

- Edges from PPid; orphans (parent already reaped) attach to the nearest live
  ancestor, else PID 1.
- Kernel threads (empty cmdline) group under `kthreadd`, dimmed style,
  **hidden by default** with a count row (mockup B).
- Reparenting under subreapers is handled by the nearest-live-ancestor rule —
  no prctl guessing.

## Columns

Flat view: Process (icon+name+unit badge), User, CPU %, Memory, Disk r/w,
Nice, PID, State. Tree view drops disk columns for hierarchy width. Visible
columns, widths, and minimums persist (linfilesearch r025 lesson: minimum
widths — Name 200, Path 300 equivalents — stop the sheet crushing text).

## Tests

Tree builder units (orphans, cycles-guard, kthread grouping), diff behavior
(update/insert/remove preserves selection path), typed-sort correctness.
