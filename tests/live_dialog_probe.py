#!/usr/bin/env python3
"""Open the kill-confirm dialog and LEAVE the app running (for inspection).
Run under systemd-run so the lifetime is independent of the caller."""
import os
import sys

sys.path.insert(0, "/home/user/projects/linprocman/src")  # systemd-run cwd is $HOME
from ui.compat import GLib  # noqa: E402
from main import LinprocmanApplication  # noqa: E402

app = LinprocmanApplication()


def trigger():
    import subprocess as sp
    victim = sp.Popen(["sleep", "600"])
    page = app.navigation_manager.get_page_widget("processes")
    st = open(f"/proc/{victim.pid}/stat").read()
    tokens = st.split(") ", 1)[1].split()
    page._capture_selection = lambda: [(victim.pid, int(tokens[19]))]
    page._do_signal("kill")
    return False


GLib.timeout_add(3000, trigger)
app.run([])
