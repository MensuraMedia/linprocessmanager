# Task 010 — process preview pane + extended columns (Phase 4 remainder)

You are the executor for linprocsearch-grade depth in linprocman
(/home/user/projects/linprocman). ZCode has frozen the schema (C-review
SIGNED, amended — see `docs/modules/sampling-pipeline.md` "Schema freeze
r093") and will verify everything. Work in stages, in order; each stage must
leave the suite green.

## Hard constraints

- Standard library only; no gi in core modules (procfs.py, manager_sampler.py
  stay UI-free — boundary law); raw gi imports banned outside ui/compat
  (import toolkit symbols from ui.compat).
- Offline. No network imports. No pip/venv.
- Do NOT run git commands. Do NOT create CLAUDE.md or .claude/ paths.
- Missing data is ALWAYS None → rendered "—" (r039 taxonomy). Never guess.
- Respect the bounding-box policy (§5b build-principles.md) for every new
  widget: pinned widths + ellipsize, fixed boxes.
- Toolkit calls in the page go through the compat seams (layout.box_add /
  layout.set_child; FlowBox uses .insert; no .add/.show_all/.get_children).

## Read first (binding)

- `docs/modules/process-preview.md` — THE SPEC (§1 columns, §2 pane, §3 menu
  extensions are OUT OF SCOPE for this task, §4 network attribution).
- `docs/modules/sampling-pipeline.md` — "Schema freeze r093" (the signed
  key list + amendments).
- `src/modules/manager_sampler.py`, `src/modules/procfs.py`,
  `src/ui/process_model.py`, `src/pages/page_processes.py`,
  `src/pages/graph_details.py` (pane patterns), `tests/test_process_model.py`,
  `tests/fixtures/` (existing fixture style).

## Stage 1 — schema + readers (core, UI-free)

Add the SIGNED keys to the sampler record per the freeze note:
`cpu_time` (stat utime+stime /100), `mem_pct` (rss/MemTotal, None-able),
`io_read_total`, `io_write_total` (/proc/<pid>/io read_bytes/write_bytes —
the counters are already read for rate deltas; store them now),
`net_rx_rate`, `net_tx_rate` (r053 attribution below), `oom_score`
(/proc/<pid>/oom_score), `affinity` (tuple[int]|None via
os.sched_getaffinity — reachable own-process pids only; EACCES → None),
`cmdline` (procfs.read_cmdline, NUL-joined, capped 512 chars),
`started` (float epoch = btime + starttime/CLK_TCK; add ONE per-pass read
of /proc/stat btime in the system build). `io_prio` is DEFERRED — do not
add it. Keep RECORD_FIELDS/frozenset + the schema test updated (the frozen
set grows 20 → 31; update sampling-pipeline.md marker to "31 fields,
r093 signed"). All new keys optional; on any read error the key is None.

## Stage 2 — per-process network attribution (r053 design, honest model)

`modules/manager_netattr.py` (new, core, UI-free): at sampler cadence build
a socket-inode → pid map from /proc/<pid>/fd/* (incremental: cache pids whose
fd table mtime/set is unchanged), read /proc/net/{tcp,tcp6,udp,udp6} inode
columns, attribute each interface's rx/tx deltas across a process's open
sockets proportional to open-duration share; tree totals sum the subtree.
Foreign pids under Yama → None. Bounded work per pass; never block the
sampler watchdog. Fixtures + unit tests (fake /proc trees).

## Stage 3 — extended columns (22-column chooser)

Extend `process_model.py` + the page chooser to the four grouped sets from
process-preview.md §1 (Identity / CPU / Memory / I/O+Network / Diagnostics —
the chooser renders the groups with headers). Every column: typed store
field, "—" representation, right-align numerics, persisted visibility +
width via the existing settings `columns` machinery (chooser popover keeps
the r081 header right-click behavior). Defaults visible = the CURRENT nine
columns; everything else opt-in via the chooser.

## Stage 4 — preview pane (right fold-out, mockup J)

Fold-out pane on the Processes page,290–330 px, the r028-style toggle is
already there (preview strip) — restore its pane role per mockup J:
Identity, KPI row, 60s CPU sparkline (ring owned by the pane, fed by
snapshots), ancestry click-to-jump (parent chain + children),
resource consumption, networking self/children/combined (attribution or
lock+"—"), dependencies (maps basenames capped 12 + count), action row wired
to the EXISTING actions (End/Kill/Stop/Renice — reuse the page's action
methods; Journal item stays a placeholder "Phase 7"). Tracks selection;
refreshes every snapshot; smaps_rollup via the existing request_rollup for
the selected row only.

## Tests (each stage lands with its own)

Stage 1: schema test update + per-reader fixture units. Stage 2: attribution
fixtures (fake /proc trees: exact own-process, Yama-None, proportional
split). Stage 3: chooser group presence, column add/remove persistence,
"—" rendering. Stage 4: pane build, selection tracking, ancestry ordering,
attribution rows lock/"—". Keep the whole suite green at every stage.

## Report

When done: files written, test counts, stage-by-stage notes, and any
interpretation calls. ZCode runs the full verification chain afterwards.
