"""Logs engine — argv contract, JSON/plaintext parse, subprocess guards.

Covers ``src/modules/manager_logs.py`` (docs/modules/logs-journal.md). The
argv-contract tests come first and pin every journalctl invocation as an EXACT
argv list: no shell, no string formatting of the command line, user input only
in ``=``-form flag values (``--grep=…``) or field matches (``_SYSTEMD_UNIT=…``,
``_UID=…``) — so a value can never be reparsed as a flag.

Pure engine: no GTK, no display; the subprocess boundary is exercised by
monkeypatching ``manager_logs.subprocess`` so the guards run without a live
journal (the live journal load is ZCode's :0 capture step).
"""

import json
import os
import re

import pytest

import manager_logs


BIN = "/usr/bin/journalctl"
BASE = [BIN, "--no-pager", "--output=json"]


# ===========================================================================
# 1. argv contract — EXACT frozen argv lists (step 1, security boundary)
# ===========================================================================

def test_argv_journal_preset_is_the_frozen_base():
    assert manager_logs.build_argv("journal") == BASE + ["--lines=500"]


def test_argv_kernel_preset_adds_dmesg_flag():
    assert manager_logs.build_argv("kernel") == BASE + ["-k", "--lines=500"]


def test_argv_auth_preset_uses_facility_value():
    assert manager_logs.build_argv("auth") == (
        BASE + ["--facility=auth,authpriv", "--lines=500"])


def test_argv_applications_preset_matches_current_uid():
    argv = manager_logs.build_argv("applications")
    assert argv == BASE + ["--lines=500", "_UID=%d" % os.getuid()]


def test_argv_unit_filter_is_a_field_match_not_a_flag():
    argv = manager_logs.build_argv("journal", unit="firefox.scope")
    assert argv == BASE + ["--lines=500", "_SYSTEMD_UNIT=firefox.scope"]


def test_argv_priority_by_name_and_by_number():
    assert manager_logs.build_argv("journal", priority="err") == (
        BASE + ["--priority=err", "--lines=500"])
    assert manager_logs.build_argv("journal", priority=3) == (
        BASE + ["--priority=3", "--lines=500"])


def test_argv_since_until_time_jump():
    argv = manager_logs.build_argv(
        "journal", since="2026-09-28 12:00:00", until="2026-09-28 13:00:00")
    assert argv == BASE + [
        "--since=2026-09-28 12:00:00", "--until=2026-09-28 13:00:00",
        "--lines=500"]


def test_argv_follow_and_tail_lines_count():
    argv = manager_logs.build_argv("journal", lines=100, follow=True)
    assert argv == BASE + ["--lines=100", "--follow"]


def test_argv_grep_is_an_equals_form_value():
    argv = manager_logs.build_argv("journal", grep="nvme0n1")
    assert argv == BASE + ["--lines=500", "--grep=nvme0n1"]


def test_argv_all_fields_together_are_ordered_and_frozen():
    argv = manager_logs.build_argv(
        "kernel", unit="sshd.service", priority="warning",
        since="09:00", until="10:00", grep="timeout", lines=250, follow=True)
    assert argv == [
        BIN, "--no-pager", "--output=json", "-k",
        "--priority=warning", "--since=09:00", "--until=10:00",
        "--lines=250", "--follow", "--grep=timeout",
        "_SYSTEMD_UNIT=sshd.service",
    ]


# --- flag-injection: user input can never become a flag --------------------

def test_flag_looking_unit_lands_as_a_value_never_a_flag():
    argv = manager_logs.build_argv("journal", unit="--merge")
    assert argv[-1] == "_SYSTEMD_UNIT=--merge"
    assert "--merge" not in argv[:-1]  # never a bare flag token


def test_flag_looking_grep_stays_inside_the_equals_value():
    argv = manager_logs.build_argv("journal", grep="-D /etc")
    assert "--grep=-D /etc" in argv
    assert "-D" not in argv  # not split into a directory flag


# --- validation: invalid input -> ValueError, never a malformed command ----

def test_unknown_preset_raises():
    with pytest.raises(ValueError):
        manager_logs.build_argv("syslog")


@pytest.mark.parametrize("bad", ["critical", "9", "-1", "err ", "", 8, -1, 3.0, True])
def test_invalid_priority_raises(bad):
    with pytest.raises(ValueError):
        manager_logs.build_argv("journal", priority=bad)


@pytest.mark.parametrize("bad", [0, -5, "500", 5.0, True, 10 ** 9])
def test_invalid_lines_raises(bad):
    with pytest.raises(ValueError):
        manager_logs.build_argv("journal", lines=bad)


@pytest.mark.parametrize("field", ["unit", "grep", "since", "until"])
def test_control_chars_in_values_raise(field):
    with pytest.raises(ValueError):
        manager_logs.build_argv("journal", **{field: "a\nb"})
    with pytest.raises(ValueError):
        manager_logs.build_argv("journal", **{field: "a\x00b"})


@pytest.mark.parametrize("field", ["unit", "grep", "since", "until"])
def test_non_string_values_raise(field):
    with pytest.raises(ValueError):
        manager_logs.build_argv("journal", **{field: 5})


# ===========================================================================
# 2. parse — journalctl --output=json fields + plaintext fallback
# ===========================================================================

def _jline(**fields):
    return json.dumps(fields)


def test_parse_json_line_extracts_all_four_fields():
    line = _jline(
        __REALTIME_TIMESTAMP="1700000000000000", PRIORITY="3",
        _SYSTEMD_UNIT="nginx.service", MESSAGE="connection refused")
    (entry,) = manager_logs.parse_entries(line)
    assert entry["priority"] == 3
    assert entry["unit"] == "nginx.service"
    assert entry["message"] == "connection refused"
    assert re.match(r"^\d{2}:\d{2}:\d{2}$", entry["timestamp"])


def test_parse_unit_falls_back_to_identifier_then_comm_then_dash():
    ident = manager_logs.parse_entries(
        _jline(SYSLOG_IDENTIFIER="sudo", MESSAGE="x"))[0]
    assert ident["unit"] == "sudo"
    comm = manager_logs.parse_entries(_jline(_COMM="bash", MESSAGE="x"))[0]
    assert comm["unit"] == "bash"
    none = manager_logs.parse_entries(_jline(MESSAGE="x"))[0]
    assert none["unit"] == "—"


def test_parse_missing_priority_defaults_to_info():
    entry = manager_logs.parse_entries(_jline(MESSAGE="x"))[0]
    assert entry["priority"] == 6  # info


def test_parse_message_byte_array_is_decoded():
    entry = manager_logs.parse_entries(_jline(MESSAGE=[104, 105]))[0]
    assert entry["message"] == "hi"


def test_parse_plaintext_fallback_for_non_json_line():
    (entry,) = manager_logs.parse_entries("-- Reboot --")
    assert entry["message"] == "-- Reboot --"
    assert entry["unit"] == "—"
    assert entry["timestamp"] == ""
    assert entry["priority"] == 6


def test_parse_skips_blank_lines_and_splits_multiple():
    text = "\n".join([_jline(MESSAGE="a"), "", _jline(MESSAGE="b")])
    entries = manager_logs.parse_entries(text)
    assert [e["message"] for e in entries] == ["a", "b"]


def test_parse_empty_text_is_empty_list():
    assert manager_logs.parse_entries("") == []


# --- severity mapping (mockup E coloring language) -------------------------

@pytest.mark.parametrize("prio,sev", [
    (0, "error"), (2, "error"), (3, "error"),
    (4, "warning"),
    (5, "normal"), (6, "normal"),
    (7, "debug"),
])
def test_severity_buckets(prio, sev):
    assert manager_logs.severity(prio) == sev


def test_severity_of_garbage_is_normal():
    assert manager_logs.severity(None) == "normal"
    assert manager_logs.severity("nope") == "normal"


# ===========================================================================
# 3. read_journal — subprocess guards (never raises past the boundary)
# ===========================================================================

class _Fake:
    def __init__(self, stdout=b"", stderr=b"", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_read_journal_success_parses_stdout(monkeypatch):
    captured = {}

    def fake_run(argv, **kw):
        captured["argv"] = argv
        captured["kw"] = kw
        return _Fake(stdout=(_jline(MESSAGE="ok", PRIORITY="6") + "\n").encode())

    monkeypatch.setattr(manager_logs.subprocess, "run", fake_run)
    argv = manager_logs.build_argv("journal")
    (entry,) = manager_logs.read_journal(argv)
    assert entry["message"] == "ok"
    # The binary is a hardcoded literal at the call site, not caller-supplied.
    assert captured["argv"][0] == BIN
    assert "timeout" in captured["kw"]


def test_read_journal_runtime_root_adds_directory_value(monkeypatch):
    captured = {}

    def fake_run(argv, **kw):
        captured["argv"] = argv
        return _Fake()

    monkeypatch.setattr(manager_logs.subprocess, "run", fake_run)
    manager_logs.read_journal(
        manager_logs.build_argv("journal"), runtime_root="/backup/journal")
    assert "--directory=/backup/journal" in captured["argv"]


def test_read_journal_missing_binary_returns_error_entry(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("no journalctl")
    monkeypatch.setattr(manager_logs.subprocess, "run", boom)
    out = manager_logs.read_journal(manager_logs.build_argv("journal"))
    assert len(out) == 1 and "error" in out[0]


def test_read_journal_timeout_returns_error_entry(monkeypatch):
    def slow(*a, **k):
        raise manager_logs.subprocess.TimeoutExpired(cmd=BIN, timeout=1)
    monkeypatch.setattr(manager_logs.subprocess, "run", slow)
    out = manager_logs.read_journal(manager_logs.build_argv("journal"))
    assert len(out) == 1 and "error" in out[0]


def test_read_journal_refuses_non_journalctl_argv(monkeypatch):
    called = []
    monkeypatch.setattr(
        manager_logs.subprocess, "run",
        lambda *a, **k: called.append(1))
    out = manager_logs.read_journal(["/usr/bin/rm", "-rf", "/"])
    assert len(out) == 1 and "error" in out[0]
    assert called == []  # guard fired before any spawn


def test_read_journal_empty_stdout_is_empty_not_error(monkeypatch):
    monkeypatch.setattr(
        manager_logs.subprocess, "run", lambda *a, **k: _Fake(returncode=0))
    assert manager_logs.read_journal(manager_logs.build_argv("journal")) == []


def test_read_journal_nonzero_exit_with_no_output_surfaces_stderr(monkeypatch):
    monkeypatch.setattr(
        manager_logs.subprocess, "run",
        lambda *a, **k: _Fake(stderr=b"Failed to open journal", returncode=1))
    out = manager_logs.read_journal(manager_logs.build_argv("journal"))
    assert len(out) == 1 and "Failed to open journal" in out[0]["error"]
