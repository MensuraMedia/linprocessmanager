"""Disks page (Phase 6, task 011) — per-mount capacity + per-device I/O rates.

Read-only. A summary band (Devices / Read / Write / Busiest) over a spreadsheet
of every real filesystem: Device, Mount, Type, Total, Used, Free, a zone-colored
usage bar with threshold ticks, Inodes %, Read/s, Write/s, Busy %. Unmounted
block devices are listed but FLAGGED; pseudo / squashfs / loop filesystems fold
into a "N hidden — show" count row (the kernel-threads pattern).

Data flow (diverges from the snapshot-observer boundary the other pages use, as
the task contract authorizes): this page consumes the pure readers
(:func:`procfs.system_diskstats`, :func:`procfs.system_mounts`) and ``os.statvfs``
DIRECTLY, at its own cadence — a manual Refresh button plus a bounded periodic
``GLib.timeout``. ``statvfs``/``stat`` never run on the UI thread (a stale NFS
mount can hang the call): each scan runs in a short-lived thread and posts its
result back via ``GLib.idle_add`` (the r071 recalibrate pattern). Rates are
computed against the previous scan's diskstats using the SAME counter-reset
clamp as the network delta machinery (:func:`disks.disk_rates`).

Boundary law: cairo through ``ui.compat.charts``, every toolkit call through a
compat seam, missing data renders "—" (r039). Bars are FIXED 160×8 boxes
(bounding-box policy §5b).
"""

import os
import threading
import time

from ui.compat import Gtk, GLib, Pango, css, layout, charts

from pages.page_base import BasePage
from config.app_settings import AppSettings
from modules import procfs
from modules import disks
from modules import manager_baseline
from modules import manager_rank as mr
from log import get_logger, log_exception

log = get_logger("disks")

# Bounded periodic re-scan (ms). Slow enough to be cheap, fast enough that a
# freshly mounted stick appears without waiting on the manual button.
_REFRESH_MS = 5000

_CARD_H = 64
_USAGE_W, _USAGE_H = 160, 8   # §5b fixed usage-bar box.

# Zone colours (r056 convention, copied from the Basics/Processes pages — the
# only colours on this page) and the usage-bar trough (disks-capacity.md §3.1).
_ZONE_RGB = {
    mr.ZONE_NOMINAL: (0x7f / 255.0, 0xd0 / 255.0, 0xa0 / 255.0),
    mr.ZONE_MEDIUM: (0xe8 / 255.0, 0xc2 / 255.0, 0x68 / 255.0),
    mr.ZONE_NEAR: (0xe0 / 255.0, 0x4c / 255.0, 0x4c / 255.0),
}
_TROUGH_RGB = (0x1b / 255.0, 0x1b / 255.0, 0x1b / 255.0)

_DIM = "#9a9a9a"
_WARN = "#d9a53f"
_TEXT = "#e6e6e6"

# Spreadsheet columns: (sort key, header title). The Usage cell is a bar but
# sorts on its usage %. Matches the task-011 scope column list.
_COLUMNS = [
    ("device", "Device"),
    ("mount", "Mount"),
    ("type", "Type"),
    ("total", "Total"),
    ("used", "Used"),
    ("free", "Free"),
    ("usage", "Usage"),
    ("inodes", "Inodes %"),
    ("read", "Read/s"),
    ("write", "Write/s"),
    ("busy", "Busy %"),
]

# Sort key -> entry field.
_SORT_FIELD = {
    "device": "device", "mount": "mount", "type": "fstype",
    "total": "total", "used": "used", "free": "free", "usage": "usage_pct",
    "inodes": "inode_pct", "read": "read_rate", "write": "write_rate",
    "busy": "busy",
}


def _escape(text):
    return (str(text) if text is not None else "").replace(
        "&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_bytes(value):
    if value is None or value < 0:
        return "—"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            if unit == "B":
                return "%d B" % int(size)
            return "%.1f %s" % (size, unit)
        size /= 1024.0
    return "%.1f TB" % size


def _fmt_rate(value):
    if value is None or value < 0:
        return "—"
    return _fmt_bytes(value) + "/s"


def _fmt_pct(value, decimals=1):
    if value is None:
        return "—"
    return "%.*f%%" % (decimals, value)


class DisksPage(BasePage):
    """Capacity + I/O for every filesystem, refreshed at its own cadence."""

    def build_content(self):
        self.settings = AppSettings.load()
        base = self.settings.get("baseline") or {}
        # r071 baseline provider: this machine's derived disk thresholds
        # (yellow 42 / red 60 on an SSD) drive the zone colour + ticks; the
        # provider's fixed defaults apply until first-run capture lands.
        thresholds = manager_baseline.Thresholds(base.get("thresholds"))
        self._yellow = thresholds.get("disk", "yellow") or disks.DEFAULT_YELLOW
        self._red = thresholds.get("disk", "red") or disks.DEFAULT_RED

        # Scan state (mutated only on the main thread, in _apply).
        self._prev_diskstats = None
        self._prev_time = None
        self._scanning = False
        self._show_hidden = False
        self._sort_key = "mount"
        self._sort_desc = False
        self._entries = []          # mounted, real filesystems (deduped)
        self._unmounted = []        # flagged leaf block devices
        self._pseudo_entries = []   # hidden pseudo/loop mounts (deduped)
        self._pseudo_count = 0
        self._summary = {"mounted": 0, "flagged": 0, "read": None,
                         "write": None, "busiest_name": None, "busiest_busy": None}

        self.add_title("Disks")
        self.add_markup_label(
            "<span foreground='#909090'>Read-only capacity and per-device I/O "
            "rates — /proc/diskstats + statvfs. Plug a stick in, then press "
            "Refresh.</span>", wrap=True, spacing_after=6)

        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        refresh = Gtk.Button(label="Refresh")
        refresh.set_tooltip_text("Re-scan mounts, capacity and I/O rates")
        css.add_css_class(refresh, "nav-button")
        refresh.connect("clicked", self._on_refresh)
        layout.box_add(tools, refresh, False, False, 0)
        layout.box_add(self, tools, False, False, 0)

        # Everything that changes per scan is rebuilt inside this box.
        self._results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                    spacing=12)
        self._results_children = []
        layout.box_add(self, self._results_box, True, True, 0)

        self.add_markup_label(
            "<span foreground='#7a7a7a'>Read-only · no mount / eject actions "
            "(elevation forbidden) · rates counter-reset clamped · unmounted "
            "devices flagged.</span>", wrap=True, spacing_after=0)

        self._rebuild_results()
        self.refresh()
        GLib.timeout_add(_REFRESH_MS, self._on_timer)

    # -- reveal / swap (show_all + get_children are gate-banned) -----------

    def _reveal(self, widget):
        def walk(w):
            if hasattr(w, "forall"):
                w.forall(lambda c: walk(c))
            w.show()
        walk(widget)

    def _rebuild_results(self):
        for child in self._results_children:
            layout.box_remove(self._results_box, child)
        self._results_children = []
        self._build_band()
        self._build_table()
        self._build_count_row()
        self._reveal(self._results_box)

    # -- refresh cadence --------------------------------------------------

    def _on_timer(self):
        self.refresh()
        return True   # keep the periodic source alive

    def _on_refresh(self, _button):
        self.refresh()

    def refresh(self):
        """Kick a background scan (mounts + statvfs + diskstats deltas).

        Guarded so an in-flight scan is never stacked (bounded concurrency); the
        blocking ``statvfs``/``stat`` calls run off the UI thread and marshal
        their result back via ``GLib.idle_add``.
        """
        if self._scanning:
            return False
        self._scanning = True
        prev = self._prev_diskstats
        prev_time = self._prev_time
        threading.Thread(target=self._scan, args=(prev, prev_time),
                         daemon=True).start()
        return False

    def _scan(self, prev, prev_time):
        """Worker thread: read the kernel, compute, post back. Never raises past
        here — an odd mount degrades to "—", it does not kill the thread."""
        try:
            now = time.monotonic()
            try:
                diskstats = procfs.system_diskstats()
            except OSError:
                diskstats = {}
            try:
                mounts = procfs.system_mounts()
            except OSError:
                mounts = []

            dwall = (now - prev_time) if prev_time is not None else None
            rates = disks.disk_rates(diskstats, prev, dwall)

            entries, pseudo = [], []
            for mount in mounts:
                entry = self._build_entry(mount, rates)
                if disks.is_pseudo(mount["fstype"], mount["device"]):
                    pseudo.append(entry)
                else:
                    entries.append(entry)
            entries = disks.dedup_by_stdev(entries)
            pseudo = disks.dedup_by_stdev(pseudo)

            mounted_basenames = {
                b for b in (disks.device_basename(m["device"]) for m in mounts)
                if b}
            unmounted = [
                self._unmounted_entry(name, rates)
                for name in disks.unmounted_devices(
                    list(diskstats.keys()), mounted_basenames)]

            summary = self._summarize(diskstats, rates, entries, unmounted)
            payload = {
                "diskstats": diskstats, "time": now,
                "entries": entries, "unmounted": unmounted,
                "pseudo": pseudo, "pseudo_count": len(pseudo),
                "summary": summary,
            }
        except Exception as exc:   # never let a scan crash the thread silently
            log.error("%s", log_exception("disks scan", exc))
            payload = None
        GLib.idle_add(self._apply, payload)

    def _build_entry(self, mount, rates):
        device, path, fstype = mount["device"], mount["mount"], mount["fstype"]
        st = st_dev = None
        try:
            st = os.statvfs(path)
        except OSError:
            st = None
        try:
            st_dev = os.stat(path).st_dev
        except OSError:
            st_dev = None
        cap = disks.capacity(st)
        base = disks.device_basename(device)
        rate = rates.get(base) if base else None
        rate = rate or {}
        return {
            "device": device, "basename": base, "mount": path, "fstype": fstype,
            "st_dev": st_dev, "flagged": False,
            "total": cap["total"], "used": cap["used"], "free": cap["free"],
            "usage_pct": cap["usage_pct"], "inode_pct": cap["inode_pct"],
            "read_rate": rate.get("read_rate"),
            "write_rate": rate.get("write_rate"), "busy": rate.get("busy"),
        }

    def _unmounted_entry(self, name, rates):
        rate = rates.get(name) or {}
        return {
            "device": "/dev/%s" % name, "basename": name, "mount": None,
            "fstype": None, "st_dev": None, "flagged": True,
            "total": None, "used": None, "free": None,
            "usage_pct": None, "inode_pct": None,
            "read_rate": rate.get("read_rate"),
            "write_rate": rate.get("write_rate"), "busy": rate.get("busy"),
        }

    def _summarize(self, diskstats, rates, entries, unmounted):
        # Sum rates over whole disks only so a disk and its partitions are not
        # double-counted; busiest is the whole disk with the highest util.
        tops = disks.top_level_devices(diskstats.keys())

        def total(field):
            vals = [rates[d][field] for d in tops
                    if d in rates and rates[d][field] is not None]
            return sum(vals) if vals else None

        busiest_name = busiest_busy = None
        for dev in tops:
            busy = (rates.get(dev) or {}).get("busy")
            if busy is not None and (busiest_busy is None or busy > busiest_busy):
                busiest_name, busiest_busy = dev, busy

        return {
            "mounted": len(entries), "flagged": len(unmounted),
            "read": total("read_rate"), "write": total("write_rate"),
            "busiest_name": busiest_name, "busiest_busy": busiest_busy,
        }

    def _apply(self, payload):
        self._scanning = False
        if payload is None:
            return False
        self._prev_diskstats = payload["diskstats"]
        self._prev_time = payload["time"]
        self._entries = payload["entries"]
        self._unmounted = payload["unmounted"]
        self._pseudo_entries = payload["pseudo"]
        self._pseudo_count = payload["pseudo_count"]
        self._summary = payload["summary"]
        self._rebuild_results()
        return False   # one-shot idle

    # -- summary band -----------------------------------------------------

    def _build_band(self):
        band = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        s = self._summary
        self._card(band, "Devices", str(s["mounted"] + s["flagged"]),
                   "%d mounted · %d unmounted (flagged)"
                   % (s["mounted"], s["flagged"]))
        self._card(band, "Read", _fmt_rate(s["read"]),
                   "whole disks · counter-reset clamped")
        self._card(band, "Write", _fmt_rate(s["write"]),
                   "whole disks · counter-reset clamped")
        busiest = s["busiest_name"] or "—"
        busy_cap = ("busy %s · util from diskstats"
                    % _fmt_pct(s["busiest_busy"], 0)
                    if s["busiest_busy"] is not None else "util from diskstats")
        self._card(band, "Busiest", busiest, busy_cap)
        layout.box_add(self._results_box, band, False, False, 0)
        self._results_children.append(band)

    def _card(self, row, key, value, caption):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card.set_hexpand(True)
        card.set_size_request(-1, _CARD_H)
        css.add_css_class(card, "basics-card")

        klbl = Gtk.Label(label=key)
        klbl.set_xalign(0)
        css.add_css_class(klbl, "basics-gauge-k")
        layout.box_add(card, klbl, False, False, 0)

        vlbl = Gtk.Label()
        vlbl.set_xalign(0)
        vlbl.set_use_markup(True)
        vlbl.set_width_chars(16)          # §5b: pinned so a long value can't grow the card
        vlbl.set_max_width_chars(16)
        vlbl.set_ellipsize(Pango.EllipsizeMode.END)
        vlbl.set_markup("<span foreground='%s' size='large'>%s</span>"
                        % (_TEXT, _escape(value)))
        layout.box_add(card, vlbl, False, False, 0)

        clbl = Gtk.Label()
        clbl.set_xalign(0)
        clbl.set_use_markup(True)
        clbl.set_width_chars(30)
        clbl.set_max_width_chars(30)
        clbl.set_ellipsize(Pango.EllipsizeMode.END)
        clbl.set_markup("<span foreground='#8a8a8a'>%s</span>" % _escape(caption))
        layout.box_add(card, clbl, False, False, 0)

        layout.box_add(row, card, True, True, 0)

    # -- spreadsheet ------------------------------------------------------

    def _sorted_rows(self):
        rows = list(self._entries) + list(self._unmounted)
        if self._show_hidden:
            rows = rows + list(self._pseudo_entries)
        field = _SORT_FIELD[self._sort_key]

        def norm(value):
            return value.lower() if isinstance(value, str) else value

        known = [r for r in rows if r.get(field) is not None]
        unknown = [r for r in rows if r.get(field) is None]
        known.sort(key=lambda r: norm(r.get(field)), reverse=self._sort_desc)
        return known + unknown   # unknowns always last, regardless of direction

    def _build_table(self):
        grid = Gtk.Grid()
        grid.set_column_spacing(1)
        grid.set_row_spacing(1)
        css.add_css_class(grid, "disks-table")
        for col, (key, title) in enumerate(_COLUMNS):
            grid.attach(self._header_cell(key, title), col, 0, 1, 1)
        for row_index, entry in enumerate(self._sorted_rows(), start=1):
            self._attach_row(grid, row_index, entry)
        layout.box_add(self._results_box, grid, False, False, 0)
        self._results_children.append(grid)

    def _header_cell(self, key, title):
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        css.add_css_class(button, "disks-th")
        label = Gtk.Label()
        label.set_xalign(0)
        label.set_use_markup(True)
        indicator = ""
        if self._sort_key == key:
            indicator = " ▾" if self._sort_desc else " ▴"
        label.set_markup("<b>%s</b>%s" % (_escape(title), indicator))
        layout.set_child(button, label)
        button.connect("clicked", lambda _b, k=key: self._on_sort(k))
        return button

    def _on_sort(self, key):
        if self._sort_key == key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key, self._sort_desc = key, False
        self._rebuild_results()

    def _attach_row(self, grid, row_index, entry):
        flagged = entry["flagged"]
        device = entry.get("basename") or entry.get("device") or "—"
        grid.attach(self._text_cell(device), 0, row_index, 1, 1)

        if entry["mount"] is None:
            grid.attach(self._text_cell("not mounted", dim=True),
                        1, row_index, 1, 1)
        else:
            grid.attach(self._text_cell(entry["mount"]), 1, row_index, 1, 1)

        grid.attach(self._text_cell(entry["fstype"] or "—"), 2, row_index, 1, 1)
        grid.attach(self._text_cell(_fmt_bytes(entry["total"])),
                    3, row_index, 1, 1)

        if flagged:
            grid.attach(self._text_cell("— flagged", warn=True),
                        4, row_index, 1, 1)
        else:
            grid.attach(self._text_cell(_fmt_bytes(entry["used"])),
                        4, row_index, 1, 1)

        grid.attach(self._text_cell(_fmt_bytes(entry["free"])),
                    5, row_index, 1, 1)
        grid.attach(self._usage_cell(entry), 6, row_index, 1, 1)
        grid.attach(self._text_cell(_fmt_pct(entry["inode_pct"])),
                    7, row_index, 1, 1)
        grid.attach(self._text_cell(_fmt_rate(entry["read_rate"]),
                                    dim=flagged), 8, row_index, 1, 1)
        grid.attach(self._text_cell(_fmt_rate(entry["write_rate"]),
                                    dim=flagged), 9, row_index, 1, 1)
        grid.attach(self._text_cell(_fmt_pct(entry["busy"], 0), dim=flagged),
                    10, row_index, 1, 1)

    def _text_cell(self, text, dim=False, warn=False):
        label = Gtk.Label()
        label.set_xalign(0)
        label.set_use_markup(True)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        color = _WARN if warn else (_DIM if dim else _TEXT)
        label.set_markup("<span foreground='%s'>%s</span>"
                         % (color, _escape(text)))
        css.add_css_class(label, "disks-td")
        return label

    def _usage_cell(self, entry):
        frac = zone = None
        pct = entry.get("usage_pct")
        if pct is not None:
            frac = max(0.0, min(1.0, pct / 100.0))
            zone = disks.usage_zone(pct, self._yellow, self._red)
        bar = charts.ChartArea(
            draw_func=lambda a, cr, w, h, f=frac, z=zone:
            self._draw_usage(cr, w, h, f, z))
        bar.set_size_request(_USAGE_W, _USAGE_H)   # §5b fixed box
        bar.set_valign(Gtk.Align.CENTER)
        return bar

    def _draw_usage(self, cr, width, height, frac, zone):
        cr.set_source_rgb(*_TROUGH_RGB)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        # Threshold ticks at the yellow/red crossings (Variant-2 language).
        cr.set_source_rgba(1, 1, 1, 0.14)
        for tick in (self._yellow / 100.0, self._red / 100.0):
            if 0.0 < tick < 1.0:
                cr.rectangle(tick * width, 0, 1, height)
                cr.fill()
        if frac is None:
            return
        rgb = _ZONE_RGB.get(zone, _ZONE_RGB[mr.ZONE_NOMINAL])
        cr.set_source_rgb(*rgb)
        cr.rectangle(0, 0, max(0.0, min(1.0, frac)) * width, height)
        cr.fill()

    # -- hidden count row -------------------------------------------------

    def _build_count_row(self):
        if self._pseudo_count == 0:
            return
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        css.add_css_class(button, "disks-count")
        label = Gtk.Label()
        label.set_xalign(0)
        label.set_use_markup(True)
        if self._show_hidden:
            text = "%d pseudo/loop devices — hide" % self._pseudo_count
        else:
            text = "%d pseudo/loop devices hidden — show" % self._pseudo_count
        label.set_markup("<span foreground='#8a8a8a'>%s</span>" % _escape(text))
        layout.set_child(button, label)
        button.connect("clicked", self._on_toggle_hidden)
        layout.box_add(self._results_box, button, False, False, 0)
        self._results_children.append(button)

    def _on_toggle_hidden(self, _button):
        self._show_hidden = not self._show_hidden
        self._rebuild_results()
