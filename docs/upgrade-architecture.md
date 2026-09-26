# linprocman — upgrade architecture (structured for easy upgrades)

Status: planning document (r044, 2026-09-26). Companion to
[gtk4-port.md](gtk4-port.md) — that document covers the 3→4 port; this one
defines the standing structure that makes EVERY upgrade class cheap:
toolkit minor releases, the major port, a future GTK5, Python bumps, and
starter-template refreshes. Collaborator-reviewed before commit.

## 1. The principle

Upgrades are expensive exactly where version-sensitive knowledge is
smeared across the codebase. The fix is structural: every toolkit
difference, every version-sensitive choice, lives in ONE small module
with dual-version code paths and its own tests. Everything else is
version-blind. Then an upgrade is: flip or extend one module, run the
gates, fix what they catch.

## 2. Layering (import direction is law)

```
kernel readers   procfs.py, sysfs.py            (pure stdlib — no GTK ever)
logic            sampler, actions, frequency,   (pure stdlib + GLib only)
                 history, config
compat           src/ui/compat/*               (ALL GTK version knowledge)
UI               src/ui/*, src/pages/*         (imports GTK only via compat)
app              src/main.py                   (Application lifecycle)
```

Rules, gate-enforced:
- Imports flow downward only. A UI file importing `procfs` directly (not
  via snapshots/logic) is a defect; a logic file importing GTK is a
  defect. Phase 1's core-import allowlist already tests the bottom half;
  the upper half joins the gate with the compat module.
- UI code never calls `gi.require_version` **and never issues
  `from gi.repository import Gtk`** — the gate bans the raw import
  statement outside `gtk_env.py`, because a bare import silently loads a
  default version and defeats the flip point. (The starter's vendored UI
  files currently import directly — all of them move to compat imports in
  task 002, on-touch.)

## 3. The compat module spec (`src/ui/compat/`)

One file per seam, each owning exactly one toolkit difference. Testing
scope is honest (collaborator correction, r044): a Python process holds
exactly one Gtk version, so "dual-path tests" means branch-selection and
non-GTK logic of both paths unit-tested in every run, while GTK-calling
lines of the non-active path are exercised only when that toolkit runs
the suite (port Stage 2; a later CI matrix):

| File | Owns | GTK3 path → GTK4 path |
|---|---|---|
| `gtk_env.py` | the ONLY `gi.require_version` calls; exports `GTK_MAJOR` and re-exports Gtk/GLib/Gdk/GdkPixbuf/Gio | **flips both `Gtk` AND `Gdk`** ("3.0"↔"4.0" — they are coupled; `GdkPixbuf` stays "2.0"; `GLib`/`Gio`/`GObject` take no version) — the single flip point of the port |
| `layout.py` | box pack semantics + child-add | `pack_start`/`add` ↔ `append`+props/`set_child` |
| `menu.py` | model-driven menus | `Popover.bind_model` ↔ `PopoverMenu.new_from_model` |
| `events.py` | click/key/motion controllers, accels | `GestureMultiPress` ↔ `GestureClick`; `SimpleAction` + `set_accels_for_action` (same both) |
| `dialogs.py` | confirm/entry windows, close semantics | plain-window pattern; `destroy()` banned — `close()` only |
| `charts.py` | `ChartArea` draw hookup | `connect("draw")` ↔ `set_draw_func` |
| `icons.py` | tinted pixbuf → widget image | pixbuf ↔ `Gdk.Texture` wrap |
| `css.py` | provider registration + class add | `add_provider_for_screen` ↔ `add_provider_for_display`; `add_css_class` spelling |

Everything in gtk4-port.md §4 (the nine seams) lands here verbatim — this
module IS that seam list, promoted from convention to structure.

## 4. Deprecation hygiene — upgrades arrive as pull-request-sized diffs

The gate suite (tests/test_gates.py) grows a warnings tier — with honest
scope for what each mechanism can see (r044 collaborator correction):

1. **Banned-API sweep** (existing, §3 of the port doc) — removed APIs
   never enter the tree. This, plus a release-notes scan on minor bumps,
   is the primary GTK-deprecation catcher.
2. **PyGObject-level deprecations as errors:** pytest `filterwarnings`
   escalates `gi.PyGIDeprecationWarning` to errors outside
   `src/ui/compat/`. Scope note: GTK's own C-level deprecations (the
   TreeView family on GTK4) do **not** emit Python warnings through
   PyGObject — this tier catches binding-level misuse only (deprecated
   constructor args, removed overrides), which is still worth failing.
3. **Diagnostic smoke, allowlisted:** the X11/Xvfb smoke launch runs with
   `G_ENABLE_DIAGNOSTIC=1` (works on GTK3 and GTK4, prints to stderr,
   covers deprecated *properties* best — not every deprecated call).
   Raw stderr from a diagnostics run also carries theme/CSS and
   GTK-internal noise we don't own, so the gate fails only on lines
   matching an allowlist pattern set (our widget/class names) — blanket
   stderr-failing would false-red.

Net: when Mint moves a GTK minor release, the app either passes clean or
fails with the exact call named by one of the three tiers.

## 5. Upgrade runbooks

| Upgrade | Runbook |
|---|---|
| GTK minor (4.14→4.16, or 3.24.x) | run gates + smoke; fix what the warnings tier names; nothing else |
| GTK major 3→4 | flip `gtk_env.py`, run [gtk4-port.md](gtk4-port.md) Stage 1–3 (parity, soak) — every other file is already version-blind |
| GTK5 (future) | the TreeView-family deprecation (since 4.10) is the known removal candidate; `compat/` isolates table API behind a thin `Table` wrapper so a ColumnView swap is one file + its tests |
| Python 3.12→3.14 | core is stdlib-only by mandate — run pytest; expected boring |
| Starter upstream refresh | vendored = ours. Upstream improvements are **cherry-picked by hand, docs-first**: a change enters the module docs (the contract), then the code, then the gates — never a merge |
| Icon library refresh | master library is local; re-run the copy, manifest is the contract, gates check manifest↔disk consistency |

## 6. Version policy (offline-compatible)

- Nothing is version-pinned from the network — ever (mandate). The app
  runs on whatever the distro ships; the compat layer + gates are the
  compatibility contract, not lockfiles.
- **PyGObject minimum:** GTK4 work requires pygobject ≥ 3.42 (noble ships
  3.48 — satisfied); noted so nobody discovers it mid-port.
- `config_themes.py` and starter visuals drift with upstream starter only
  via the docs-first runbook above.
- requirements.txt stays a comment (system packages): python3-gi,
  python3-cairo, python3-pil — no versions, no pip.

## 7. Roadmap integration

The compat module + upper-layer import gate + warnings tier ride the
Phase 2 contract (task 002) alongside the live-table work — new UI code
is then born inside the structure instead of retrofitted. Cost estimate:
one extra day inside Phase 2; saves the multi-week retrofit forever.

## 8. Risks

| Risk | Mitigation |
|---|---|
| compat module accquires logic (becomes a dumping ground) | one difference per file; UI code caught importing GTK directly fails the gate |
| non-active toolkit path drifts untested | branch/non-GTK logic tested every run; GTK-calling lines exercised at port Stage 2 and by a future CI matrix; smoke runs the active path |
| PyGObject-level warnings filter noise from vendored starter code | scope the filter to our src/ trees; starter code is vendored ours and gets cleaned on touch |
| diagnostics allowlist goes stale | patterns derive from our class/widget names, regenerated by a small gate helper |
| Table wrapper premature abstraction | wrapper stays thin (construct, columns, diff hooks); ColumnView swap deferred until GTK4 is real |

## 9. Not verified

- `filterwarnings` ergonomics for `gi.PyGIDeprecationWarning` (lands with
  task 002; expected minor tuning).
- `G_ENABLE_DIAGNOSTIC` output stability and our-allowlist filtering
  accuracy across GTK minor versions and themes.
- ColumnView API shape (no GTK4 build exists yet — gtk4-port.md §8 stands).
