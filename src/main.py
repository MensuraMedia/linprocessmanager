#!/usr/bin/env python3
"""
linprocman — native Linux GTK process manager
Main application entry point: Gtk.Application lifecycle (gtk4-port.md §4.1,
upgrade-architecture.md §2 app layer). Toolkit symbols come from the compat
seam, never from gi.repository directly.
"""

import sys

from log import setup_logging, log_exception, get_logger

setup_logging()  # r064: native logging first, so everything after this
                 # lands in ~/.local/state/linprocman/

from ui.compat import Gtk, GLib

from ui.dashboard_window import DashboardWindow
from modules.manager_navigation import NavigationManager
from modules.manager_theme_applicator import ThemeApplicator
from modules.manager_sampler import Sampler
from modules import manager_baseline
from config.config_themes import get_theme


class LinprocmanApplication(Gtk.Application):
    """Application controller — owns lifecycle and the single main window."""

    def __init__(self):
        super().__init__(application_id="io.github.linprocman")
        self.navigation_manager = NavigationManager()
        self.theme_applicator = ThemeApplicator()
        # The GLib-free sampler is owned here; the Processes page installs the
        # single idle source that drains it (r046). Started on activate,
        # stopped on shutdown.
        self.sampler = Sampler()
        self.window = None
        self.connect("shutdown", self._on_shutdown)

    def do_activate(self):
        """Build (once) and present the main window; run the sampler."""
        try:
            self._do_activate()
        except Exception as e:
            from log import get_logger
            get_logger("app").error("%s", log_exception("do_activate", e))
            raise

    def _do_activate(self):
        if self.window is None:
            # Apply default theme now that a display is available.
            self.theme_applicator.apply_theme(get_theme('default'))
            self.window = DashboardWindow(
                self.navigation_manager, sampler=self.sampler, application=self
            )
            self.window.show_all()
        self.window.present()
        # r071: baseline loads/applies off the UI thread — the ~6 s idle
        # sampling must never freeze the first launch.
        GLib.timeout_add(200, self._ensure_baseline)
        # r058 close-review P2-7: honor the page's pause state across
        # re-activation — never silently restart a paused sampler.
        page = self.navigation_manager.get_page_widget("processes")
        if page is None or not getattr(page, "_paused", False):
            self.sampler.start()

    def _ensure_baseline(self):
        """Apply the stored baseline, or capture one in a background thread
        on first run (r071; adversarial P0-2 + P1-2 fixes)."""
        import threading
        page = self.navigation_manager.get_page_widget("processes")
        if page is None or getattr(page, "settings", None) is None:
            return False
        baseline = page.settings.get("baseline")
        if baseline and baseline.get("thresholds"):
            page.set_thresholds(
                manager_baseline.Thresholds(baseline["thresholds"]))
            log.info("baseline applied (stored)")
            return False  # one-shot
        def work():
            specs, thresholds = manager_baseline.capture()
            def apply():
                try:
                    page.settings.set("baseline", {
                        "specs": specs, "thresholds": thresholds,
                        "schema": manager_baseline.SCHEMA})
                    page.settings.save()
                    page.set_thresholds(
                        manager_baseline.Thresholds(thresholds))
                    log.info("baseline captured: %s", thresholds)
                except Exception as e:
                    from log import get_logger
                    get_logger("baseline").error(
                        "%s", log_exception("baseline apply", e))
            GLib.idle_add(apply)
        threading.Thread(target=work, daemon=True).start()
        return False

    def _on_shutdown(self, _app):
        """Stop the sampler thread cleanly on application shutdown."""
        self.sampler.stop(timeout=2.0)


def main():
    """Main application entry point"""
    app = LinprocmanApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
