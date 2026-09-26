# Module doc — log frequency analysis (`src/modules/manager_frequency.py` + view in `page_logs.py`)

Part of the linprocman modular docs. Siblings: [logs-journal.md](logs-journal.md) ·
[procfs-data.md](procfs-data.md) · [sampling-pipeline.md](sampling-pipeline.md) ·
[process-table.md](process-table.md) · [actions-permissions.md](actions-permissions.md) ·
[resource-graphs.md](resource-graphs.md) · [persistence-config.md](persistence-config.md) ·
[disks-filesystems.md](disks-filesystems.md) · [sysfs-data.md](sysfs-data.md).
Overview: [../process-manager-concept.md](../process-manager-concept.md).

Operator-mandated (r040): right-click a log entry → **Frequency** opens a
charting view showing how that error occurs over time, with related events
plotted before and after each incident. Aimed at medium-to-serious errors.

## Purpose

Turn the currently loaded journal window into temporal analytics for one
message pattern: occurrence histogram, incident detection, related-event
context, export. Read-only over in-memory entries — no second journal read.

## Interface

Consumes: the loaded entries from [logs-journal.md](logs-journal.md) (already
bounded and capped there) + the selected entry as the seed pattern.

Provides:
- **Pattern key (the heuristic):** the seed message is normalized into a
  template — digits → `N`, hex/UUID → `H`, IPs/paths → `P`, quoted strings
  collapsed — so "I/O error, dev nvme0n1, sector 1953525136" and
  "…sector 1953525220" count as ONE pattern. Pattern shown above the chart
  with a live match count; editable if the normalization over-groups.
- **Chart view:** cairo DrawingArea, same theme-derived palette as the
  resource graphs —
  - occurrence bars per time bin (auto bin: window/120, snapped to
    1 min / 5 min / 1 h), y = entries per bin for this pattern;
  - **related events:** all other entries in a ±lookback window around each
    bin, plotted as small priority-colored markers on a secondary strip
    (err red, warning amber, info gray) — the "before and after" context;
  - **incident bands:** bins above threshold (max(3, median×4)) group into
    incidents; each incident gets a highlighted band across both strips with
    start/end brackets;
  - hover on a bar → tooltip with exact time range + count; click → the
    incident table scrolls to it.
- **Incident table:** one row per incident — start, end, duration, count,
    peak/bin, top 3 related units (by co-occurrence in the band). Row click
    jumps the journal view to the incident start (cursor scroll-to).
- **Export (both local, FileChooser, sanctioned in build-principles §5):**
  chart as PNG (cairo surface write), binned data + incidents as CSV.

## Context-menu gating

The Frequency item is offered on every entry but the view self-tunes:
warning/err seeds default to incident mode (bands + related strip); info/
debug seeds default to plain histogram (bands off) — the operator's
"medium-to-serious" focus without hiding the tool for noisy info patterns.

## Rules

- Analysis window = the loaded window only (cap inherited from the logs
  view). If the window is small, the view says so and offers "load older"
  which re-uses logs-journal cursor paging, then re-analyzes.
- Pure functions: entries+params → bins/incidents/related — unit-testable
  without GTK; the DrawingArea only renders results.
- No persistence of analyses in v1 (a saved view may reopen Frequency with
  its saved query, re-running the analysis).

## Tests

Template normalization units (digits/hex/IP/path/quoted; over-group guard),
bin snapping, incident threshold edge cases (flat noise, single spike,
continuous high), related-window co-occurrence counting, CSV shape.
