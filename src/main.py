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
from config.config_themes import get_theme


class LinprocmanApplication(Gtk.Application):
    """Application controller — owns lifecycle and the single main window."""

    def __init__(self):
        super().__init__(application_id="io.github.linprocman")
        self.navigation_manager = NavigationManager()
        self.theme_applicator = ThemeApplicator()
        self.window = None

    def do_activate(self):
        """Build (once) and present the main window."""
        if self.window is None:
            # Apply default theme now that a display is available.
            self.theme_applicator.apply_theme(get_theme('default'))
            self.window = DashboardWindow(
                self.navigation_manager, application=self
            )
        self.window.present()


def main():
    """Main application entry point"""
    app = LinprocmanApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
