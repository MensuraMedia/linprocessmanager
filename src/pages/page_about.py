"""
About Page
GTK information, platforms, and adoption
Updated: Removed GTK Resources section
"""

from pages.page_base import BasePage


class AboutPage(BasePage):
    """About page — app identity, license, and project location."""

    def build_content(self):
        """Build about page content."""

        # Page title
        self.add_title("About LinProcessManager")

        # Overview
        self.add_paragraph(
            "LinProcessManager is a native Linux process manager and system "
            "monitor: a live process table with signals, priorities and group "
            "operations, per-app network traffic, disk capacity and I/O, "
            "hardware sensors, and a journal viewer — built on GTK and "
            "Python for the Linux desktop."
        )

        # License section
        self.add_subtitle("License")

        self.add_paragraph(
            "Released under the Creative Commons Attribution-NonCommercial "
            "4.0 International license (CC BY-NC 4.0).\n\n"
            "You are welcome to use, modify, and share this software freely. "
            "Commercial use is not permitted without prior permission from "
            "the author — please reach out to discuss terms. Attribution is "
            "appreciated."
        )

        # Project location
        self.add_subtitle("Project")

        self.add_paragraph(
            "Source and releases: github.com/MensuraMedia/linprocessmanager"
        )

        # Credits
        self.add_subtitle("Built with")

        self.add_paragraph(
            "GTK and PyGObject · Python 3 · the Phosphor icon set (MIT) · "
            "the gtk-python-dashboard-starter framework."
        )
