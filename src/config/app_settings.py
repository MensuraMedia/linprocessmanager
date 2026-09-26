"""Persistence skeleton for linprocman (docs/modules/persistence-config.md).

One settings file, written in one place, read at startup. Everything the app
remembers between runs lives here — nowhere else.

Toolkit-free by design: the module resolves the XDG config directory with the
stdlib (``$XDG_CONFIG_HOME`` or ``~/.config``, which is exactly what
``GLib.get_user_config_dir()`` returns) so it imports no ``gi`` and stays unit
testable headless — the raw-import ban forbids ``gi`` outside ``gtk_env`` and a
settings store has no business pulling GTK into a plain-Python import. The path
is injectable so tests round-trip against a tmp dir.

Every key is validated and clamped to its schema range at load: a hand-edited
``refresh_interval_s`` of 0 or -1 falls back to the default, an unknown enum to
its per-key default, a missing/corrupt file to all defaults — never a crash.
Unknown keys survive a save round-trip (forward compatibility).
"""

import json
import os
import tempfile

# Interval bounds mirror manager_sampler.{MIN,MAX,DEFAULT}_INTERVAL — kept as
# literals here so the toolkit-free config module needs no sampler import.
MIN_INTERVAL = 0.5
MAX_INTERVAL = 5.0
DEFAULT_INTERVAL = 2.0

# Canonical process-table column keys (order = default display order).
COLUMN_KEYS = [
    "process", "user", "cpu", "memory", "swap", "disk_rw", "nice", "pid",
    "state",
]

# Enforced per-column minimum widths (linfilesearch r025 lesson: a persisted
# width can never collapse a column below usability).
COLUMN_MIN_WIDTH = {
    "process": 200, "user": 90, "cpu": 70, "memory": 100, "swap": 90,
    "disk_rw": 120, "nice": 55, "pid": 75, "state": 80,
}

VIEW_MODES = ("flat", "tree")
SCOPE_CHIPS = ("all", "mine", "system", "active")
CPU_NORMALIZED = ("per_core", "total")
SORT_DIRECTIONS = ("asc", "desc")

DEFAULTS = {
    "refresh_interval_s": DEFAULT_INTERVAL,
    "view_mode": "flat",
    "columns": {
        "visible": list(COLUMN_KEYS),
        "widths": dict(COLUMN_MIN_WIDTH),
    },
    "sort": {"column": "cpu", "direction": "desc"},
    "scope_chip": "all",
    "show_kernel_threads": False,
    "cpu_normalized": "per_core",
}

# Top-level keys the validator owns; anything else is preserved verbatim.
_OWNED_KEYS = frozenset(DEFAULTS)


def _clamp_interval(value):
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL
    if seconds != seconds:  # NaN
        return DEFAULT_INTERVAL
    if seconds <= 0:  # invalid (0, negative) -> default per module doc
        return DEFAULT_INTERVAL
    return max(MIN_INTERVAL, min(MAX_INTERVAL, seconds))  # near-miss clamps


def _enum(value, allowed, default):
    return value if value in allowed else default


def _bool(value, default):
    return value if isinstance(value, bool) else default


def _validate_columns(raw):
    if not isinstance(raw, dict):
        raw = {}
    visible_raw = raw.get("visible")
    if isinstance(visible_raw, list):
        visible = [k for k in visible_raw if k in COLUMN_KEYS]
    else:
        visible = []
    if not visible:
        visible = list(COLUMN_KEYS)

    widths_raw = raw.get("widths")
    widths = dict(COLUMN_MIN_WIDTH)
    if isinstance(widths_raw, dict):
        for name, width in widths_raw.items():
            if name not in COLUMN_MIN_WIDTH:
                continue
            try:
                px = int(width)
            except (TypeError, ValueError):
                continue
            widths[name] = max(COLUMN_MIN_WIDTH[name], px)
    return {"visible": visible, "widths": widths}


def _validate_sort(raw):
    if not isinstance(raw, dict):
        raw = {}
    column = _enum(raw.get("column"), COLUMN_KEYS, "cpu")
    direction = _enum(raw.get("direction"), SORT_DIRECTIONS, "desc")
    return {"column": column, "direction": direction}


class AppSettings:
    """Load / mutate / save the single JSON settings file (validated)."""

    def __init__(self, data=None, path=None):
        self._path = path or self.default_path()
        self._data = self._validate(data if isinstance(data, dict) else {})

    # -- paths ------------------------------------------------------------

    @staticmethod
    def default_path():
        """``$XDG_CONFIG_HOME/linprocman/settings.json`` (``~/.config`` base)."""
        base = os.environ.get("XDG_CONFIG_HOME")
        if not base:
            base = os.path.join(os.path.expanduser("~"), ".config")
        return os.path.join(base, "linprocman", "settings.json")

    # -- load / save ------------------------------------------------------

    @classmethod
    def load(cls, path=None):
        """Read + validate the file. Missing/corrupt → defaults (never crash)."""
        target = path or cls.default_path()
        raw = {}
        try:
            with open(target, "r", encoding="utf-8") as handle:
                parsed = json.load(handle)
            if isinstance(parsed, dict):
                raw = parsed
        except (FileNotFoundError, ValueError, OSError, UnicodeDecodeError):
            raw = {}
        return cls(raw, target)

    def save(self):
        """Atomic write: tmp file in the target dir + ``os.replace`` (rename).

        Never truncates the live file in place — an interrupted save leaves the
        previous good file untouched.
        """
        directory = os.path.dirname(self._path)
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=directory, prefix=".settings-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self._path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # -- validation -------------------------------------------------------

    def _validate(self, raw):
        data = {
            "refresh_interval_s": _clamp_interval(raw.get("refresh_interval_s")),
            "view_mode": _enum(raw.get("view_mode"), VIEW_MODES, "flat"),
            "columns": _validate_columns(raw.get("columns")),
            "sort": _validate_sort(raw.get("sort")),
            "scope_chip": _enum(raw.get("scope_chip"), SCOPE_CHIPS, "all"),
            "show_kernel_threads": _bool(raw.get("show_kernel_threads"), False),
            "cpu_normalized": _enum(
                raw.get("cpu_normalized"), CPU_NORMALIZED, "per_core"),
        }
        # Forward compatibility: keep every key we do not own untouched.
        for key, value in raw.items():
            if key not in _OWNED_KEYS:
                data[key] = value
        return data

    # -- accessors --------------------------------------------------------

    def get(self, key, default=None):
        return self._data.get(key, default)

    def as_dict(self):
        """A defensive copy of the validated settings (for inspection/tests)."""
        return json.loads(json.dumps(self._data))

    @property
    def path(self):
        return self._path

    def set(self, key, value):
        """Set a single top-level key, re-validating owned keys on the way in."""
        merged = dict(self._data)
        merged[key] = value
        self._data = self._validate(merged)

    # -- typed convenience setters (each clamps via _validate) -----------

    def set_interval(self, seconds):
        self.set("refresh_interval_s", seconds)

    def set_sort(self, column, direction):
        self.set("sort", {"column": column, "direction": direction})

    def set_scope(self, scope):
        self.set("scope_chip", scope)

    def set_show_kernel_threads(self, value):
        self.set("show_kernel_threads", bool(value))

    def set_view_mode(self, mode):
        self.set("view_mode", mode)

    def set_column_width(self, name, width):
        columns = dict(self._data["columns"])
        widths = dict(columns["widths"])
        widths[name] = width
        columns["widths"] = widths
        self.set("columns", columns)

    def set_visible_columns(self, visible):
        columns = dict(self._data["columns"])
        columns["visible"] = list(visible)
        self.set("columns", columns)
