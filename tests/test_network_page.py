"""Network page (r113): per-process live traffic table.

Covers: active-only row filtering, in-place keyed updates, sortable columns
(unknowns-last), and the summary band. Needs a display (UI tier).
"""

import os
import time
import types

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get('DISPLAY'), reason='needs an X display')

gi = pytest.importorskip('gi')
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk                                        # noqa: E402


def _snap(procs):
    return types.SimpleNamespace(procs=procs, system={})


def _rec(name, user, rx, tx, unit=None):
    return {
        "pid": 1, "starttime": 1, "name": name, "user": user,
        "state": "S", "ppid": 1, "unit": unit, "cpu_pct": 0.0,
        "mem_rss": 0, "mem_vsize": 0, "mem_shared": 0, "mem_swap": 0,
        "io_read_rate": 0.0, "io_write_rate": 0.0,
        "net_rx_rate": rx, "net_tx_rate": tx,
        "nice": 0, "threads": 1, "is_kthread": False,
        "is_defunct": False, "from_backoff": False, "rollup": None,
    }


def _names(model):
    return [model.get_value(model.get_iter_from_string(str(i)), 0)
            for i in range(len(model))]


def _col(model, col):
    return [model.get_value(model.get_iter_from_string(str(i)), col)
            for i in range(len(model))]


def _build_page():
    from ui.compat import Gtk  # noqa: F401  (ui-side import first)
    from pages.page_network import NetworkPage
    page = NetworkPage()
    box = Gtk.OffscreenWindow()
    layout_box = Gtk.Box()
    layout_box.add(page)
    box.add(layout_box)
    box.set_default_size(1200, 800)
    box.show_all()
    end = time.time() + 0.4
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
    return page, box


def test_active_rows_only_and_band():
    page, _box = _build_page()
    page.on_snapshot(_snap({
        (10, 1): _rec("downloader", "user", 50000.0, 1000.0),
        (11, 1): _rec("idle-app", "user", None, None),     # no attribution
        (12, 1): _rec("zero-traffic", "user", 0.0, 0.0),   # attributed, idle
    }))
    assert _names(page.store) == ["downloader"], (
        'only attributed, nonzero-traffic processes are listed')
    assert page._band["apps"].get_text() == "1"
    assert page._band["busiest"].get_text() == "downloader"
    assert page._band["rx"].get_text() == "48.8 KB/s"


def test_rows_update_in_place_and_gone_apps_leave():
    page, _box = _build_page()
    page.on_snapshot(_snap({
        (20, 1): _rec("app-a", "user", 100.0, 50.0),
    }))
    page.on_snapshot(_snap({
        (20, 1): _rec("app-a", "user", 300.0, 20.0),
        (21, 1): _rec("app-b", "user", 5.0, 5.0),
    }))
    assert _names(page.store) == ["app-a", "app-b"], 'new app appended'
    page.on_snapshot(_snap({
        (21, 1): _rec("app-b", "user", 5.0, 5.0),
    }))
    assert _names(page.store) == ["app-b"], 'departed app removed in place'


def test_columns_sortable_unknowns_last():
    page, _box = _build_page()
    page.sampler = types.SimpleNamespace(open_sockets=lambda: {30: 2})
    page.on_snapshot(_snap({
        (30, 1): _rec("restricted", "user", None, None),   # Yama + sockets
        (31, 1): _rec("small", "user", 10.0, 0.0),
        (32, 1): _rec("big", "user", 900.0, 0.0),
    }))
    assert len(page.store) == 3, 'socket-holder with no rates is listed'

    page._on_header_clicked(None, 3)     # first click on Rx: descending
    assert page._sort_state == {"col": 3, "desc": True}
    assert _col(page.store, 3)[0] == 900.0, 'busiest first'
    assert _col(page.store, 3)[-1] == -1, 'unknowns last (desc)'

    page._on_header_clicked(None, 3)     # same column: flips to ascending
    assert page._sort_state == {"col": 3, "desc": False}
    assert _col(page.store, 3) == [10.0, 900.0, -1.0], (
        'ascending: smallest first, unknown LAST in both directions')


def test_idle_socket_holder_listed_via_connections():
    page, _box = _build_page()
    page.sampler = types.SimpleNamespace(open_sockets=lambda: {40: 1})
    page.on_snapshot(_snap({
        (40, 1): _rec("long-lived-listener", "user", 0.0, 0.0),
    }))
    assert _names(page.store) == ["long-lived-listener"], (
        'a process holding sockets is listed even at zero traffic')
