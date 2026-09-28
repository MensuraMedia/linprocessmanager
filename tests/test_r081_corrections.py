"""r081 operator corrections, pinned by tests:

1. Right-click on the column-header band opens the COLUMN CHOOSER, not the
   process context menu (r075 regression: widget-vs-bin-window coords slid
   header clicks into the first data row).
2. (r092) The Processes band double-click lands on the Graphs hub — the
   Basics cards live at its top; the standalone Basics page and the sidebar
   submenu are retired (superseded the r081 caret tests).

Builds the real window; needs a display like the other UI tiers.
"""

import os
import time

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get('DISPLAY'), reason='needs an X display')

gi = pytest.importorskip('gi')
gi.require_version('Gtk', '3.0')


def _pump(t=0.8):
    from ui.compat import Gtk
    end = time.time() + t
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)


def _build_window():
    # ui package first — the pages⇄ui import chain only resolves from that
    # side (same order-sensitivity every UI test here works around)
    from ui.compat import Gtk  # noqa: F401
    from modules.manager_navigation import NavigationManager
    from ui.dashboard_window import DashboardWindow
    win = DashboardWindow(NavigationManager(), sampler=None, application=None)
    win.set_default_size(1200, 800)
    win.show_all()
    _pump()
    return win


def test_header_right_click_opens_column_chooser_not_process_menu():
    win = _build_window()
    page = win.nav_manager.get_page_widget('processes')
    opened = []
    popped = []
    page._open_column_chooser = lambda x, y: opened.append((x, y))
    page._popup_menu = lambda x, y: popped.append((x, y))
    page._on_row_menu(None, None, 300, 8)      # header band (widget coords)
    assert opened and not popped, \
        'right-click on the header must open the column chooser'
    page._on_row_menu(None, None, 300, 5)      # further left = same band
    assert len(opened) == 2 and not popped
    # a data-row right-click still opens the process menu (path monkeypatched
    # because the headless table has no rows)
    from ui.compat import Gtk
    page._path_at = lambda x, y: Gtk.TreePath.new_first()
    page._on_row_menu(None, None, 300, 120)
    assert popped and len(opened) == 2, \
        'right-click on a data row must keep the process menu'
    win.destroy()


def test_band_chart_double_click_lands_on_graphs_hub():
    """r092: the Basics cards live at the TOP of the Graphs hub, so the
    band double-click lands on 'graphs' (the standalone Basics page and
    the sidebar submenu are retired)."""
    win = _build_window()
    nav = win.nav_manager
    page = nav.get_page_widget('processes')

    class _App:                       # the page only needs navigation_manager
        navigation_manager = nav
    page._app = _App()

    page._on_gauge_pressed('cpu')
    assert nav.get_current_page() == 'graphs', \
        'band double-click must open the Graphs hub (Basics at its top)'
    assert nav.get_page_widget('basics') is None, \
        'the standalone Basics page must be unregistered'
    win.destroy()
