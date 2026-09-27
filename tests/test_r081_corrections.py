"""r081 operator corrections, pinned by tests:

1. Right-click on the column-header band opens the COLUMN CHOOSER, not the
   process context menu (r075 regression: widget-vs-bin-window coords slid
   header clicks into the first data row).
2. The Graphs caret toggles the Basics submenu downward/upward WITHOUT
   navigating (r075 left no collapse path at all).
3. A Processes band-chart click lands on Basics and auto-expands the
   Graphs group in the sidebar (dashboard on_page_changed hook).

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


def _graphs_box(sidebar):
    return sidebar.submenu_boxes['graphs']


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


def test_caret_toggles_basics_submenu_without_navigating():
    win = _build_window()
    sidebar = win.sidebar
    nav = win.nav_manager
    assert not _graphs_box(sidebar).get_visible(), 'starts collapsed'
    caret_changed = []
    before = nav.get_current_page()
    sidebar._on_caret_toggle('graphs')
    assert _graphs_box(sidebar).get_visible(), 'caret expands downward'
    sidebar._on_caret_toggle('graphs')
    assert not _graphs_box(sidebar).get_visible(), 'caret contracts upward'
    assert nav.get_current_page() == before, 'caret toggle must not navigate'
    assert caret_changed == []
    win.destroy()


def test_band_chart_click_lands_on_basics_and_expands_group():
    win = _build_window()
    nav = win.nav_manager
    page = nav.get_page_widget('processes')

    class _App:                       # the page only needs navigation_manager
        navigation_manager = nav
    page._app = _App()

    assert not _graphs_box(win.sidebar).get_visible()
    page._on_gauge_pressed('cpu')
    _pump(0.3)
    assert nav.get_current_page() == 'basics', \
        'band-chart click must open the Basics page'
    assert _graphs_box(win.sidebar).get_visible(), \
        'Basics destination must arrive with the Graphs group expanded'
    win.destroy()


def test_caret_click_delivered_as_real_event_does_not_navigate():
    """CROSS-REVIEW P2-1 (Claude, r081): the direct-call test cannot prove
    that a REAL pointer press on the caret EventBox is swallowed — if the
    group button also saw it, the caret would toggle AND navigate. This
    drives a genuine button-press/release pair through the event pipeline
    at the caret's on-screen position (r034 synthesized-event pattern)."""
    win = _build_window()
    sidebar = win.sidebar
    nav = win.nav_manager
    from ui.compat import Gdk, Gtk

    toggle_box = None
    for page_id, info in sidebar.submenus.items():
        if page_id == 'graphs':
            caret = info['caret']
            toggle_box = caret.get_parent()      # the EventBox
    assert toggle_box is not None

    _pump(0.3)
    assert not sidebar.submenu_boxes['graphs'].get_visible()
    page_before = nav.get_current_page()

    wx = toggle_box.get_allocation()
    ex, ey = wx.x + wx.width // 2, wx.y + wx.height // 2
    win_win = toggle_box.get_window()
    assert win_win is not None, 'caret EventBox must be mapped'
    for etype in (Gdk.EventType.BUTTON_PRESS, Gdk.EventType.BUTTON_RELEASE):
        ev = Gdk.Event.new(etype)
        ev.button.window = win_win
        ev.button.button = 1
        ev.button.x, ev.button.y = float(ex), float(ey)
        ev.button.time = Gtk.get_current_event_time()
        seat = Gdk.Display.get_default().get_default_seat()
        ev.button.device = seat.get_pointer()
        Gtk.main_do_event(ev)
    _pump(0.5)

    assert sidebar.submenu_boxes['graphs'].get_visible(), \
        'the real press must toggle the submenu open'
    assert nav.get_current_page() == page_before, \
        'the group button must NOT receive the caret click (no navigation)'
    win.destroy()
