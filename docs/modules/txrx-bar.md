# Component spec — the Tx←→Rx packet-tick bar (network representation)

Part of the linprocman modular docs. Companions:
[network-page.md](network-page.md) (the page that shipped it) ·
[process-preview.md](process-preview.md) §4 (the attribution model whose
numbers the bar displays) · [sampling-pipeline.md](sampling-pipeline.md)
(the schema keys that feed it: `net_rx_rate` / `net_tx_rate`).
Renderer: `ui/compat/charts.py::txrx_bar_surface` / `draw_txrx_bar`
(mockup R — CONFIRMED by the operator r129: "you have it exactly in
ANATOMY").

## 1. What it is

THE network-activity representation of linprocman — one visual language
every network feature shares. A 160 × 12 px bar (the Disks usage-bar
geometry, §5b fixed box) that reads as a train of little vertical
rectangles ("packet ticks"):

```
┌────────────────────────────────────────────────────────┐
│▓▓ ▓▓▓ ▓▓    ┊        │ ▓ ▓▓▓▓ ▓  ▓▓▓ ▓▓▓▓ ▓▓▓          │
└────────────────────────────────────────────────────────┘
  Tx → grows toward the center   ← Rx grows toward the center
  (yellow #facc15)                (blue #2196f3)
```

- **Tx (transmitted, yellow `#facc15`)**: ticks packed from the **LEFT
  edge**, growing **toward the center**.
- **Rx (received, blue `#2196f3`)**: ticks packed from the **RIGHT edge**,
  growing **toward the center**.
- **Center line** (`#3a3a3a`, 1px) = zero. Trough `#1b1b1b`.
- Uneven traffic opens a trough gap **around the center**; balanced traffic
  (e.g. syncthing) reads as equal halves meeting at the middle —
  "uploading as much as it downloads" at a glance.
- Ticks are **little vertical rectangles** (3px tick + 2px gap — packet
  bursts), the operator's confirmed design: they simulate packets visually
  instead of a flat volume fill.

Confirmed behavior, per the operator's red-line iterations: the boundary
is **never negotiable** — the bar's two halves always occupy exactly their
share, and the anchor edges (left = Tx, right = Rx) are fixed.

## 2. The math (how ticks are calculated)

Per rendered bar, the caller supplies **per-side tick counts**:

```
tx_ticks = round(tx_share × ticks_per_half)      # ticks_per_half = ⌊W/2⌋ ÷ 5
rx_ticks = round(rx_share × ticks_per_half)
minimum 1 tick per side when that side's rate is nonzero
```

- `ticks_per_half` = ⌊160/2⌋ ÷ 5px = **16 packets per half** (32 max).
- **Per-side normalization**: `tx_share = tx / max_tx` and
  `rx_share = rx / max_rx`, where max_rx / max_tx are the busiest process
  on the CURRENT surface (page). A side with no data normalizes to zero —
  bars never inherit another page's scale.
- `0` share → `0` ticks (empty half). Nonzero share rounding down to 0
  ticks is floored to **1** — a nonzero rate is always visible.
- Restricted processes (Yama, rates `None`): the caller passes **0 ticks**
  and renders the lock + "—" in the text columns; the bar draws the trough
  + center line alone. Never a fabricated fill.

Worked example (Network page, one tick): librewolf at rx 1.1 MB/s / tx
88.2 KB/s with max_rx 1.1 MB/s and max_tx 900 KB/s → rx_ticks 16, tx_ticks
2 → a full blue half and a small yellow stub at the left.

## 3. How it is produced (implementation)

Two layers, both in the compat charts seam:

- `charts.txrx_ticks(width, tx_share, rx_share)` → tick counts (pure;
  the only place the 5px period lives).
- `charts.txrx_bar_surface(width, height, tx_ticks, rx_ticks)` → a cairo
  ARGB32 surface: trough, center line, then the tick rectangles packed
  from each edge. `charts.draw_txrx_bar(cr, w, h, …)` draws onto an
  existing context (live widgets).
- `page_network._bar_pixbuf(tx_ticks, rx_ticks)` wraps the surface in a
  GdkPixbuf for the tree-view cell, **cached by tick counts** — only
  17×17 possible bars exist, each generated once.

Constants live ONCE, in the seam: `TX_TICK_RGB #facc15`,
`RX_TICK_RGB #2196f3`, `TXRX_TROUGH_RGB #1b1b1b`,
`TXRX_MIDLINE_RGB #3a3a3a`.

## 4. Where it is used

| Surface | Since | Call |
|---|---|---|
| Network page — "Tx ← → Rx" column (in front of Total/s, per operator) | r129 | `_bar_pixbuf(tx_ticks, rx_ticks)` per row; per-side max normalization across the visible rows |

Adoption path for any new network feature (per-app monitor pane v2,
history overlays, the preview's networking section): compute the per-side
shares on THAT surface, call `txrx_ticks` + `txrx_bar_surface` (or
`draw_txrx_bar` into the widget's cairo context), and keep the
attribution honesty label adjacent to the bar. Do not introduce a second
bar style.

## 5. Rules

- The split is structural (Paned midline / fixed columns) — content can
  never skew the halves (the r075→r108 lesson chain).
- Dynamic labels near the bar carry §5b pins (width_chars + ellipsize).
- Attribution labeling accompanies every appearance of the bar.
- No fabricated fills: unknown sides draw empty; restricted shows lock +
  "—" in the text columns, never a colored estimate.

## 6. Tests

`tests/test_network_page.py::test_txrx_bar_column_pixbufs` — distinct
pixbufs for rx-heavy vs tx-heavy rows, column order (bar in front of
Total/s). The seam's tick math is pure and covered by the page tests'
tick-count assertions; extend with surface-pixel checks if the draw
grammar grows.
