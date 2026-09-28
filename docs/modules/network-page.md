# Module doc — Network page (`src/pages/page_network.py`)

Part of the linprocman modular docs. Siblings:
[process-preview.md](process-preview.md) (§4 — the attribution design this
page renders) · [process-table.md](process-table.md) ·
[sampling-pipeline.md](sampling-pipeline.md) ·
[manager_netattr source](../../src/modules/manager_netattr.py) ·
[disks-capacity.md](disks-capacity.md). Overview:
[../process-manager-concept.md](../process-manager-concept.md).

Shipped r113 (operator): a dedicated **Network** sidebar entry (between
Disks and Peripherals) listing the processes that are actively sending
and/or receiving packets — to the internet or any other network location —
with every column sortable and a four-card summary band. This document is
the comprehensive engineering reference: what the feature is, every moving
part, how data flows end to end, how it is configured, how it is tested,
and where the v2 design stands.

---

## 1. What the feature is

One live table answering "who is on my network right now, and how hard?":

- One row per **process with live network activity** — attributed rx/tx
  rates, open-socket count, user. Rows update **in place** on every
  sampler tick (no flicker, no rebuild).
- **Every column sorts.** Click a header once → descending; click again →
  ascending. Unknown values (restricted processes) sort **last in both
  directions** — the process-table convention.
- A four-card **summary band** above the table: ↓ total received, ↑ total
  sent, active apps, busiest process.
- An honesty banner in the page subtitle: rates are **socket-owner
  attribution (proportional) — not kernel accounting**.

The sidebar entry sits between **Disks** and **Peripherals**
(`NAV_ITEMS` in `src/ui/sidebar.py`).

---

## 2. Data flow, end to end

```
/proc + /sys (kernel)
   │  Sampler thread (one pass per refresh_interval_s, 0.5–5.0 s,
   │  default 2.0 — settings key refresh_interval_s)
   ▼
manager_netattr.NetAttributor.poll()
   │  incremental fd-scan (mtime-cached): /proc/<pid>/fd/* → socket inodes
   │  /proc/net/{tcp,tcp6,udp,udp6} → inode tables
   │  each interface's rx/tx delta split across sockets by open-duration
   │  share (open_weight), then equally among a socket's holders
   │  restricted pids (Yama EACCES) → None
   ▼
Sampler._enrich_net()  (post build_snapshot — mutates plain record dicts)
   │  writes rec["net_rx_rate"], rec["net_tx_rate"]  (float | None)
   ▼
snapshot queued → single drain (Processes page, r046 law)
   │  GLib idle on the UI thread; forwards to registered observers
   ▼
NetworkPage.on_snapshot(snapshot)
   │  sockets = sampler.open_sockets()      ← pid → open-network-socket count
   │  filter → keyed diff → store update    ← main thread only (GTK)
   ▼
Gtk.ListStore rows + summary band labels
```

Boundary law holds end to end: `manager_netattr.py` and the sampler are
UI-free and stdlib-only; the page never reads `/proc` — it consumes
snapshot records and the sampler's public `open_sockets()` summary.

### 2a. The attribution model (why rates are "proportional")

The kernel exposes no per-socket byte counters without eBPF or root — both
rejected by the mandates. The honest substitute:

1. Each pass maps open network sockets → owning pids (fd-table scan).
2. The machine's **total** interface rx/tx delta for the interval is known
   exactly (from `/proc/net/dev`-class readers).
3. That delta is split across the open sockets, weighted by how much of the
   interval each socket was open (`open_weight`, clamped 0–1), then equally
   among a socket's holders.
4. A process holding the *only* socket receives the whole delta — exact. A
   process among many receives a labelled estimate.

The UI says so, everywhere the numbers appear. Column semantics, page
subtitle, and the preview pane all carry the attribution note. **Never
present these numbers as measured per-process bandwidth.**

### 2b. Restricted processes (Yama ptrace_scope=1)

Reading another process's fd table raises EACCES on stock Debian-family
kernels. Those pids are *restricted*: `net_rx_rate`/`net_tx_rate` stay
`None`, and the row renders **lock + "—"** — but the row itself still
lists, because holding sockets is known even when the rates are not
(fd-table metadata is readable even where contents are not, in the common
case; where even that fails, the pid is absent and nothing is fabricated).

---

## 3. Row lifecycle (the keyed diff-in-place algorithm)

```
on_snapshot(snapshot):
    sockets = sampler.open_sockets()
    active = {}
    for key, rec in snapshot.procs:
        rx, tx = rec.net_rx_rate, rec.net_tx_rate
        conns  = sockets.get(pid)
        skip   = (rx is None and tx is None and not conns)   # not a net user
        skip  |= ((rx or 0) + (tx or 0) <= 0 and not conns)  # attributed, idle
        if not skip:
            active[key] = {...}

    for key in rows:            # departed → remove
        if key not in active: store.remove(rows.pop(key))
    for key, info in active:    # present → update in place
        changed cells only      # no flicker
    new keys → append
```

- "Actively" = attributed with a nonzero combined rate, **or** holding
  sockets (a long-lived listener with zero current traffic is still a
  network process; its rates read "—" until traffic flows).
- Row identity is `(pid, starttime)` — recycled pids never collide.
- The update writes **only changed cells** (the r098 diff discipline).

---

## 4. Sorting (page-owned state machine)

The sort is **page-owned** (`_sort_state = {"col", "desc"}`), deliberately
not GTK's `get_sort_column_id` indirection — that made the unknowns-last
sign flaky under test (the comparator could not tell which column's
direction it was serving).

- `_on_header_clicked(column, col_id)`: new column → desc; same column →
  toggle. Then `_apply_sort()`.
- `_apply_sort()`: `store.set_sort_column_id(col, Gtk.SortType…)` per the
  state.
- The registered comparators read the state: numeric columns treat
  `None`/`-1` as **unknown**, and the unknown's comparison sign flips with
  the direction so unknowns land **last in both directions**. Text columns
  sort casefolded.
- Default state: **Total/s descending** — busiest first, on first visit.

Columns: Process (text), User (text), Conns (int), ↓ Rx/s, ↑ Tx/s,
Total/s (rates) — hidden store columns 6/7 carry `(pid, starttime)` for
future click-through. Rate cells render through a data func ("—" for
unknown/negative; human-scaled B/s…TB/s otherwise).

---

## 5. Page anatomy

```
NetworkPage (BasePage, spacing 12 / margin 24)
├── title + honesty subtitle
├── summary band — 4 fixed cards (§5b): ↓ total · ↑ total · active apps · busiest
└── ScrolledWindow
    └── TreeView (6 visible columns + 2 hidden key columns)
```

- Summary values are recomputed from the same `active` map the rows come
  from — the band and the table can never disagree.
- "Busiest" = the highest `rx + tx` this tick; renders "—" when the map is
  empty.
- Empty state: zero rows → the cards read "—" and the table is empty. A
  machine with no traffic is healthy, not broken (r039 taxonomy).

---

## 6. Configuration surface

| What | Where | Default |
|---|---|---|
| Update cadence | `settings.refresh_interval_s` (shared sampler tick) | 2.0 s (0.5–5.0 clamp) |
| Sidebar position | `NAV_ITEMS`, `src/ui/sidebar.py` | between Disks and Peripherals |
| Default sort | `_sort_state` in `_build_table` | Total/s, descending |
| Visible columns | fixed in v1 (6 of 6) | all |
| Attribution honesty labels | page subtitle + doc | fixed |

Nothing user-configurable is unique to this page in v1 — it deliberately
shares the sampler cadence and the settings file conventions. v2 candidates
(behind new settings keys, each needing a decision): an idle-socket-holders
toggle, a per-app history retention cap, and a per-app monitor pane
(designed in mockup Q2).

---

## 7. Wiring map (who owns what)

| Piece | File | Notes |
|---|---|---|
| Attribution engine | `src/modules/manager_netattr.py` | core, UI-free, DI-seamed for tests |
| Sampler enrichment + `open_sockets()` | `src/modules/manager_sampler.py` | `poll()` wrapped best-effort; failures degrade to no attribution, never the watchdog |
| Rates in records | sampler post-hoc `_enrich_net` | mutates plain record dicts after `build_snapshot` |
| Page | `src/pages/page_network.py` | consumes snapshots + the public passthrough |
| Sidebar entry | `src/ui/sidebar.py` `NAV_ITEMS` | "Network" between Disks and Peripherals |
| Registration + observer + sampler handoff | `src/ui/content_area.py`, `src/ui/dashboard_window.py` | `network_page.on_snapshot` in the observer list; `set_sampler()` wired beside the Processes page's `attach_sampler` |

`NetAttributor.open_sockets()` and `Sampler.open_sockets()` were added
r113 as public passthroughs — **no extra fd scans**: the page reads the
map the sampler's own pass already maintains.

---

## 8. Testing

`tests/test_network_page.py` (UI tier, skips without DISPLAY):

- active-only filter: unattributed and idle processes excluded.
- keyed updates: rates change in place; new apps append; departed apps
  remove — across three successive snapshots.
- sorting: descending busiest-first; ascending flip; unknowns (-1)
  last in BOTH directions; socket-holder with unknown rates listed.
- summary band values (rx/tx totals, active count, busiest name).

The attribution engine itself is covered by `tests/test_netattr.py`
(~16 cases: exact single-holder, proportional split, Yama None, shared
sockets, honest zero, first-sample weights, injected fake /proc trees).

Live gate on `:0`: navigate to Network with the real sampler running —
rows populate from the live machine (verified r113: 132 rows with real
per-process rates, busiest = wineserver).

---

## 9. Performance notes

- The page does **no I/O**: it filters and renders dicts already in memory.
- Row updates are bounded by the active-app count (tens of rows typical;
  the 132-row worst case observed is still O(n) cell compares per tick).
- The underlying attribution is the bounded part — incremental fd scans
  (mtime-cached), set math otherwise, wrapped so failure degrades to "no
  attribution" and never trips the sampler watchdog.

---

## The Tx←→Rx packet-tick bar (r129, mockup R — CONFIRMED)

Each row carries a **160×12 bar (the Disks geometry)** rendering network
activity as the mockup R design — confirmed by the operator:

- **Tx ticks (yellow #facc15)** are packed from the **LEFT edge**, growing
  toward the center; **Rx ticks (blue #2196f3)** are packed from the
  **RIGHT edge**, growing toward the center. The **center line = zero**.
- Each side is normalized to the busiest process on ITS side
  (max_rx / max_tx across the current rows); ticks = round(share × 16),
  minimum 1 tick when the rate is nonzero. Uneven traffic opens a trough
  gap around the middle; balanced traffic reads as equal halves meeting at
  the center ("uploading as much as it downloads" at a glance).
- Ticks render as **little vertical rectangles** (3px tick + 2px gap —
  packet bursts), per the operator: "little vertical rectangles to
  simulate … packets visually".
- Restricted rows (rates None) draw the trough + center line alone.
- The bar sits **in front of the Total/s column** (operator) and is not
  itself sortable — Total/s is its number. Implemented as a cached pixbuf
  per (tx_ticks, rx_ticks) — 17×17 possible bars, generated once
  (`_bar_pixbuf`), stored in `_COL_BAR` (store column 6).
- Full component spec: [txrx-bar.md](txrx-bar.md) — the reusable renderer
  lives in the charts seam (`charts.txrx_bar_surface` / `draw_txrx_bar`);
  every network feature draws ITS bar through that one function.

## 10. v2 — designed, not built (needs approval + a sign-off gate)

Per-app click-through monitor (mockup Q2) and a history pane (Q3):

- **Per-app rx/tx history**: a dedicated `manager_history` ring per tracked
  app — ring law applies (gaps are gaps). Allocation policy is the open
  design question: cap the tracked-app count, evict least-recently-seen;
  needs a schema-freeze-style sign-off before build (r048/r093 precedent).
- **Connection frequency**: the NetAttributor's first-seen ledger already
  records socket appearance — a "new/changed sockets per interval" counter
  per app gives the bursty-reconnect signal (mockup Q2's frequency bars).
- **Collective history pane** (Q3): window selector (10 min / 1 h) over
  collective rx/tx + connection spikes.
- Build order: sign-off → manager_history extension → pane → tests, one
  executor dispatch.

---

## 11. Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| All rate cells "—" for other users' processes | Yama ptrace_scope=1 — by design | none; the lock marker is the honesty signal |
| A killed app's row lingers one tick | keyed removal runs on the next snapshot | none; gone within one interval |
| Row count seems high (100+) | every socket-holding process lists when it has traffic | sort by Total/s desc; idle rows sink |
| Page empty, band "—" | sampler not started, or no attribution this pass | check the journal for `netattr` degrade lines; verify the Processes table is live (same drain) |
