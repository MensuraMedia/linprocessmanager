# Task 002 — Phase 2a: compat module, gate tiers, Application lifecycle, riders

Phase: 2a (concept §9 + upgrade-architecture.md)   Branch: task/002-compat-gates (checked out)
Dispatcher: ZCode (r046)  Executor: Claude Code, headless, acceptEdits

## Goal

Stand up the upgrade structure BEFORE the UI-heavy tasks: the
src/ui/compat/ module (one file per seam), the gate tiers that police it,
Gtk.Application lifecycle, and two cosmetic riders. After this task the
codebase is structurally GTK4-safe and every later task is born inside the
structure.

## Read first (binding)

- docs/upgrade-architecture.md — §2 import law, §3 compat spec, §4 tiers. THE SPEC.
- docs/gtk4-port.md — §3 API delta table, §4 seams. Context for each adapter.
- docs/debian-compatibility.md — §2 feature-probe pattern (HAS_* flags).
- AGENTS.md (loads automatically).

## Scope (touch nothing else)

- NEW  src/ui/compat/{__init__,gtk_env,layout,menu,events,dialogs,charts,icons,css}.py
- EDIT src/ui/{sidebar,content_area,dashboard_window}.py,
       src/ui/components/component_theme_selector.py,
       src/pages/*.py — migrate imports to compat (see rules)
- EDIT src/main.py — Gtk.Application + ApplicationWindow lifecycle
- EDIT tests/test_gates.py — add the new tiers
- EDIT src/pages/page_settings.py — rider: stale strings
- EDIT src/ui/dashboard_window.py — rider: title 'linprocman'

## Rules (verbatim)

1. compat/gtk_env.py is the ONLY file calling gi.require_version and the
   ONLY file issuing `from gi.repository import ...`. It requires BOTH
   Gtk and Gdk at "3.0", GdkPixbuf at "2.0" (GLib/Gio/GObject versionless),
   exports GTK_MAJOR and HAS_* flags (e.g. HAS_ALERT_DIALOG = minor >= 10),
   and re-exports Gtk, Gdk, GLib, Gio, GObject, GdkPixbuf.
2. Every other file under src/ui/ and src/pages/ imports toolkit symbols
   ONLY from ..compat / .compat — never from gi.repository.
3. Adapters implement BOTH paths where applicable, selected by GTK_MAJOR:
   layout.box_add/set_child; menu.model_popover (bind_model ↔
   new_from_model); events.click_gesture (GestureMultiPress ↔ GestureClick),
   key_controller, motion_controller, accels via Gio.SimpleAction +
   set_accels_for_action; dialogs.confirm_window pattern + close-only;
   charts.ChartArea (connect('draw') ↔ set_draw_func); icons.image_from_pixbuf
   (plain ↔ Gdk.Texture wrap); css helpers (add_provider_for_screen ↔
   _for_display; add_css_class).
4. Adapters carry NO feature logic — only toolkit differences. A UI file
   importing GTK directly, or an adapter growing feature code, is a defect.
5. Application lifecycle: main.py uses Gtk.Application (application-id
   e.g. 'io.github.linprocman'), activate() builds the window;
   dashboard_window becomes Gtk.ApplicationWindow; show_all removed in
   favor of present(); window title 'linprocman'.
6. Gate tiers to add in test_gates.py:
   a. raw-import ban: `from gi.repository` appears ONLY in
      src/ui/compat/gtk_env.py (and tests may import gi for their own use).
   b. banned-API sweep, scoped: Box-only pack_start/pack_end outside
      compat/layout.py; `.add(`/`set_border_width` outside compat;
      `.destroy(` outside compat/dialogs.py; `show_all` outside src/main.py
      and compat; RadioButton; Gtk.Dialog|MessageDialog; ShortcutController;
      new `connect('button-press-event'|'key-press-event')` outside
      compat/events.py; `connect('draw')` outside compat/charts.py.
   c. PyGIDeprecationWarning-as-error tier: pytest filterwarnings in the
      gates test (or conftest) escalating gi.PyGIDeprecationWarning to
      error for code outside src/ui/compat/.
7. All existing mandates unchanged: offline app code, no subprocess in
   this task, no pip/venv, never create claude-named files/dirs.
8. You cannot run Bash — do not try. Write code + Report; ZCode runs
   tests and sends failures back on this session.

## Acceptance (ZCode verifies)

1. python3 -m pytest tests/ -q green, including the three new tiers.
2. Gates prove: zero gi.repository imports outside gtk_env.py; zero
   banned-API hits; existing 49 tests still pass.
3. App launches on X11 :0 (ZCode smoke + screenshot): window titled
   'linprocman', nav shell unchanged, Processes active.
4. git diff vs staging/branch base touches only Scope.
5. Dual-path adapter branches exist for both GTK3/GTK4 selections
   (unit-test the selection logic where GTK objects aren't required).

## Report

Markdown: file map; adapter-by-adapter note on dual paths; deviations
(none expected); open questions; anything needing Bash.

## Out of scope

Sampler, table UI, pages' content, settings persistence, charts
implementation (ChartArea is the adapter only), menu contents.
