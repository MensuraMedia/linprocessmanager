#!/usr/bin/env python3
"""Live GUI walk for linprocman — run ON :0, never under pytest.

Drives the REAL application through its own navigation code path (the same
NavigationManager.navigate_to the sidebar buttons invoke), screenshots every
page, prints a PASS/FAIL line per page, and exits.

Usage: DISPLAY=:0 python3 tests/live_gui_walk.py [outdir]
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/lpm-walk"
os.makedirs(OUT, exist_ok=True)

from ui.compat import GLib, Gtk  # noqa: E402

from main import LinprocmanApplication  # noqa: E402

PAGES = ["processes", "resources", "disks", "logs", "about", "settings"]
results = {}
# LIVE marker: minimum real process rows the table must show on this machine.
MIN_LIVE_ROWS = 10
live = {"rows": None}
app = LinprocmanApplication()


def keep_above():
    """Force the window above others so screenshots capture it, not the desk."""
    if app.window is not None:
        app.window.set_keep_above(True)
    return False


def count_live_rows():
    """LIVE check: count visible rows in the Processes model after warm-up.

    Reads the filter model the page installed (kernel threads hidden by
    default) — proof the sampler → diff-in-place path put REAL rows on screen,
    not just that a window appeared.
    """
    page = app.navigation_manager.get_page_widget("processes")
    count = 0
    if page is not None and getattr(page, "model", None) is not None:
        model = page.model.filter
        it = model.get_iter_first()
        while it is not None:
            count += 1
            it = model.iter_next(it)
    live["rows"] = count
    return False


def shot(name):
    path = os.path.join(OUT, name + ".png")
    env = {**os.environ, "DISPLAY": os.environ.get("WALK_DISPLAY", ":0")}
    subprocess.run(["gnome-screenshot", "-f", path], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ok = os.path.exists(path) and os.path.getsize(path) > 10000
    return path if ok else None


def capture(page, nav_ok):
    results[page] = (nav_ok, shot(page))
    if page == PAGES[-1]:
        GLib.timeout_add(800, app.quit)
    return False


def step(i):
    page = PAGES[i]
    nav_ok = app.navigation_manager.navigate_to(page)
    GLib.timeout_add(450, capture, page, nav_ok)
    return False


GLib.timeout_add(300, keep_above)
# Count live rows ~2 s in (several sampler drains have landed by then).
GLib.timeout_add(2000, count_live_rows)

for i in range(len(PAGES)):
    GLib.timeout_add(1500 + 1300 * i, step, i)

exit_code = app.run([])

fails = 0
for page in PAGES:
    nav_ok, path = results.get(page, (False, None))
    status = "PASS" if (nav_ok and path) else "FAIL"
    if status == "FAIL":
        fails += 1
    print(f"{status} {page} nav={nav_ok} shot={path}")

rows = live["rows"]
rows_ok = rows is not None and rows >= MIN_LIVE_ROWS
print(f"{'PASS' if rows_ok else 'FAIL'} [live] process-rows={rows} "
      f"(need >= {MIN_LIVE_ROWS})")
if not rows_ok:
    fails += 1
print(f"--- {len(PAGES) - fails}/{len(PAGES) + 1} checks passed")
sys.exit(1 if fails else 0)
