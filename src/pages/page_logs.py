"""
Logs Page — minimal functional journal viewer (Phase 7, part 1).

Feeds off the UI-free engine :mod:`modules.manager_logs` (argv-contract
journalctl reader). This page wires the four presets, a unit filter, a priority
filter, a lines selector, a Load button and a monospace read-only results list
with mockup-E priority coloring (red for err/alert, amber for warning, dimmed
for debug). Search/follow cadence, saved views and flags are task 014 — not
built here.
"""

import threading

from ui.compat import Gtk, GLib, Pango, css, layout

from pages.page_base import BasePage
from modules import manager_logs
from log import get_logger

log = get_logger("logs")


# Preset combo rows -> engine preset ids (order fixed; mockup E submenu order).
_PRESETS = (
    ("Journal", "journal"),
    ("Kernel", "kernel"),
    ("Auth", "auth"),
    ("Applications", "applications"),
)

# Priority combo rows -> engine --priority value (None = all levels).
_PRIORITIES = (
    ("All priorities", None),
    ("Error", "err"),
    ("Warning", "warning"),
    ("Notice", "notice"),
    ("Info", "info"),
    ("Debug", "debug"),
)

_LINES = (200, 500, 1000, 2000)

# priority level -> short badge label.
_PRIO_LABELS = {
    0: "EMERG", 1: "ALERT", 2: "CRIT", 3: "ERR",
    4: "WARN", 5: "NOTICE", 6: "INFO", 7: "DEBUG",
}

# severity bucket (manager_logs.severity) -> foreground; normal = theme default.
_SEVERITY_COLORS = {"error": "#e88", "warning": "#e8c268", "debug": "#777"}


class LogsPage(BasePage):
    """Logs page — preset-driven journalctl viewer (minimal, functional)."""

    COL_TIME = 0
    COL_PRIO = 1
    COL_UNIT = 2
    COL_MSG = 3

    def build_content(self):
        """Build page content."""
        self.add_title("Logs — Journal")

        self._build_controls()

        self.status_label = Gtk.Label(label="Choose a preset and Load.")
        self.status_label.set_xalign(0)
        css.add_css_class(self.status_label, "page-subtitle")
        layout.box_add(self, self.status_label, False, False, 0)

        self._build_results()

    # -- controls ---------------------------------------------------------

    def _build_controls(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.preset_combo = Gtk.ComboBoxText()
        for label, _pid in _PRESETS:
            self.preset_combo.append_text(label)
        self.preset_combo.set_active(0)
        self.preset_combo.set_tooltip_text("Journal source preset")
        layout.box_add(bar, self.preset_combo, False, False, 0)

        self.unit_entry = Gtk.Entry()
        self.unit_entry.set_placeholder_text("unit (e.g. sshd.service)")
        self.unit_entry.set_width_chars(22)
        self.unit_entry.set_tooltip_text("Filter by systemd unit")
        layout.box_add(bar, self.unit_entry, False, False, 0)

        self.priority_combo = Gtk.ComboBoxText()
        for label, _value in _PRIORITIES:
            self.priority_combo.append_text(label)
        self.priority_combo.set_active(0)
        self.priority_combo.set_tooltip_text("Minimum priority")
        layout.box_add(bar, self.priority_combo, False, False, 0)

        self.lines_combo = Gtk.ComboBoxText()
        for count in _LINES:
            self.lines_combo.append_text("%d lines" % count)
        self.lines_combo.set_active(1)  # 500
        self.lines_combo.set_tooltip_text("How many recent entries to load")
        layout.box_add(bar, self.lines_combo, False, False, 0)

        self.load_button = Gtk.Button(label="Load")
        self.load_button.connect("clicked", self._on_load)
        layout.box_add(bar, self.load_button, False, False, 0)

        layout.box_add(self, bar, False, False, 0)

    # -- results view -----------------------------------------------------

    def _build_results(self):
        # time, priority (int), unit, message
        self.store = Gtk.ListStore(str, int, str, str)
        self.treeview = Gtk.TreeView(model=self.store)
        self.treeview.set_enable_search(False)
        self.treeview.get_selection().set_mode(Gtk.SelectionMode.SINGLE)

        self._add_column("Time", self.COL_TIME, width=110)
        self._add_column("Priority", self.COL_PRIO, width=80)
        self._add_column("Unit / Source", self.COL_UNIT, width=170)
        self._add_column("Message", self.COL_MSG, width=520, ellipsize=True)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(420)
        layout.set_child(scrolled, self.treeview)
        layout.box_add(self, scrolled, True, True, 0)

    def _add_column(self, title, store_index, width, ellipsize=False):
        renderer = Gtk.CellRendererText()
        # Monospace read-only rows (mockup E: tabular, dense).
        renderer.set_property("family", "Monospace")
        renderer.set_property("family-set", True)
        if ellipsize:
            renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        column = Gtk.TreeViewColumn(title, renderer)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column.set_fixed_width(width)
        column.set_min_width(width)
        column.set_resizable(True)
        column.set_cell_data_func(renderer, self._cell_data, store_index)
        self.treeview.append_column(column)
        return column

    def _cell_data(self, _column, cell, model, it, store_index):
        prio = model.get_value(it, self.COL_PRIO)
        color = _SEVERITY_COLORS.get(manager_logs.severity(prio))
        if color:
            cell.set_property("foreground", color)
            cell.set_property("foreground-set", True)
        else:
            cell.set_property("foreground-set", False)
        if store_index == self.COL_PRIO:
            text = _PRIO_LABELS.get(prio, str(prio))
        else:
            text = model.get_value(it, store_index)
        cell.set_property("text", text)

    # -- load / populate --------------------------------------------------

    def _collect_argv(self):
        """Build the journalctl argv from the current control state.

        Pure read of the widgets; raises ``ValueError`` only if the engine
        rejects the assembled filter (guarded before spawn).
        """
        _label, preset = _PRESETS[max(self.preset_combo.get_active(), 0)]
        _plabel, priority = _PRIORITIES[max(self.priority_combo.get_active(), 0)]
        lines = _LINES[max(self.lines_combo.get_active(), 0)]
        unit = self.unit_entry.get_text().strip() or None
        return manager_logs.build_argv(
            preset, unit=unit, priority=priority, lines=lines)

    def _on_load(self, _button):
        try:
            argv = self._collect_argv()
        except ValueError as exc:
            self.status_label.set_text("Invalid filter: %s" % exc)
            return
        self.load_button.set_sensitive(False)
        self.status_label.set_text("Loading…")

        def work():
            entries = manager_logs.read_journal(argv)
            GLib.idle_add(self._populate, entries)

        threading.Thread(target=work, daemon=True).start()

    def _populate(self, entries):
        """Fill the results store from engine entries (main-thread callback)."""
        self.store.clear()
        self.load_button.set_sensitive(True)

        if len(entries) == 1 and "error" in entries[0]:
            self.status_label.set_text(entries[0]["error"])
            return
        if not entries:
            # Empty ≠ locked (logs-journal.md r042): a readable-but-empty
            # source says so plainly — never an error dialog.
            self.status_label.set_text("No entries match — none in retention.")
            return

        for entry in entries:
            self.store.append([
                entry.get("timestamp", ""),
                entry.get("priority", manager_logs.DEFAULT_PRIORITY),
                entry.get("unit", manager_logs.DASH),
                entry.get("message", ""),
            ])
        self.status_label.set_text("%d entries loaded." % len(entries))
        return False  # one-shot idle callback
