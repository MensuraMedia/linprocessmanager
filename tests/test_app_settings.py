"""Tests for src/config/app_settings.py (persistence-config.md acceptance).

Round-trip load/save with an injected tmp config dir, corrupt-file fallback,
the hostile-value clamping table, unknown-key preservation, and atomic-write
(no partial file / stray tmp on save). Pure stdlib — no GTK, no live kernel.
"""

import json
import os

import pytest

from config.app_settings import (
    AppSettings, COLUMN_KEYS, COLUMN_MIN_WIDTH, DEFAULT_INTERVAL,
    DEFAULT_VISIBLE_COLUMNS, MIN_INTERVAL, MAX_INTERVAL,
)


def _path(tmp_path):
    return os.path.join(str(tmp_path), "sub", "settings.json")


# --- round trip -------------------------------------------------------------

def test_round_trip_interval_sort_columns(tmp_path):
    settings = AppSettings({}, path=_path(tmp_path))
    settings.set_interval(0.5)
    settings.set_sort("memory", "asc")
    settings.set_show_kernel_threads(True)
    settings.set_scope("mine")
    settings.set_column_width("process", 321)
    settings.set_visible_columns(["pid", "cpu"])
    settings.save()

    reloaded = AppSettings.load(_path(tmp_path))
    assert reloaded.get("refresh_interval_s") == 0.5
    assert reloaded.get("sort") == {"column": "memory", "direction": "asc"}
    assert reloaded.get("show_kernel_threads") is True
    assert reloaded.get("scope_chip") == "mine"
    assert reloaded.get("columns")["widths"]["process"] == 321
    assert reloaded.get("columns")["visible"] == ["pid", "cpu"]


def test_defaults_when_file_missing(tmp_path):
    settings = AppSettings.load(_path(tmp_path))  # no file yet
    assert settings.get("refresh_interval_s") == DEFAULT_INTERVAL
    assert settings.get("view_mode") == "flat"
    assert settings.get("scope_chip") == "all"
    # r093: default visible is the opt-in-free head, not every extended column.
    assert settings.get("columns")["visible"] == list(DEFAULT_VISIBLE_COLUMNS)


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    target = _path(tmp_path)
    os.makedirs(os.path.dirname(target))
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("{not json at all,,,")
    settings = AppSettings.load(target)
    assert settings.get("refresh_interval_s") == DEFAULT_INTERVAL
    assert settings.get("cpu_normalized") == "per_core"


# --- hostile-value clamping table ------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    (0, DEFAULT_INTERVAL),
    (-1, DEFAULT_INTERVAL),
    (999, MAX_INTERVAL),
    (0.1, MIN_INTERVAL),
    ("abc", DEFAULT_INTERVAL),
    (None, DEFAULT_INTERVAL),
    (0.5, 0.5),
    (5.0, 5.0),
    (3, 3.0),
])
def test_interval_clamping(raw, expected):
    settings = AppSettings({"refresh_interval_s": raw})
    assert settings.get("refresh_interval_s") == expected


@pytest.mark.parametrize("key,raw,default", [
    ("view_mode", "spaghetti", "flat"),
    ("scope_chip", "everything", "all"),
    ("cpu_normalized", "per_toaster", "per_core"),
])
def test_bogus_enum_falls_back(key, raw, default):
    assert AppSettings({key: raw}).get(key) == default


@pytest.mark.parametrize("raw", ["yes", 1, None, "false"])
def test_show_kernel_threads_non_bool_defaults_false(raw):
    assert AppSettings({"show_kernel_threads": raw}).get("show_kernel_threads") is False


def test_unknown_columns_filtered_and_empty_defaults():
    settings = AppSettings({"columns": {"visible": ["pid", "bogus", "cpu"]}})
    assert settings.get("columns")["visible"] == ["pid", "cpu"]
    settings_empty = AppSettings({"columns": {"visible": []}})
    assert settings_empty.get("columns")["visible"] == list(DEFAULT_VISIBLE_COLUMNS)


def test_column_widths_clamped_to_minimums():
    settings = AppSettings({"columns": {"widths": {"process": 10, "pid": 999}}})
    widths = settings.get("columns")["widths"]
    assert widths["process"] == COLUMN_MIN_WIDTH["process"]  # 10 -> min
    assert widths["pid"] == 999                               # above min kept


def test_bogus_sort_falls_back():
    settings = AppSettings({"sort": {"column": "nope", "direction": "sideways"}})
    assert settings.get("sort") == {"column": "cpu", "direction": "desc"}


# --- unknown-key preservation + atomic write --------------------------------

def test_unknown_keys_survive_round_trip(tmp_path):
    settings = AppSettings(
        {"logs": {"saved_views": [1, 2]}, "future_flag": True},
        path=_path(tmp_path))
    settings.save()
    reloaded = AppSettings.load(_path(tmp_path))
    assert reloaded.get("logs") == {"saved_views": [1, 2]}
    assert reloaded.get("future_flag") is True


def test_atomic_write_leaves_no_tmp_and_valid_json(tmp_path):
    target = _path(tmp_path)
    settings = AppSettings({}, path=target)
    settings.save()
    directory = os.path.dirname(target)
    leftovers = [n for n in os.listdir(directory) if n.endswith(".tmp")]
    assert leftovers == []
    with open(target, "r", encoding="utf-8") as handle:
        parsed = json.load(handle)  # must be complete, parseable JSON
    assert parsed["refresh_interval_s"] == DEFAULT_INTERVAL


# --- r093 (task 010) column chooser groups + extended-column persistence ----

def test_column_groups_cover_every_key_exactly_once():
    from config.app_settings import COLUMN_GROUPS
    grouped = [k for _name, keys in COLUMN_GROUPS for k in keys]
    assert sorted(grouped) == sorted(COLUMN_KEYS)   # exact coverage
    assert len(grouped) == len(set(grouped))        # no key in two groups
    assert [name for name, _ in COLUMN_GROUPS] == [
        "Identity", "CPU", "Memory", "I/O & Network", "Diagnostics"]


def test_default_visible_is_the_opt_in_free_head():
    # The extended columns are opt-in: default-visible is the original set only.
    for extended in ("cmdline", "cpu_time", "affinity", "net_rx", "oom_score",
                     "started", "ppid", "pss"):
        assert extended in COLUMN_KEYS               # exists in the chooser
        assert extended not in DEFAULT_VISIBLE_COLUMNS  # but not shown by default


def test_extended_columns_visibility_round_trips(tmp_path):
    chosen = ["process", "cpu", "oom_score", "net_rx", "started", "affinity"]
    settings = AppSettings({}, path=_path(tmp_path))
    settings.set_visible_columns(chosen)
    settings.set_column_width("oom_score", 120)
    settings.save()
    reloaded = AppSettings.load(_path(tmp_path))
    assert reloaded.get("columns")["visible"] == chosen
    assert reloaded.get("columns")["widths"]["oom_score"] == 120


def test_default_path_honours_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    expected = os.path.join(str(tmp_path), "linprocman", "settings.json")
    assert AppSettings.default_path() == expected
