# Mockup catalog — docs/mockups/

This directory is the DESIGN RECORD of linprocman: every UI direction was
mocked here first (HTML + rendered PNG), reviewed in the operator's browser
(`python3 -m http.server 8931` from this directory →
<http://127.0.0.1:8931/>), then applied, superseded, or parked. This README
is the catalog: what each mockup shows and where it stands. The executable
spec for each applied design lives in the linked module doc.

Mockups are part of the documentation, not scratch files: they are committed,
indexed in `index.html`, and referenced from `docs/modules/*`.

## Catalog

| Mockup | Subject | Status | Spec / notes |
|---|---|---|---|
| [A — Processes](mockup-a-processes.html) | primary layout: sidebar + band + flat table | **APPLIED** (r005-era; the app's base layout) | [process-table.md](../modules/process-table.md) |
| [B — Tree](mockup-b-tree.html) | tree-grouped process view | design reserve (`view_mode` setting exists; not built) | [process-table.md](../modules/process-table.md) |
| [C — Resources](mockup-c-resources.html) | whole-machine resource summary | **SUPERSEDED** — retired r061 by the Graphs hub ([L](mockup-l-graphs.html)) | [resource-graphs.md](../modules/resource-graphs.md) |
| [D — Actions](mockup-d-actions.html) | context menu + kill/stop surface | **APPLIED with deviations** — Phase 3 shipped; the floating confirm was replaced by the inline bar (r065); group ops r074 | [actions-permissions.md](../modules/actions-permissions.md) |
| [E — Logs](mockup-e-logs.html) | journal viewer | **PENDING** Phase 7 (task 013) | [logs-journal.md](../modules/logs-journal.md) |
| [F — Views](mockup-f-views.html) | saved log views + flags | **PENDING** Phase 7 (task 014) | [logs-journal.md](../modules/logs-journal.md) |
| [G — Frequency](mockup-g-frequency.html) | log/pattern frequency analysis | **PENDING** Phase 7 (task 015) | [log-frequency.md](../modules/log-frequency.md) |
| [H — Sidebar width study](mockup-h-sidebar.html) | 150 / 170 / 190 px variants | **APPLIED** — 170 px chosen; the study predates the r092 flat sidebar (submenu removed) | sidebar history in changelog r062/r075/r092 |
| [I — Extended columns](mockup-i-extended-columns.html) | 20+-column chooser, grouped | **APPLIED** (r098 — 25 backed columns, 5 groups) | [process-preview.md](../modules/process-preview.md) §1 |
| [J — Preview + context](mockup-j-preview-context.html) | right process-preview pane, row menu | **APPLIED** (r098 pane; r092 double-click→hub; context menu partial — open-location r099, frequency/journal pending) | [process-preview.md](../modules/process-preview.md) §2–4 |
| [K — Metric bars](mockup-k-metricbars.html) | band gauge Variant 2 (ticks + captions) | **APPLIED** (r059/r060; arrows removed r070) | [metric-band-basics.md](../modules/metric-band-basics.md) |
| [L — Graphs](mockup-l-graphs.html) | Graphs hub grid + detail pages | **APPLIED** (r061/r068; Basics cards merged on top r092) | [graphs-hub.md](../modules/graphs-hub.md) |
| [M — Visuals](mockup-m-visuals.html) | Basics split cards + chart visuals | **APPLIED** (r068–r070) | [metric-band-basics.md](../modules/metric-band-basics.md) |
| [N — Disks](mockup-disks.html) | Disks page: capacity + I/O | **PENDING operator pick** → task 011 | [disks-capacity.md](../modules/disks-capacity.md) + [disks-filesystems.md](../modules/disks-filesystems.md) + [disks-implementation.md](../modules/disks-implementation.md) |
| [P — Peripherals](mockup-peripherals.html) | connected devices + sensors | **SHIPPED** r092 (page live; sidebar updated r092 to the flat structure) | [peripherals.md](../modules/peripherals.md) + [sysfs-data.md](../modules/sysfs-data.md) |

Planned, not yet mocked: a **Network** page (dedicated per-app traffic view —
technical doc + mockup queued, operator item r099/9). When it exists it
becomes mockup Q and joins this table.

## Also in this directory

- `app-live-*.png` — the live-verification captures taken at each phase
  close (the photographic record of what actually shipped; `index.png` is
  the original starter baseline).
- `index.html` — visual review index (serve this directory and open it);
  every mockup above has a card there.

## Workflow (how a mockup becomes documentation)

1. HTML mockup in the app's real design language, render-verified
   (headless Firefox → PNG, pixel-checked).
2. Card added to `index.html`; directory served on :8931 for the operator.
3. Operator picks → status updated here (APPLIED / SUPERSEDED / PENDING) →
   the owning module doc in `docs/modules/` carries the executable spec.
4. Superseded mockups are KEPT (never deleted) — they are the design
   history; their status row says what replaced them.
