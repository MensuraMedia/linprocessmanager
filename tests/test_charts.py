"""Render-helper units for the shared multi-series renderer (r068, mockup M).

Covers the pure geometry/palette helpers in :mod:`ui.compat.charts`
(:func:`series_palette`, :func:`segment_points`, :func:`nearest_value`, the zone
band fractions) plus a headless smoke of :func:`render_series` against an
offscreen cairo surface — no display required. Skips if the GTK bindings (needed
merely to import the compat seam) are unavailable.

Ring law (gap honesty): the line and its fill break at ``None`` and at time gaps
wider than ``gap_s`` — proven by :func:`segment_points` here so the drawing code
above it inherits it. r042: the per-series palette is generated from the accent,
never a hardcoded N-colour list.
"""

import pytest

pytest.importorskip("gi")

try:
    from ui.compat import charts
except (ImportError, ValueError) as exc:  # missing typelib etc.
    pytest.skip("GTK bindings unavailable: %s" % exc, allow_module_level=True)


def _luminance(rgb):
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


# --- series_palette (r042 shade-stepping) -----------------------------------

def test_series_palette_degenerate_counts():
    assert charts.series_palette(charts.ACCENT_RGB, 0) == []
    assert charts.series_palette((0.1, 0.2, 0.3), 1) == [(0.1, 0.2, 0.3)]


def test_series_palette_is_shade_stepped_and_in_range():
    palette = charts.series_palette(charts.ACCENT_RGB, 5)
    assert len(palette) == 5
    for rgb in palette:
        assert all(0.0 <= c <= 1.0 for c in rgb)
    # A shade walk: the darkest step is dimmer than the lightest.
    assert _luminance(palette[0]) < _luminance(palette[-1])
    # Distinct steps (no accidental duplicates -> a usable legend).
    assert len({tuple(round(c, 4) for c in rgb) for rgb in palette}) == 5


# --- segment_points (gap honesty) -------------------------------------------

def test_segment_points_breaks_on_none_and_time_gap():
    pts = [(0.0, 1.0), (1.0, 2.0), (2.0, None), (3.0, 3.0), (20.0, 4.0)]
    segs = charts.segment_points(pts, gap_s=8.0)
    # None splits after 1.0; the 3->20 jump (17s > 8s) splits again.
    assert segs == [[(0.0, 1.0), (1.0, 2.0)], [(3.0, 3.0)], [(20.0, 4.0)]]


def test_segment_points_contiguous_is_one_segment():
    pts = [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)]
    assert charts.segment_points(pts, 8.0) == [pts]


def test_segment_points_empty():
    assert charts.segment_points([], 8.0) == []


# --- nearest_value (crosshair sampling) -------------------------------------

def test_nearest_value_picks_closest_and_ignores_gaps():
    pts = [(0.0, 10.0), (10.0, None), (20.0, 30.0)]
    assert charts.nearest_value(pts, 1.0) == 10.0
    assert charts.nearest_value(pts, 19.0) == 30.0


def test_nearest_value_all_gaps_is_none():
    assert charts.nearest_value([(0.0, None), (1.0, None)], 0.5) is None


# --- zone band mapping ------------------------------------------------------

def test_zone_bands_tile_the_full_height_without_gaps():
    bands = charts.ZONE_BANDS
    assert bands[0][0] == 0.0
    assert bands[-1][1] == 1.0
    for (_lo, hi), (nlo, _nhi) in zip(bands, bands[1:]):
        assert hi == nlo                      # green->amber->red, contiguous
    # Thresholds match r057 (60 / 85).
    assert bands[0][1] == 0.60
    assert bands[1][1] == 0.85


# --- render_series headless smoke -------------------------------------------

def test_render_series_draws_without_a_display():
    cairo = pytest.importorskip("cairo")
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 80)
    cr = cairo.Context(surface)
    rx = [(0.0, 10.0), (1.0, 20.0), (2.0, None), (3.0, 30.0)]
    tx = [(0.0, 5.0), (1.0, 6.0), (2.0, 7.0), (3.0, 8.0)]
    # Multi-series + fills + zone bands + crosshair readout, all at once.
    charts.render_series(
        cr, 200, 80, [rx, tx], [charts.RX_RGB, charts.TX_RGB],
        vmax=100.0, fills=[True, True], zone_bands=True, gridlines=True,
        crosshair={"x": 100.0, "label": "now · rx 30%",
                   "markers": [(30.0, charts.RX_RGB)]})
    # Empty series list must be a no-op, not a crash.
    charts.render_series(cr, 200, 80, [], [])
