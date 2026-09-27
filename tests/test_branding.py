"""Branding (r082): one mark, every placement.

- the checked-in raster set is complete and carries the brand treatment
  (blue tile + white glyph; accent sidebar logo)
- branding.pixbuf_for / logo_pixbuf / set_window_icon work
- ROUTING GATE: sidebar / main / tray must consume ui.branding — a new
  placement may not hardcode resource paths again.
"""

import ast
import os

import pytest

gi = pytest.importorskip('gi')
gi.require_version('GdkPixbuf', '2.0')

REPO = os.path.join(os.path.dirname(__file__), '..')


def _img(name):
    from PIL import Image
    return Image.open(os.path.join(
        REPO, 'resources', 'images', name)).convert('RGBA')


def test_icon_set_complete_and_on_brand():
    from ui.branding import ICON_SIZES
    for size in ICON_SIZES:
        path = os.path.join(REPO, 'resources', 'images',
                            'icon-%d.png' % size)
        assert os.path.exists(path), 'missing brand raster %s' % path
        im = _img('icon-%d.png' % size)
        assert im.size == (size, size)
    master = _img('icon-512.png')
    assert master.getpixel((4, 4))[3] == 0, 'tile corner must be transparent'
    assert master.getpixel((256, 82))[:3] == (0, 120, 215), 'tile must be accent'
    big = _img('icon-128.png')
    inks = [big.getpixel((x, y)) for x in range(40, 90) for y in range(40, 90)]
    assert any(p[:3] == (255, 255, 255) and p[3] == 255 for p in inks), \
        'white glyph ink missing'


def test_sidebar_logo_assets_on_brand():
    logo = _img('logo.png')
    assert logo.size == (150, 150)
    assert any(p[3] > 0 and p[:3] == (0, 120, 215) for p in logo.getdata()), \
        'accent ink missing'
    svg = open(os.path.join(REPO, 'resources', 'images', 'logo.svg')).read()
    assert '#0078D7' in svg, 'logo.svg must carry the accent fill'


def test_pixbuf_helpers():
    from ui import branding
    pb = branding.logo_pixbuf(64)
    assert pb is not None and pb.get_width() == 64 and pb.get_height() == 64
    assert branding.tray_icon_path().endswith('icon-128.png')
    assert branding.pixbuf_for('/nonexistent/x.png', 32) is None


def test_routing_gate_all_placements_use_branding():
    """Every runtime placement must consume ui.branding (r082 contract)."""
    main_src = open(os.path.join(REPO, 'src', 'main.py')).read()
    sidebar_src = open(os.path.join(REPO, 'src', 'ui', 'sidebar.py')).read()
    tray_src = open(os.path.join(REPO, 'src', 'ui', 'compat', 'tray.py')).read()
    assert 'branding.set_window_icon' in main_src
    assert 'branding.tray_icon_path()' in main_src
    assert 'branding.logo_pixbuf' in sidebar_src
    assert 'icon_path' in tray_src
    for name, src in (('main.py', main_src), ('tray.py', tray_src),
                      ('sidebar.py', sidebar_src)):
        assert 'icon-128.png' not in src, \
            f'{name} hardcodes a brand raster — route through ui.branding'


def test_set_window_icon_smoke():
    pytestmark_check = os.environ.get('DISPLAY')
    if not pytestmark_check:
        pytest.skip('needs an X display')
    gi.require_version('Gtk', '3.0')
    from ui.compat import Gtk
    from ui import branding
    win = Gtk.OffscreenWindow()
    assert branding.set_window_icon(win) is True
    assert win.get_icon() is not None
