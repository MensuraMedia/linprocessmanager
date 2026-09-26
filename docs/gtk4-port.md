# linprocman — GTK3 → GTK4 port strategy

Status: planning document (r043, 2026-09-26). v1 ships on GTK3 (concept §7
non-goal stands); this document defines the path that makes the eventual
port a mechanical sweep instead of a rewrite. Reviewed by the collaborator
(Claude) for GTK4 factual accuracy before commit.

## 1. Ground truth — verified on this machine (2026-09-26)

| Fact | Status |
|---|---|
| GTK 4.14.5 present and importable (`gi.require_version("Gtk","4.0")` works today; `gir1.2-gtk-4.0` 4.14.5+ds-0ubuntu0.10 in noble repos) | verified |
| GTK3 runtime 3.24.41 — v1 target, unchanged | verified |
| Both toolkits importable in the same system-python environment; GTK3 and GTK4 apps coexist | verified |
| Current GTK3-only API surface: **~21 greppable call sites in 2,157 lines / 26 files** — 18 `pack_start/pack_end`, 1 `show_all`, 1 `button-press-event`, 1 `connect("draw")`; zero RadioButton, zero legacy `Gtk.Menu`, zero `Gtk.Dialog`. This is a *seam census, not a full surface count* — collaborator review (r043) flagged the un-grepped remainder: `container.add()/.remove()`, `widget.destroy()`, `set_border_width`, CSS-provider registration | verified by grep + review |

## 2. Why this port is structurally cheap here

1. **The core is UI-free by mandate.** `procfs.py`, `sysfs.py`, the sampler,
   the actions module, the frequency analyzer — none import GTK. Porting
   cost is confined to `src/ui/`, `src/pages/`, and chart/widget code.
   The r041 modularity rule is what makes this true; keep enforcing it.
2. **The table layer ports almost untouched.** Gtk.TreeView, ListStore,
   TreeStore, TreeModelFilter, TreeSortable, TreeRowReference,
   TreeSelection, CellRenderers and `set_cell_data_func` **all exist in
   GTK4** — with the honest caveat (collaborator review): the TreeView
   family is **deprecated since GTK 4.10**. On 4.14 it works and only
   warns; it is the one subsystem on a GTK5 removal track. The diff-in-place
   engine, typed columns, and filter machinery carry over as-is; the
   optional ColumnView migration may move *earlier* than post-port if
   deprecation hygiene demands it (§6).
3. **Charts are cairo in both toolkits.** Only the draw-callback hookup
   changes (`connect("draw")` → `set_draw_func`); the cairo drawing code
   itself is toolkit-agnostic.
4. **The app is 6 phases from done, not shipped-and-crusted.** Every seam
   rule below is cheap to apply *while building* and expensive to retrofit.

## 3. The API delta that actually touches us

| GTK3 (today) | GTK4 | Our exposure |
|---|---|---|
| `Gtk.main()` / `Gtk.init()` | `Gtk.Application` + `app.run()`, `activate()` | none yet (starter uses plain Gtk.main) — adopt Application NOW (works in GTK3) |
| `box.pack_start(child, expand, fill, padding)` | `box.append` + expand props (**Box only** — HeaderBar/ActionBar pack_* survive in GTK4) | **18 sites** — sidebar, pages, panes; gate scoped to Box |
| `window.show_all()` | widgets visible by default; `window.present()` | 1 site |
| `container.add()/remove()` | `set_child()` (Window, ScrolledWindow, Frame, Button, Viewport…) | un-grepped, larger than pack — needs its own seam |
| `widget.destroy()` | `window.close()` / child `unparent()` | dialog close paths — folded into the dialog adapter |
| `set_border_width` | margin properties | shell/pages |
| `button-press-event` / `key-press-event` signals | event controllers: `EventControllerKey`/`EventControllerMotion` exist in both toolkits; **click gesture is `GestureMultiPress` in GTK3, renamed `GestureClick` in GTK4** — version-switched adapter | 1 site today; context menus, keyboard ops, Frequency hover all grow here |
| accelerators / shortcuts | `ShortcutController` is GTK4-only — the portable seam is `Gio.SimpleAction` + `app.set_accels_for_action()` (both toolkits) | none yet — keyboard phase must use actions+accels |
| `Gtk.Menu` / `Menuitem` | `Gtk.PopoverMenu` + `Gio.Menu`; **Gio.Menu model ports cleanly, popover wiring does not** (GTK3 `Popover.bind_model` vs GTK4 `PopoverMenu.new_from_model`) — thin adapter | zero today; menus as model+adapter from day one |
| `Gtk.Dialog` / `MessageDialog` | plain `Gtk.Window` (+ `Gtk.AlertDialog` ≥4.10 for confirms) | zero today — kill/renice/signal dialogs use the safe pattern |
| `connect("draw", cb)` | `drawing_area.set_draw_func(cb)` | 1 site today; all charts inherit the fix if wrapped once |
| `Gdk.threads_*` | removed | unused (GLib.idle_add discipline already correct) |
| CSS on removed properties / widget margins in CSS; provider registration `StyleContext.add_provider_for_screen` → `add_provider_for_display`; `get_style_context().add_class()` → `widget.add_css_class()` (both toolkits since 4.0; write it that way where GTK3 allows) | class-based starter CSS is low risk; provider load goes through one theme-manager helper |
| `Gdk.Pixbuf` in renderers | `Gdk.Texture`/`Paintable` (Pixbuf still exists for loading) | icon tint pipeline (Pillow) unchanged; wrap the final pixbuf→widget step in one helper |
| `Gtk.RadioButton` | `ToggleButton` + group | zero today; theme selector uses toggles — keep it that way |

## 4. Portability seams — rules to adopt NOW (the "easily" part)

Each rule is enforceable in pytest (a **portability gate** alongside the
offline gates), so drift fails CI instead of surfacing during the port.

1. **Lifecycle:** build on `Gtk.Application` + `ApplicationWindow` today
   (fully supported in GTK3). The only lifecycle delta left at port time
   is deleting `show_all` and calling `present()`.
2. **Menus:** every menu — logs context menu, signal picker, column
   choosers, overflow menus — is a `PopoverMenu` fed by `Gio.Menu`
   models. `Gtk.Menu`/`MenuItem` are forbidden by gate. Zero-cost now,
   zero-work at port.
3. **Events & accelerators:** keyboard/motion via `EventControllerKey` /
   `EventControllerMotion` (both toolkits). Click gestures go through a
   version-switched adapter (`GestureMultiPress` ↔ `GestureClick` — a
   rename, not a shared name). Accelerators are `Gio.SimpleAction` +
   `app.set_accels_for_action()` — never `ShortcutController` (GTK4-only)
   and no new `*-event` connections. (The one existing
   `button-press-event` site converts in Phase 2 when real interactions
   begin.)
4. **Layout & child-add:** one `src/ui/layout.py` helper owning BOTH
   `box_add(box, child, expand, fill, padding)` (pack_start ↔ append+props)
   and `set_child(container, child)` (add/remove ↔ set_child). All pack and
   add sites migrate to the helper once; helpers flip at port. `destroy()`
   is banned — windows `close()`, the dialog adapter owns that path.
5. **Charts:** one `ChartArea(DrawingArea)` adapter owning the draw hookup
   (`connect("draw")` on GTK3, `set_draw_func` on GTK4). Chart code talks
   only to the adapter + a cairo context.
6. **Dialogs:** kill/renice/confirm dialogs as plain `Gtk.Window` with
   headerbar + action row (works identically in both toolkits);
   `AlertDialog` only behind a version check if used at all.
7. **Icons:** keep the Pillow→Pixbuf tint pipeline; one
   `image_from_pixbuf()` helper hides the Texture/Pixbuf difference.
8. **CSS:** classes and state selectors only (the r034 linfilesearch
   lesson already forces view-node targeting, which GTK4 also wants); no
   layout through CSS; provider registration and class-adding go through
   the theme-manager helper (`add_css_class` spelling).
9. **Gate:** `tests/test_gates.py` grows a banned-API sweep — scoped, not
   naive greps: `Gtk.Box`-only `pack_start|pack_end` outside layout.py
   (HeaderBar/ActionBar pack survives GTK4); `container.add(`/`set_border_width`/
   `.destroy()` outside adapters; `show_all` outside one launcher;
   `RadioButton`; new `button-press-event|key-press-event|draw` connects
   outside adapters; `Gtk.Dialog|MessageDialog`; `ShortcutController`.

## 5. Migration plan (when triggered)

Trigger: operator decision, or a GTK3 EOL signal. Not before v1 tag.

- **Stage 0 — seams green:** all §4 rules enforced by the gate, both
  toolkits' code paths unit-tested where dual (layout, ChartArea, icons).
- **Stage 1 — branch `gtk4-port`:** flip `gi.require_version("Gtk",
  "4.0")` + the adapter version switches. Expect: window sizing quirks,
  focus/selection visual differences, CSS node deltas.
- **Stage 2 — parity pass:** run the full pytest suite (core tests are
  toolkit-blind by design); fix shell/pages until the X11 smoke-launch
  and pixel rig match GTK3 screenshots within tolerance.
- **Stage 3 — soak side-by-side:** keep GTK3 main until the operator has
  used the GTK4 build for real sessions; then main switches, GTK3 branch
  archives.

Estimated effort **with seams enforced: 2–4 working sessions**, dominated
by Stage 2 visual parity — the seam census (§1) tells us where the surface
is, and the un-grepped remainder (add/destroy/CSS registration) rides the
same adapters, so the estimate is grounded in seams identified, not a
counted surface. Without them: a multi-week rewrite touching every file.

## 6. Deliberately NOT in the port

- **No libadwaita** — adds a dependency and GNOME-centric styling for a
  Mint/Cinnamon-first app; plain GTK4 keeps universality and the
  7-theme system intact. (It remains an operator opt-in later; offline
  mandate unaffected either way.)
- **No TreeView→ColumnView rewrite in the port** — TreeView works on
  GTK 4.14 but is **deprecated since 4.10**; it is the one subsystem on a
  GTK5 removal track, so the ColumnView migration is a standing post-port
  item that may be pulled earlier if deprecation warnings bother us.
- **No GTK5 speculation.**

## 7. Risks

| Risk | Mitigation |
|---|---|
| TreeView family deprecated since 4.10 (GTK5 removal track) | works on 4.14; ColumnView migration scheduled post-port, may pull earlier |
| Hidden TreeView behavioral deltas in GTK4 (selection/focus semantics) | Stage 2 pixel parity + selection-restore tests already in the suite |
| CSS node-tree differences change row styling | class-based CSS only; pixel rig catches drift (r034 lesson) |
| Event-controller rewrite feels alien mid-feature | seams adopted now; GTK3 already supports controllers |
| GTK4 minor-version drift (4.14 today) | pin nothing; test on the installed version only |
| Port attempted before v1 | blocked: trigger requires operator decision |

## 8. Not verified

- Exact GTK4 pixel/CSS parity behavior of our specific widgets (no GTK4
  build exists yet — Stage 2 is where that truth surfaces).
- `Gtk.AlertDialog` ergonomics (doc-reference only).
- Whether TreeView performance in GTK4 matches GTK3 at our row budget —
  measured at Stage 2; ColumnView is the fallback.
