"""Disks page UI tier (task 011): the sidebar entry builds, a background scan
of the real machine's mounts populates the summary band + spreadsheet, the
usage-bar draw callbacks have the ChartArea arity, and a rebuild replaces
(never accumulates) the tracked results. Needs a display like the other UI
tiers."""

import os
import time

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get('DISPLAY'), reason='needs an X display')

gi = pytest.importorskip('gi')
gi.require_version('Gtk', '3.0')


def _build_window():
    from ui.compat import Gtk  # noqa: F401
    from modules.manager_navigation import NavigationManager
    from modules.manager_sampler import Sampler
    from ui.dashboard_window import DashboardWindow
    win = DashboardWindow(NavigationManager(), sampler=Sampler(),
                          application=None)
    win.set_default_size(1200, 800)
    win.show_all()
    return win


def _pump(t=1.2):
    from ui.compat import Gtk
    end = time.time() + t
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)


def test_disks_page_builds_band_and_table():
    win = _build_window()
    page = win.nav_manager.get_page_widget('disks')
    assert page is not None, 'disks must be a registered sidebar page'
    assert win.nav_manager.navigate_to('disks')
    _pump()   # let the background scan land + idle_add rebuild
    # Band + spreadsheet always build (band shows "—" even with no data).
    assert len(page._results_children) >= 2
    # This box always has at least one real mounted filesystem (/).
    assert page._summary['mounted'] >= 1
    win.destroy()


def test_disks_usage_bar_draw_callback_arity():
    import cairo
    win = _build_window()
    page = win.nav_manager.get_page_widget('disks')
    win.nav_manager.navigate_to('disks')
    _pump()

    areas = []

    def walk(w):
        if type(w).__name__ == 'ChartArea':
            areas.append(w)
        if hasattr(w, 'forall'):
            w.forall(walk)
    walk(page)
    assert areas, 'the spreadsheet must contain usage-bar ChartAreas'

    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 160, 8)
    cr = cairo.Context(surf)
    for area in areas:
        cb = (area.get_draw_callback() if hasattr(area, 'get_draw_callback')
              else area._draw_func)
        assert cb is not None
        cb(area, cr, 160, 8)   # wrong arity raises TypeError here
    win.destroy()


def test_disks_rebuild_replaces_not_accumulates():
    win = _build_window()
    page = win.nav_manager.get_page_widget('disks')
    win.nav_manager.navigate_to('disks')
    _pump()
    before = len(page._results_children)
    page._rebuild_results()
    _pump(0.3)
    assert len(page._results_children) == before, \
        'rebuild must replace the tracked results, not stack them'
    win.destroy()
