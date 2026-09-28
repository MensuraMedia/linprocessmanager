"""r111 regression pin: the Basics cards must REGISTER their widget refs
(_gauges/_state) at construction AND receive live snapshot updates.

The r111 rebuild left the ref assignments after ``return card`` (dead code):
cards rendered as empty frames, every snapshot tick raised KeyError inside
the drain observer, and the single-drain law died with it. Caught by the
r096-audit follow-through test pattern; needs a display.
"""

import os
import time

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get('DISPLAY'), reason='needs an X display')

gi = pytest.importorskip('gi')
gi.require_version('Gtk', '3.0')


def test_basics_cards_register_refs_and_receive_snapshots():
    from ui.compat import Gtk  # noqa: F401  (ui-side import first)
    from modules.manager_navigation import NavigationManager
    from modules.manager_sampler import Sampler
    from ui.dashboard_window import DashboardWindow

    # a real, STARTED sampler — the r073 gate keeps sampler.start() out of
    # the window, so a direct-built window must start it itself (exactly
    # like _do_activate does) or no snapshot ever reaches the page.
    sampler = Sampler()
    win = DashboardWindow(NavigationManager(), sampler=sampler,
                          application=None)
    win.set_default_size(1200, 800)
    win.show_all()
    sampler.start()

    basics = win.nav_manager.get_page_widget('graphs')._basics_section \
        if hasattr(win.nav_manager.get_page_widget('graphs'),
                   '_basics_section') else None
    if basics is None:
        found = []

        def find(w):
            if type(w).__name__ == 'BasicsPage':
                found.append(w)
            if hasattr(w, 'forall'):
                w.forall(find)
        win.forall(find)
        basics = found[0]
    assert basics is not None

    assert set(basics._gauges.keys()) == {
        'cpu', 'memory', 'swap', 'disk', 'network', 'load'}, (
        'every metric must register its widget refs')
    assert set(basics._state.keys()) == set(basics._gauges.keys())

    end = time.time() + 6
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)

    caption = basics._gauges['cpu']['caption'].get_text()
    assert caption, 'cpu caption must be populated by a live snapshot'
    assert basics._gauges['cpu']['contrib'].get_children(), \
        'contributor rows must build from the live snapshot'
    sampler.stop()
    win.destroy()
