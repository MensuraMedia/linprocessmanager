"""Peripherals page UI tier (r092): the sidebar entry builds and lists the
real machine's USB devices (this box always has host controllers), sensor
chips render, and Refresh rebuilds the tracked sections idempotently.
Needs a display like the other UI tiers."""

import os
import time

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get('DISPLAY'), reason='needs an X display')

gi = pytest.importorskip('gi')
gi.require_version('Gtk', '3.0')


def _build_window():
    # ui package first — the pages⇄ui import chain only resolves from that
    # side
    from ui.compat import Gtk  # noqa: F401
    from modules.manager_navigation import NavigationManager
    from modules.manager_sampler import Sampler
    from ui.dashboard_window import DashboardWindow
    win = DashboardWindow(NavigationManager(), sampler=Sampler(),
                          application=None)
    win.set_default_size(1200, 800)
    win.show_all()
    return win


def _pump(t=0.6):
    from ui.compat import Gtk
    end = time.time() + t
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)


def test_peripherals_page_lists_devices_and_refresh_rebuilds():
    win = _build_window()
    page = win.nav_manager.get_page_widget('peripherals')
    assert page is not None, 'peripherals must be a registered sidebar page'
    assert win.nav_manager.navigate_to('peripherals')
    _pump()
    assert len(page._devices_children) >= 1, \
        'this machine always has USB host controllers to list'
    assert len(page._sensors_children) >= 1, \
        'sensor chips section must build (temps exist here)'
    before_dev = len(page._devices_children)
    page.refresh()
    _pump()
    assert len(page._devices_children) == before_dev, \
        'refresh must rebuild, not accumulate, the tracked sections'
    win.destroy()
