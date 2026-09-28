#!/usr/bin/env python3
"""Live drive: open the app, click the CPU gauge (its real handler), let the
top-10 popover render, screenshot; then navigate to Basics and screenshot.
Run on :0. Exits after captures."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/lpm-007-drive"
os.makedirs(OUT, exist_ok=True)

from ui.compat import GLib  # noqa: E402
from main import LinprocmanApplication  # noqa: E402

app = LinprocmanApplication()
state = {}


def shot(name):
    path = os.path.join(OUT, name + ".png")
    subprocess.run(["gnome-screenshot", "-f", path],
                   env={**os.environ, "DISPLAY": os.environ.get("WALK_DISPLAY", ":0")},
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return path if os.path.exists(path) else None


def pop_open():
    page = app.navigation_manager.get_page_widget("processes")
    page._on_gauge_pressed("cpu")          # the real gesture handler path
    state["pop"] = shot("cpu-top10")
    return False


def to_basics():
    app.navigation_manager.navigate_to("graphs")
    state["basics"] = shot("graphs-basics")
    GLib.timeout_add(400, app.quit)
    return False


def late():
    state["main"] = shot("processes-band")
    GLib.timeout_add(300, pop_open)
    GLib.timeout_add(1600, to_basics)
    return False


GLib.timeout_add(2500, late)
app.run([])
for k, v in state.items():
    print(k, "->", v, os.path.getsize(v) if v else 0)
sys.exit(0 if all(state.get(k) for k in ("main", "pop", "basics")) else 1)
