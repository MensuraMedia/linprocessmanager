"""r080 layout regression: the sidebar must sit flush at the window's left
edge. r075's group-button label carried set_hexpand(True); GTK3 propagates
hexpand up the ancestor chain, so the Sidebar itself became expansion-hungry
— the window's spare width was handed to the 171px sidebar, which floated
centered with dead strips on both flanks while the table squeezed to ~537px
(the operator's 15:52 screenshot). Building the real window needs a display.
"""

import os
import time

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get('DISPLAY'), reason='needs an X display')

gi = pytest.importorskip('gi')
gi.require_version('Gtk', '3.0')


def _build_window():
    # import ui FIRST: the pages⇄ui import chain is order-sensitive and only
    # resolves when entered from the ui side
    from ui.compat import Gtk  # noqa: F401  (loads the ui package first)
    from modules.manager_navigation import NavigationManager
    from ui.dashboard_window import DashboardWindow
    win = DashboardWindow(NavigationManager(), sampler=None, application=None)
    win.set_default_size(1200, 800)
    win.show_all()
    return win


def _pump(t=0.8):
    from ui.compat import Gtk
    end = time.time() + t
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)


def test_sidebar_flush_left_no_flanks():
    win = _build_window()
    _pump()
    sidebar = win.sidebar.get_allocation()
    content = win.content_area.get_allocation()
    assert sidebar.x == 0, (
        f'sidebar must sit flush left, got x={sidebar.x} — a child set '
        'hexpand again and GTK3 propagated it up to the Sidebar')
    assert content.x == sidebar.width, (
        f'content must start immediately after the sidebar, '
        f'got x={content.x} vs sidebar width {sidebar.width}')
    assert content.x + content.width == 1200, (
        'content must reach the right window edge')
    win.destroy()
