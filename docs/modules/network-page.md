# Module doc — Network page (`src/pages/page_network.py`)

Part of the linprocman modular docs. Siblings:
[process-preview.md](process-preview.md) (§4 — the attribution design this
page renders) · [process-table.md](../modules/process-table.md) ·
[sampling-pipeline.md](sampling-pipeline.md) · [resource-graphs.md](../modules/resource-graphs.md).
Overview: [../process-manager-concept.md](../process-manager-concept.md).

Shipped r113 (operator): a dedicated **Network** sidebar entry (between
Disks and Peripherals) showing the processes that are actively sending
and/or receiving packets — to the internet or any other network location —
with every column sortable.

## Purpose

One live table answering "who is on my network right now, and how hard?"
plus four summary cards (↓ total, ↑ total, active apps, busiest). Rows
update in place from the shared snapshot stream — the Processes page owns
the single drain and forwards snapshots here (single-drain law, r046).

## Data model (honesty first)

- Rates come from the **r053 socket-owner attribution**: `/proc/<pid>/fd/*`
  → socket inodes → `/proc/net/{tcp,tcp6,udp,udp6}` tables, each interface's
  delta split proportional to open-duration share. The kernel has no
  per-socket byte counters without eBPF/root (both rejected) — the page
  LABELS this in its subtitle and column semantics ("attribution
  (proportional), not kernel accounting").
- Restricted pids (Yama ptrace_scope=1, other users) attribute `None` → the
  row renders lock + "—" rates, but IS listed when it holds sockets.
- "Actively" = attributed with nonzero total rate, OR holding sockets (a
  long-lived listener with zero current traffic is still a network process;
  its rates read "—" until traffic flows).
- Open-socket counts: `sampler.open_sockets()` → `NetAttributor.open_sockets()`
  (public passthrough added r113) — the fd-cache map, no extra scans.

## Columns (all sortable, page-owned sort state)

| Column | Store col | Kind | Sort |
|---|---|---|---|
| Process | 0 | text (casefold) | asc/desc on click |
| User | 1 | text (casefold) | asc/desc |
| Conns | 2 | int, unknown −1 | unknowns last |
| ↓ Rx/s | 3 | float, unknown −1 | unknowns last |
| ↑ Tx/s | 4 | float, unknown −1 | unknowns last |
| Total/s | 5 | float (rx+tx), unknown −1 | unknowns last — DEFAULT desc (busiest first) |

Sort state is PAGE-OWNED (`_sort_state`), not GTK's `get_sort_column_id` —
the GTK indirection made the unknowns-last sign flaky under test. Header
click: new column → desc; same column → toggles. The comparators flip their
unknown sign to match so unknowns land LAST in both directions
(process-table convention).

Hidden store columns 6/7 carry (pid, starttime) for future click-through.

## Row lifecycle

Keyed diff-in-place: rows update rates in place (no flicker), new apps
append, departed apps remove. Active-only filter: attributed with
nonzero total, OR holding sockets. Zero rows → summary cards read "—" and
the table is simply empty (a machine with no traffic is healthy, not
broken — r039 taxonomy).

## v2 (designed, not built)

Per-app click-through performance monitor (the operator's item 9): a
per-app detail page with a connection-frequency pane (connection events per
interval from the NetAttributor's first-seen ledger) + rx/tx history from a
dedicated manager_history ring (bounded, ring law). Mockup Q
(`docs/mockups/mockup-q-network*.png`) sketches it. Requires: per-app ring
allocation policy (cap the number of tracked apps; evict least-recently-seen)
— needs a schema-freeze style sign-off before build.

## Tests

`tests/test_network_page.py` — active-only filtering (unattributed and
idle-excluded), in-place keyed updates, departed-app removal, sortable
columns with unknowns-last in both directions, socket-holder listing,
summary band values.
