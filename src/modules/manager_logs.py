"""System-journal reader — the logs engine (docs/modules/logs-journal.md).

Core, UI-free, stdlib only. The source of truth is the systemd journal, read
through the **local** ``/usr/bin/journalctl`` binary — no ``python3-systemd``,
no sockets, no network. journalctl is a machine-local executable, so it is
allowed under the offline mandate (build-principles.md §4): the app never opens
a network socket; every datum still comes from the local kernel/journal.

Security boundary (build-principles.md §4, §5; logs-journal.md "subprocess
contract"):

- :func:`build_argv` is a **pure** function returning an argv *list* — never a
  shell string. User input enters exclusively as ``=``-form flag values
  (``--grep=…``, ``--priority=…``, ``--since=…``, ``--until=…``) or field
  matches (``_SYSTEMD_UNIT=…``, ``_UID=…``). A value can therefore never be
  reparsed as a flag (``-D /path``, ``--merge``). Invalid input raises
  ``ValueError`` — a malformed command is never emitted.
- :func:`read_journal` spawns with the argv list and **no shell**. The binary
  is a hardcoded literal at the call site; the caller-supplied ``argv[0]`` is
  validated and then discarded. Every failure (missing binary, timeout, lookup
  error) is caught and returned as an ``{"error": …}`` entry — nothing raises
  past the boundary, so the UI never sees a stack trace or an error dialog.
"""

import json
import os
import subprocess
import time

JOURNALCTL = "/usr/bin/journalctl"

# The four sidebar presets (logs-journal.md). One engine, canned filters.
PRESETS = ("journal", "kernel", "auth", "applications")

# syslog priority names journalctl accepts for --priority=, mapped to level.
PRIORITY_NAMES = {
    "emerg": 0, "alert": 1, "crit": 2, "err": 3,
    "warning": 4, "notice": 5, "info": 6, "debug": 7,
}
DEFAULT_PRIORITY = 6  # info, when a JSON entry carries no PRIORITY field

# Bounded fetch: refuse absurd line counts (logs-journal.md "bounded fetch").
LINES_HARD_CAP = 100000

DEFAULT_TIMEOUT = 6.0

DASH = "—"  # the project's "no data" glyph


# ---------------------------------------------------------------------------
# argv builder (pure)
# ---------------------------------------------------------------------------

def _safe_value(field, value):
    """A user string bound for an ``=``-form value; reject control chars."""
    if not isinstance(value, str):
        raise ValueError("%s must be a string, got %s"
                         % (field, type(value).__name__))
    if "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError("%s contains control characters" % field)
    return value


def _normalize_priority(priority):
    """Return the validated ``--priority=`` value, or raise ``ValueError``.

    Accepts a syslog level name (``err``, ``warning``, …) or an integer 0-7
    (as ``int`` or its plain digit string). Everything else is rejected so the
    value can never smuggle in a flag.
    """
    if isinstance(priority, bool):  # bool is an int subclass — reject early
        raise ValueError("invalid priority: %r" % (priority,))
    if isinstance(priority, int):
        if 0 <= priority <= 7:
            return str(priority)
        raise ValueError("priority out of range: %r" % (priority,))
    if isinstance(priority, str):
        token = priority
        if token in PRIORITY_NAMES:
            return token
        if token.isdigit() and 0 <= int(token) <= 7:
            return token
    raise ValueError("invalid priority: %r" % (priority,))


def build_argv(preset, unit=None, priority=None, since=None, until=None,
               grep=None, lines=500, follow=False):
    """Build the journalctl argv list for a preset + optional filters.

    Pure and side-effect-free (aside from reading the current uid for the
    ``applications`` preset). Returns a list beginning with :data:`JOURNALCTL`;
    invalid input raises ``ValueError`` before any command is formed.
    """
    if preset not in PRESETS:
        raise ValueError("unknown preset: %r" % (preset,))
    if isinstance(lines, bool) or not isinstance(lines, int):
        raise ValueError("lines must be an int: %r" % (lines,))
    if lines <= 0 or lines > LINES_HARD_CAP:
        raise ValueError("lines out of range: %r" % (lines,))

    argv = [JOURNALCTL, "--no-pager", "--output=json"]

    # Preset option flags (matches for `applications` are appended at the end).
    if preset == "kernel":
        argv.append("-k")
    elif preset == "auth":
        argv.append("--facility=auth,authpriv")

    if priority is not None:
        argv.append("--priority=%s" % _normalize_priority(priority))
    if since is not None:
        argv.append("--since=%s" % _safe_value("since", since))
    if until is not None:
        argv.append("--until=%s" % _safe_value("until", until))

    argv.append("--lines=%d" % lines)

    if follow:
        argv.append("--follow")
    if grep is not None:
        argv.append("--grep=%s" % _safe_value("grep", grep))

    # Field matches go last (journalctl convention: matches follow options).
    if preset == "applications":
        argv.append("_UID=%d" % os.getuid())
    if unit is not None:
        argv.append("_SYSTEMD_UNIT=%s" % _safe_value("unit", unit))

    return argv


# ---------------------------------------------------------------------------
# parse (pure) — JSON fields with a plaintext fallback
# ---------------------------------------------------------------------------

def _fmt_ts(raw):
    """``__REALTIME_TIMESTAMP`` microseconds -> local ``HH:MM:SS`` string."""
    if raw is None:
        return ""
    try:
        micros = int(raw)
    except (TypeError, ValueError):
        return ""
    return time.strftime("%H:%M:%S", time.localtime(micros / 1_000_000))


def _coerce_priority(raw):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_PRIORITY
    return value if 0 <= value <= 7 else DEFAULT_PRIORITY


def _coerce_unit(obj):
    for key in ("_SYSTEMD_UNIT", "SYSLOG_IDENTIFIER", "_COMM"):
        value = obj.get(key)
        if value:
            return value
    return DASH


def _coerce_message(raw):
    if raw is None:
        return ""
    if isinstance(raw, list):  # journal stores non-UTF8 MESSAGE as byte array
        try:
            return bytes(raw).decode("utf-8", errors="replace")
        except (TypeError, ValueError):
            return ""
    return str(raw)


def _parse_line(line):
    try:
        obj = json.loads(line)
    except (ValueError, TypeError):
        obj = None
    if not isinstance(obj, dict):
        # Plaintext fallback: the whole line is the message.
        return {"timestamp": "", "priority": DEFAULT_PRIORITY,
                "unit": DASH, "message": line}
    return {
        "timestamp": _fmt_ts(obj.get("__REALTIME_TIMESTAMP")),
        "priority": _coerce_priority(obj.get("PRIORITY")),
        "unit": _coerce_unit(obj),
        "message": _coerce_message(obj.get("MESSAGE")),
    }


def parse_entries(text):
    """Parse journalctl output into structured entries.

    One ``--output=json`` object per line; a line that is not valid JSON falls
    back to a plaintext message (journalctl prints ``-- Reboot --`` markers and
    some sources emit bare text). Blank lines are skipped.
    """
    entries = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            entries.append(_parse_line(stripped))
    return entries


def severity(priority):
    """Map a priority level to a coloring bucket (mockup E language).

    ``error`` (emerg..err, red), ``warning`` (amber), ``debug`` (dimmed), or
    ``normal`` (notice/info, default). Garbage -> ``normal``.
    """
    try:
        level = int(priority)
    except (TypeError, ValueError):
        return "normal"
    if level <= 3:
        return "error"
    if level == 4:
        return "warning"
    if level >= 7:
        return "debug"
    return "normal"


# ---------------------------------------------------------------------------
# read_journal (the subprocess boundary)
# ---------------------------------------------------------------------------

def read_journal(argv, runtime_root=None, timeout=DEFAULT_TIMEOUT):
    """Run journalctl with ``argv`` and return parsed entries.

    ``argv`` is a list as returned by :func:`build_argv`. The binary is a
    hardcoded literal at the spawn site — ``argv[0]`` is only validated (must
    name journalctl) and then dropped, so no caller can redirect the spawn.
    ``runtime_root`` (optional) reads a journal from a specific directory via
    ``--directory=`` (e.g. a backup or mounted journal).

    Never raises past the boundary: a missing binary, timeout, or nonzero exit
    with no output all come back as a single ``{"error": …}`` entry. An empty
    journal returns ``[]`` (empty state), never an error.
    """
    if not isinstance(argv, (list, tuple)) or not argv:
        return [{"error": "empty journalctl argv"}]
    if os.path.basename(str(argv[0])) != "journalctl":
        return [{"error": "refusing to run non-journalctl argv"}]

    tail = list(argv[1:])
    if runtime_root:
        tail = ["--directory=%s" % runtime_root] + tail

    try:
        # The binary is a string LITERAL here (not the JOURNALCTL constant) so
        # the subprocess-argv gate can statically prove the spawn target; the
        # variable `tail` only ever contributes `=`-form values / field matches.
        completed = subprocess.run(
            ["/usr/bin/journalctl", *tail],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, check=False,
        )
    except FileNotFoundError:
        return [{"error": "journalctl not found (%s)" % JOURNALCTL}]
    except subprocess.TimeoutExpired:
        return [{"error": "journalctl timed out after %gs" % timeout}]
    except (OSError, ProcessLookupError) as exc:  # spawn/reap failure
        return [{"error": "journalctl failed: %s" % exc}]

    stdout = completed.stdout or b""
    text = stdout.decode("utf-8", errors="replace")
    entries = parse_entries(text)
    if not entries and completed.returncode not in (0, None):
        stderr = (completed.stderr or b"").decode("utf-8", errors="replace")
        message = stderr.strip() or ("journalctl exited %s"
                                     % completed.returncode)
        return [{"error": message}]
    return entries
