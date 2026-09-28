"""Logs page smoke (UI tier) — build + preset/argv wiring + populate.

Instantiating a page needs a display, so this module skips without ``DISPLAY``
(suite convention, cf. test_layout_regression). The pure engine is covered by
test_logs_engine.py; here we prove the page builds, reflects its controls into
the engine argv, and renders engine entries into its store without touching a
live journal.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY"), reason="needs an X display")

pytest.importorskip("gi")

try:
    from ui.compat import Gtk  # noqa: F401  (loads the ui package first)
    from pages.page_logs import LogsPage
except (ImportError, ValueError) as exc:  # missing typelib etc.
    pytest.skip("GTK bindings unavailable: %s" % exc, allow_module_level=True)

from modules import manager_logs   # SAME module object the page uses


def _entry(ts="12:00:00", prio=6, unit="systemd", msg="hello"):
    return {"timestamp": ts, "priority": prio, "unit": unit, "message": msg}


def test_page_builds_with_empty_store():
    page = LogsPage()
    assert len(page.store) == 0
    assert page.treeview.get_model() is page.store
    assert page.treeview.get_n_columns() == 4


def test_controls_reflect_into_engine_argv():
    page = LogsPage()
    page.preset_combo.set_active(1)     # Kernel
    page.priority_combo.set_active(1)   # Error -> err
    page.lines_combo.set_active(1)      # 500
    page.unit_entry.set_text("sshd.service")
    assert page._collect_argv() == manager_logs.build_argv(
        "kernel", unit="sshd.service", priority="err", lines=500)


def test_empty_unit_is_omitted_from_argv():
    page = LogsPage()
    page.unit_entry.set_text("   ")
    assert page._collect_argv() == manager_logs.build_argv("journal", lines=500)


def test_populate_fills_store_and_status():
    page = LogsPage()
    page._populate([_entry(msg="a"), _entry(prio=3, msg="b")])
    assert len(page.store) == 2
    assert page.store[0][page.COL_MSG] == "a"
    assert page.store[1][page.COL_PRIO] == 3
    assert "2 entries" in page.status_label.get_text()


def test_populate_empty_shows_empty_state_not_error():
    page = LogsPage()
    page._populate([])
    assert len(page.store) == 0
    assert "No entries" in page.status_label.get_text()


def test_populate_error_entry_shows_error_text_no_rows():
    page = LogsPage()
    page._populate([{"error": "journalctl not found"}])
    assert len(page.store) == 0
    assert "not found" in page.status_label.get_text()


def test_load_button_smoke_populates(monkeypatch):
    # patch BEFORE construction: the page auto-loads on build, and an
    # unpatched first load spawns the real journalctl (500 live rows)
    monkeypatch.setattr(
        manager_logs, "read_journal",
        lambda argv, **kw: [_entry(msg="live"), _entry(msg="row")])
    page = LogsPage()
    page._on_load(page.load_button)
    # The read runs on a worker thread and posts back via GLib.idle_add; pump
    # the loop until the idle callback lands.
    from ui.compat import GLib  # noqa: F401
    import time
    deadline = time.time() + 2.0
    while time.time() < deadline and len(page.store) == 0:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.01)
    assert len(page.store) == 2
