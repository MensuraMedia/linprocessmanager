"""Cairo draw hookup for chart/custom-drawn widgets (upgrade-architecture.md
§3, seam 5; gtk4-port.md §4.5).

Cairo drawing is toolkit-agnostic; only the callback hookup differs:

- GTK3 : ``drawing_area.connect("draw", cb)`` — ``cb(widget, cr)``.
- GTK4 : ``drawing_area.set_draw_func(cb)`` — ``cb(area, cr, width, height)``.

``ChartArea`` is the ONLY place allowed to connect the ``draw`` signal (the
gate bans that connection elsewhere). It normalizes both paths to a single
draw callback ``cb(area, cr, width, height)`` so chart code talks only to the
adapter + a cairo context.

The seam also owns the **shared multi-series renderer** (:func:`render_series`,
r068/mockup M) plus the pure geometry/palette helpers it is built from
(:func:`series_palette`, :func:`segment_points`, :func:`nearest_value`). Cairo
drawing is version-agnostic, so all chart pages draw through this one helper —
legends, fills, gridlines, zone bands and the hover crosshair are defined here
once and shared by the Graphs hub, the per-metric detail pages, and the Basics
gauge bars. The pure helpers carry no cairo, so the palette/segmentation math is
fixture-testable without a display.
"""

import math

from .gtk_env import Gtk, GTK_MAJOR

# --- palette + zone constants (r042: shade-step from the accent, never a
# hardcoded per-series colour list; r057 threshold zones) ---------------------

ACCENT_RGB = (0x00 / 255.0, 0x78 / 255.0, 0xD7 / 255.0)   # theme accent (primary)
RX_RGB = (0x3f / 255.0, 0xbf / 255.0, 0x6f / 255.0)        # down/rx — green family
TX_RGB = (0xe8 / 255.0, 0xa3 / 255.0, 0x3d / 255.0)        # up/tx — amber family

# Threshold-zone band fractions of the chart height (green / amber / red).
ZONE_BANDS = ((0.0, 0.60), (0.60, 0.85), (0.85, 1.0))
_ZONE_BAND_RGBA = (
    (0x7f / 255.0, 0xd0 / 255.0, 0xa0 / 255.0, 0.08),
    (0xe8 / 255.0, 0xc2 / 255.0, 0x68 / 255.0, 0.08),
    (0xe0 / 255.0, 0x4c / 255.0, 0x4c / 255.0, 0.08),
)
_GRID_RGBA = (1, 1, 1, 0.08)
_FILL_ALPHA = 0.14           # area fill under a primary series (spec: 12-16%)
_CROSSHAIR_RGBA = (0.62, 0.62, 0.62, 0.85)


class ChartArea(Gtk.DrawingArea):
    """A ``Gtk.DrawingArea`` whose draw callback is version-normalized.

    Pass ``draw_func=cb`` or call ``set_draw_callback(cb)`` later. ``cb`` is
    always invoked as ``cb(area, cr, width, height)`` on both toolkits.
    """

    def __init__(self, draw_func=None):
        super().__init__()
        self._draw_func = None
        self._gtk3_handler_id = None
        if draw_func is not None:
            self.set_draw_callback(draw_func)

    def set_draw_callback(self, draw_func):
        """Register the normalized draw callback, wiring the version path."""
        self._draw_func = draw_func
        if GTK_MAJOR >= 4:
            self.set_draw_func(self._on_draw_gtk4)
        else:
            if self._gtk3_handler_id is None:
                self._gtk3_handler_id = self.connect("draw", self._on_draw_gtk3)

    def _on_draw_gtk3(self, widget, cr):
        allocation = widget.get_allocation()
        if self._draw_func is not None:
            self._draw_func(widget, cr, allocation.width, allocation.height)
        return False

    def _on_draw_gtk4(self, area, cr, width, height):
        if self._draw_func is not None:
            self._draw_func(area, cr, width, height)


# ===========================================================================
# Pure helpers (no cairo) — palette, segmentation, sampling.
# ===========================================================================

def _mix(rgb, target, t):
    """Blend ``rgb`` toward ``target`` by fraction ``t`` (0..1)."""
    return tuple(rgb[i] + (target[i] - rgb[i]) * t for i in range(3))


def series_palette(base_rgb, count):
    """``count`` shade-stepped RGB tuples derived from ``base_rgb``.

    r042 rule: a per-series palette is *generated* from the theme accent, never a
    hardcoded N-colour list, so any core/series count reads as one family. The
    walk runs symmetrically darker→base→lighter, so adjacent steps stay
    distinguishable while the hue is held.
    """
    if count <= 0:
        return []
    if count == 1:
        return [tuple(base_rgb)]
    out = []
    for i in range(count):
        pos = (i / (count - 1)) * 2.0 - 1.0        # -1 (dark) .. +1 (light)
        if pos < 0:
            out.append(_mix(base_rgb, (0.0, 0.0, 0.0), -pos * 0.55))
        else:
            out.append(_mix(base_rgb, (1.0, 1.0, 1.0), pos * 0.55))
    return out


def segment_points(points, gap_s):
    """Split a ``(ts, value)`` series into contiguous drawable segments.

    The line breaks (ring law, gap honesty) at every ``None`` value and at every
    time gap larger than ``gap_s`` — a pause or backoff window renders as a gap,
    never an interpolated straight line. Returns a list of segments, each a list
    of ``(ts, value)`` with no ``None`` inside.
    """
    segments = []
    current = []
    prev_t = None
    for ts, value in points:
        if value is None:
            if current:
                segments.append(current)
                current = []
            prev_t = None
            continue
        if prev_t is not None and (ts - prev_t) > gap_s:
            if current:
                segments.append(current)
                current = []
        current.append((ts, value))
        prev_t = ts
    if current:
        segments.append(current)
    return segments


def nearest_value(points, ts):
    """Value of the sample nearest ``ts`` (gaps/``None`` ignored), or ``None``."""
    best = None
    best_d = None
    for t, value in points:
        if value is None:
            continue
        d = abs(t - ts)
        if best_d is None or d < best_d:
            best_d = d
            best = value
    return best


# ===========================================================================
# The shared multi-series renderer (r068, mockup M).
# ===========================================================================

def _value_to_y(value, vmax, h):
    frac = min(1.0, max(0.0, value / vmax)) if vmax > 0 else 0.0
    return h - frac * (h - 2) - 1


def _draw_zone_bands(cr, w, h, zone_band_colors):
    colours = zone_band_colors or _ZONE_BAND_RGBA
    for (lo, hi), rgba in zip(ZONE_BANDS, colours):
        cr.set_source_rgba(*rgba)
        y = h - hi * h
        cr.rectangle(0, y, w, (hi - lo) * h)
        cr.fill()


def _draw_gridlines(cr, w, h):
    cr.set_source_rgba(*_GRID_RGBA)
    for frac in (0.25, 0.5, 0.75):
        cr.rectangle(0, h - frac * h, w, 1)
        cr.fill()


def _draw_trace(cr, w, h, points, t0, span, vmax, rgb, width, fill, gap_s):
    segments = segment_points(points, gap_s)
    if fill:
        cr.set_source_rgba(rgb[0], rgb[1], rgb[2], _FILL_ALPHA)
        for seg in segments:
            if len(seg) < 2:
                continue
            first_x = (seg[0][0] - t0) / span * w
            cr.move_to(first_x, h)
            for ts, value in seg:
                cr.line_to((ts - t0) / span * w, _value_to_y(value, vmax, h))
            cr.line_to((seg[-1][0] - t0) / span * w, h)
            cr.close_path()
            cr.fill()
    cr.set_source_rgb(*rgb)
    cr.set_line_width(width)
    for seg in segments:
        if len(seg) < 2:
            continue
        started = False
        for ts, value in seg:
            x = (ts - t0) / span * w
            y = _value_to_y(value, vmax, h)
            if started:
                cr.line_to(x, y)
            else:
                cr.move_to(x, y)
                started = True
        cr.stroke()


def render_series(cr, w, h, points_list, colors, *, vmax=None, t0=None, span=None,
                  fills=None, line_widths=None, primary_index=0, fill_primary=True,
                  gridlines=True, zone_bands=False, zone_band_colors=None,
                  crosshair=None, gap_s=8.0, endpoint_dot=True, value_floor=1.0):
    """Draw an ordered set of ``(ts, value)`` series on ``cr`` over ``w``x``h``.

    ``points_list`` is the ordered series (each a ``(ts, value)`` list, ``None``
    as a gap marker); ``colors`` the matching RGB per series. The primary series
    (``primary_index``) is drawn last so it sits on top of the others, gets the
    endpoint dot, and — when ``fill_primary`` and no explicit ``fills`` — the
    area fill. ``vmax`` fixes the value mapped to the chart top (auto-scaled from
    the trailing peak when ``None``); ``t0``/``span`` fix the time axis (spanned
    across every series when ``None``). ``zone_bands`` paints the r057 threshold
    bands (percentage charts); ``crosshair`` is an optional
    ``{"x", "label", "markers": [(value, rgb), ...]}`` readout drawn on-chart.

    Gap honesty (ring law) is enforced by :func:`segment_points`: the line and
    its fill break at ``None`` and at time gaps wider than ``gap_s``.
    """
    n = len(points_list)
    if zone_bands:
        _draw_zone_bands(cr, w, h, zone_band_colors)
    if gridlines:
        _draw_gridlines(cr, w, h)
    if n == 0:
        return

    if t0 is None or span is None:
        lo = hi = None
        for pts in points_list:
            if pts:
                lo = pts[0][0] if lo is None else min(lo, pts[0][0])
                hi = pts[-1][0] if hi is None else max(hi, pts[-1][0])
        if lo is None:
            return
        t0 = lo
        span = max(1e-6, hi - lo)

    if vmax is None:
        peak = 0.0
        for pts in points_list:
            for _ts, value in pts:
                if value is not None and value > peak:
                    peak = value
        vmax = max(value_floor, peak * 1.2)
    if vmax <= 0:
        return

    if colors is None:
        colors = [ACCENT_RGB] * n
    if fills is None:
        fills = [False] * n
        if fill_primary and 0 <= primary_index < n:
            fills[primary_index] = True
    if line_widths is None:
        line_widths = [1.6] * n
        if 0 <= primary_index < n:
            line_widths[primary_index] = 2.2

    # Non-primary first, primary last (drawn on top).
    order = [i for i in range(n) if i != primary_index]
    if 0 <= primary_index < n:
        order.append(primary_index)
    for i in order:
        _draw_trace(cr, w, h, points_list[i], t0, span, vmax,
                    colors[i], line_widths[i], fills[i], gap_s)

    if endpoint_dot and 0 <= primary_index < n:
        last = None
        for ts, value in points_list[primary_index]:
            if value is not None:
                last = (ts, value)
        if last is not None:
            cr.set_source_rgb(*colors[primary_index])
            cr.arc((last[0] - t0) / span * w,
                   _value_to_y(last[1], vmax, h), 3.0, 0, 2 * math.pi)
            cr.fill()

    if crosshair:
        _draw_crosshair(cr, w, h, vmax, crosshair)


def _draw_crosshair(cr, w, h, vmax, crosshair):
    cx = min(max(float(crosshair.get("x", 0.0)), 0.0), w)
    cr.set_source_rgba(*_CROSSHAIR_RGBA)
    cr.set_line_width(1.0)
    cr.set_dash([3.0, 3.0])
    cr.move_to(cx, 0)
    cr.line_to(cx, h)
    cr.stroke()
    cr.set_dash([])
    for value, rgb in crosshair.get("markers", ()):  # dot per visible series
        cr.set_source_rgb(*rgb)
        cr.arc(cx, _value_to_y(value, vmax, h), 3.0, 0, 2 * math.pi)
        cr.fill()
    label = crosshair.get("label")
    if label:
        cr.select_font_face("Ubuntu")
        cr.set_font_size(10)
        cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.move_to(6, 13)
        cr.show_text(label)


# ---------------------------------------------------------------------------
# Tx←→Rx packet-tick bar (mockup R — CONFIRMED r129) — the shared network
# representation. Any network feature draws ITS activity bar through this
# function so every surface in the app reads the same visual language:
# Tx ticks packed from the LEFT edge growing toward the center, Rx ticks
# from the RIGHT edge growing toward the center, center line = zero.
# ---------------------------------------------------------------------------

TX_TICK_RGB = (0xfa / 255.0, 0xcc / 255.0, 0x15 / 255.0)   # yellow: sent
RX_TICK_RGB = (0x21 / 255.0, 0x96 / 255.0, 0xf3 / 255.0)   # blue: received
TXRX_TROUGH_RGB = (0x1b / 255.0, 0x1b / 255.0, 0x1b / 255.0)
TXRX_MIDLINE_RGB = (0x3a / 255.0, 0x3a / 255.0, 0x3a / 255.0)


def txrx_ticks(width, tx_share, rx_share, *, tick=3.0, gap=2.0):
    """Packet-tick counts for a Tx←→Rx bar of ``width`` px.

    ``tx_share``/``rx_share`` are per-side fractions of their own half
    (0.0–1.0). Returns ``(tx_ticks, rx_ticks)`` where each tick is one
    packet burst (tick+gap period). Zero-share sides get zero ticks.
    """
    per_half = max(1, int(width // 2 // (tick + gap)))
    return (int(round(tx_share * per_half)), int(round(rx_share * per_half)))


def draw_txrx_bar(cr, width, height, tx_ticks, rx_ticks, *, tick=3.0):
    """Draw the bidirectional packet-tick bar onto an existing cairo context.

    Tx ticks grow from the LEFT edge toward the center; Rx ticks grow from
    the RIGHT edge toward the center; the center line is zero. Unknown
    traffic (either count None) renders the trough + center line alone.
    """
    cr.set_source_rgb(*TXRX_TROUGH_RGB)
    cr.rectangle(0, 0, width, height)
    cr.fill()
    half = width / 2.0
    cr.set_source_rgb(*TXRX_MIDLINE_RGB)
    cr.rectangle(half - 0.5, 0, 1, height)
    cr.fill()
    if tx_ticks:
        cr.set_source_rgb(*TX_TICK_RGB)
        for i in range(tx_ticks):
            cr.rectangle(i * tick, 0, tick - 1.0, height)
        cr.fill()
    if rx_ticks:
        cr.set_source_rgb(*RX_TICK_RGB)
        for i in range(rx_ticks):
            cr.rectangle(width - (i + 1) * tick, 0, tick - 1.0, height)
        cr.fill()


def txrx_bar_surface(width, height, tx_ticks, rx_ticks, *, tick=3.0):
    """``draw_txrx_bar`` onto a fresh ARGB32 surface (pixbuf/preview use)."""
    import cairo
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(width), int(height))
    draw_txrx_bar(cairo.Context(surf), int(width), int(height),
                  tx_ticks, rx_ticks, tick=tick)
    surf.flush()
    return surf
