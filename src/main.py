#!/usr/bin/env python3
"""
linprocman — native Linux GTK process manager
Main application entry point: Gtk.Application lifecycle (gtk4-port.md §4.1,
upgrade-architecture.md §2 app layer). Toolkit symbols come from the compat
seam, never from gi.repository directly.
"""

import sys

from ui.compat import Gtk

from ui.dashboard_window import DashboardWindow
from modules.manager_navigation import NavigationManager
from modules.manager_theme_applicator import ThemeApplicator
from modules.manager_sampler import Sampler
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
        if self.window is None:
            # Apply default theme now that a display is available.
            self.theme_applicator.apply_theme(get_theme('default'))
            self.window = DashboardWindow(
                self.navigation_manager, sampler=self.sampler, application=self
            )
            self.window.show_all()
        self.sampler.start()
        self.window.present()

    def _on_shutdown(self, _app):
        """Stop the sampler thread cleanly on application shutdown."""
        self.sampler.stop(timeout=2.0)


def main():
    """Main application entry point"""
    app = LinprocmanApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
