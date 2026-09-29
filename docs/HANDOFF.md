# linprocman — Handoff (2026-09-28, session close)

Supersedes the 2026-09-27 machine-restart handoff (that restart happened;
everything in it was verified). This document is the complete resume state
for the next session — a fresh mind, a fresh checkout, or a fresh machine.

## 1. State at handoff

- **HEAD:** `c2a8d41` on `main`, working tree clean, pushed to
  MensuraMedia/linprocman. 40 commits since the previous handoff
  (`a68c77e`), every one changelogged.
- **Tests:** **421 + 5 green** (421 unit/fixture/UI + 5 opt-in `-m live`),
  gates green (raw-import, banned-API, claude-path, subprocess-argv).
- **Backups:** through `20260928-203542` (s009, 20M) — taken at this handoff.
- **The running app:** `linprocman-app.service` (transient systemd unit,
  `systemd-run --user`) on the current build; window verified; journal
  clean since the r136 fit-id fix (zero "Source ID" warnings).
- **Phases/features shipped:** Processes (live table + 25-column chooser +
  preview pane + signals/priority/affinity + group termination + kill
  verification), Graphs hub + 7 detail pages with the Basics cards merged
  on top, Disks (capacity + I/O, live), Network (per-process traffic with
  the Tx←→Rx packet-tick bar, importance marks, tracking + pattern
  classifier, properties sidebar), Peripherals (USB + sensors), Logs
  (journal engine + functional page), Settings (incl. baseline
  recalibration), tray + menu + installer with revision stamp,
  USER_MANUAL.md for end users.

## 2. Everything since the previous handoff (a68c77e → c2a8d41)

Grouped narrative; `changelog.md` holds the per-item detail.

### Layout and navigation corrections

- **r080 — sidebar flanking fixed at root:** the r075 label `set_hexpand`
  propagated up the widget chain (GTK3) and made the whole Sidebar
  expansion-hungry — it floated centered with dead strips both sides.
  Regression test pins the flush-left layout.
- **r092 — the sidebar submenu is RETIRED:** Basics content merged into the
  top of the Graphs hub; the Basics button and the Graphs caret removed.
  The r081 caret work (Paned-toggle experiments, press_swallow seam) was
  deleted with it — git history preserves it.
- **r098 — preview pane (mockup J) + 25 extended columns** shipped by
  executor (task 010) on the signed schema freeze (r093, 30 fields).

### The Network page (new feature, r113 → r130 → r133 → r134)

- Per-process live traffic table, every column sortable (page-owned sort
  state, unknowns-last), keyed in-place row updates.
- The **Tx←→Rx packet-tick bar** (mockup R, CONFIRMED) in front of
  Total/s: Tx grows from the left edge toward the center, Rx from the
  right edge; ticks = Bytes/KB increments (64 B/s doubling); each side
  normalized to the busiest process on its side. Renderer lives in the
  charts seam (`txrx_bar_surface`/`draw_txrx_bar`/`txrx_ticks`) — ONE
  implementation for every network feature. Spec: `txrx-bar.md`.
- **Importance marks** (High/Medium/Low, persisted per process name in
  `netwatch.json`), **Track/Stop tracking** with per-process rings, the
  **pattern classifier** (regular-intervals / telemetry-like /
  irregular-spikes / quiet / insufficient-data — heuristic, labelled as
  such), and the **properties sidebar** (mockup T, as shipped).
- **r134 fixed the operator's non-functional right-click menu:** the action
  callbacks took zero args while make_action delivers (action, parameter) —
  every click raised TypeError. Lesson: TESTS MUST DRIVE THE ACTION LAYER,
  not the handlers directly.

### Disks (Phase 6 core, task 011)

- Capacity + I/O table (executor, worktree), zone-colored usage bars with
  threshold ticks (160×12 — now the app-wide bar standard), inode column,
  flagged unmounted rows, hidden pseudo/loop count row, mount reader with
  octal-escaped paths.
- **r118/r120:** uniform 4px cell margins (the disks-* classes previously
  had NO CSS) and the VIVID zone palette (page_disks had kept the old
  muted table).

### Logs (Phase 7 core, task 013)

- `manager_logs.py` argv-contract engine (journalctl, argv-list-only —
  gate-extended) + functional page: presets, unit/priority filters,
  severity coloring. Saved views (014) and frequency (015) queued.

### Unification and polish

- **Every usage bar in the app is now 160×12** (Disks geometry): Processes
  band gauges, Basics performance bar, contributor mini-bars.
- **Vivid zone palette everywhere** (green #22c55e, yellow #facc15, red
  #ef4444) — page_disks was the last muted holdout.
- **r136:** the debounced column-fit clears its GLib source id — the
  "Source ID not found" journal spam (thousands of lines) is gone.
- **Installer:** revision stamp + working `--version` (two heredoc-
  expansion bugs fixed: `$0` baked `./install.sh` into the launcher).
- **r139:** `docs/USER_MANUAL.md` — the complete end-user manual, linked
  from README.
- **r136-r140:** mockup catalog (README with per-mockup status), mockups
  Q/R/T, component spec `txrx-bar.md`.

### Defect classes caught this cycle (process lessons)

1. **GTK3 hexpand propagates up the ancestor chain** (r080) — a label's
   hexpands made the whole Sidebar expansion-hungry. NEVER pin hexpand on
   deep children to size a parent.
2. **Zero-arg action callbacks silently do nothing** (r134) — make_action
   delivers (action, parameter); tests must drive the ACTION layer.
3. **Dead code after `return`** (r111) — refs registered after the return
   left cards as empty frames. AST-check new code paths.
4. **Page_disks-class drift**: when a palette or convention changes, grep
   for the OLD values in EVERY page — one file always lags.
5. **Executor dispatches run in ISOLATED WORKTREES** (r103+) — never on the
   live checkout (the r111 incident: mid-edit schema code broke the
   running app at restart).

## 3. Run and verify

```bash
cd ~/projects/linprocman
git status                 # expect clean
git rev-parse --short HEAD # expect c2a8d41 (or newer)
python3 -m pytest tests/ -q          # 421 passing
python3 -m pytest tests/ -q -m live  # +5 live tier
systemctl --user restart linprocman-app
systemctl --user is-active linprocman-app
journalctl --user -u linprocman-app --since '-60 s' | grep -c 'Source ID'
#   expect 0 (the r136 fit-id fix)
```

Live page gates (each verified this session): Processes (populated table,
band, preview pane, context menu incl. signals + group ops), Graphs
(Basics cards + hub, 50/50 splits, vivid zones), Disks (real mounts, zone
bars, margins), Network (151 socket-holders, 15 actively transferring,
Tx←→Rx bars, marks/tracking/sidebar), Peripherals (USB cards + sensor
chips), Logs (presets + real journal), Settings, About, tray, menu entry,
`linprocman --version` → revision.

Journal: `~/.local/state/linprocman/linprocman.log` (rotating) — the
authoritative record; stderr mirrors it for journalctl.

## 4. Open defects and watch items

- **fit_source_id**: FIXED r136 (id cleared when the debounced pass fires).
  Watch one resize cycle to confirm no regression.
- **Menu placeholders**: Show in tree, Frequency…, View journal for unit…
  remain grayed (tasks 013-015/010 remnants); Open executable location is
  functional.
- **Submenu retirement debt**: none in code; docs references updated.
- **telemetry-like naming**: deliberately softened (r055 lesson) — keep it
  a pattern description, never an accusation.
- **Attribution honesty**: the Network page labels rates as proportional
  estimates; keep that label on every new surface.
- **GTK4 port**: `press_swallow` was removed with the caret; the seam's
  `click_gesture(min_press=)` is the portable pattern.

## 5. Queued work with precedence

1. **Task 014 — Logs saved views + flags** (mockup F).
2. **Task 015 — Logs frequency analysis** (mockup G).
3. **Network v2** — per-app monitor pane + history (mockup Q2/Q3
   directions CONFIRMED via the Tx←→Rx bar work); needs the per-app ring
   policy sign-off before build.
4. **Disks v2** — per-mount history sparklines (spec'd in
   disks-capacity.md §3 item 5).
5. **Phase 8 — ship**: version stamp, .deb packaging, v1 tag.

## 6. Operational notes (standing laws + this cycle's additions)

- **Offline**: no network imports under `src/` (grep-gated).
- **Assets**: only from `~/projects/assets/icons`, copied in.
- **Boundary law**: procfs/sysfs/sampler/actions/netattr/netwatch stay
  UI-free and headlessly testable.
- **Import law**: no raw gi outside `ui/compat`; pages import toolkit
  symbols from the compat seams.
- **Raw-import order trap**: tests/scripts must import the `ui` package
  before `pages`/`modules` — the pages⇄ui chain only resolves from the ui
  side.
- **§5b bounding-box policy**: fixed boxes; pinned labels
  (width_chars + max_width_chars + ellipsize); wrapped labels' NATURAL
  request is their full single-line text — cap it or it crushes siblings.
- **Single-drain law**: the Processes page owns the one sampler drain and
  forwards to observers; observers must never raise (an exception kills
  the drain source).
- **Action callbacks** receive (action, parameter) — zero-arg lambdas
  raise TypeError on activation (r134).
- **Executor collaboration**: ZCode contracts → Claude executes headless
  (`--permission-mode acceptEdits`, no Bash) in an ISOLATED WORKTREE
  (`git worktree add -b task-NNN /tmp/lpm-NNN HEAD`) — never the live
  checkout (the r111 incident: mid-edit code broke the running app).
  Integrate by scoped file copy after the worktree-verified suite; record
  the dual-import trap (tests import ui first).
- **Never `pkill -f` a pattern that appears in your own command line** —
  use the `main[.]py` bracket trick.
- **Never `pkill` by pattern at all when a pid is known** — kill by pid.
- **changelog.md is append-only**; the ledger (Zai-ZCode/s-register.md)
  tracks the response marker per project.
- **Backup after every completed phase** (s009; latest
  `20260928-203542`).
