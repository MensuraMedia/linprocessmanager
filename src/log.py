#!/usr/bin/env python3
"""Application logging bootstrap (r064).

Native, offline logging for linprocman. Design:

- ``logging`` stdlib only — no new dependency, mandate-safe.
- One file handler writing to ``~/.local/state/linprocman/log`` (XDG state
  dir; created on demand) with 1 MiB rotation × 3 backups, so issues
  survive restarts and can be triaged into the backlog.
- A copy of warnings/errors also goes to stderr so `journalctl --user -u
  linprocman-app` keeps working for the systemd unit (severity-routing:
  INFO+ to file, WARNING+ to stderr).
- ``log_exception()`` records a traceback AND appends a one-line entry to
  the in-repo issues ledger (``.zcode/memory/issues.md`` when running from
  a checkout; file-not-found is swallowed — installed runs just log).

Usage (import once at the top of src/main.py, before other imports):
    from log import setup_logging, log_exception, log
    setup_logging()
"""
import logging
import logging.handlers
import os
import sys
import traceback
from datetime import datetime

_LOG = None
_ISSUES_PATH = None


def _state_dir():
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "linprocman")


def _issues_path():
    """Issues ledger lives in the checkout when available (dev/agent runs)."""
    global _ISSUES_PATH
    if _ISSUES_PATH is None:
        here = os.path.dirname(os.path.abspath(__file__))  # src/
        root = os.path.dirname(here)
        candidate = os.path.join(root, ".zcode", "memory", "issues.md")
        _ISSUES_PATH = candidate if os.path.isdir(os.path.dirname(candidate)) else ""
    return _ISSUES_PATH


def setup_logging(level=logging.INFO):
    """Idempotent logging bootstrap. Returns the application logger."""
    global _LOG
    if _LOG is not None:
        return _LOG

    log_dir = _state_dir()
    os.makedirs(log_dir, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")

    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "linprocman.log"),
        maxBytes=1_000_000, backupCount=3)
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)  # journal sees problems only
    stderr_handler.setFormatter(fmt)

    root = logging.getLogger("linprocman")
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(stderr_handler)
    root.propagate = False

    # Third-party/GLib noise stays out of our file unless warning+.
    logging.getLogger("gi").setLevel(logging.WARNING)
    _LOG = root
    root.info("logging initialised (%s)", os.path.join(log_dir, "linprocman.log"))
    return root


def get_logger(name):
    """Child logger under the application namespace."""
    return logging.getLogger("linprocman." + name)


def log_exception(context, exc=None):
    """Record an exception: full traceback to the log file, one-line issue
    entry appended to the in-repo issues ledger for backlog triage."""
    log = _LOG or setup_logging()
    if exc is None:
        exc = sys.exc_info()[1]
    tb = "".join(traceback.format_exception(
        type(exc), exc, exc.__traceback__)).rstrip() if exc else "n/a"
    log.error("EXCEPTION in %s: %s\n%s", context,
              f"{type(exc).__name__}: {exc}" if exc else "?", tb)

    path = _issues_path()
    if path:
        first_line = (str(exc).strip().splitlines() or ["?"])[0][:160]
        try:
            with open(path, "a") as f:
                stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                f.write(f"- {stamp} | {context} | {type(exc).__name__}: "
                        f"{first_line}\n")
        except OSError:
            pass  # ledger is best-effort; the log file is the record
    return f"{type(exc).__name__} in {context}: {first_line}" \
        if path else f"{type(exc).__name__} in {context}"


def issue(text):
    """Record a non-exception issue/observation for backlog triage."""
    path = _issues_path()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    (_LOG or setup_logging()).warning("issue: %s", text)
    if path:
        try:
            with open(path, "a") as f:
                f.write(f"- {stamp} | note | {text[:200]}\n")
        except OSError:
            pass
