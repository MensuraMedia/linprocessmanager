"""
Disks Page
Phase-1 shell for per-device I/O rates and per-mount usage (concept §4).
The diskstats-backed rates and mount table arrive in Phase 6.
"""

from pages.page_base import BasePage


class DisksPage(BasePage):
    """Disks page (nav shell placeholder)"""

    def build_content(self):
        """Build page content"""

        self.add_title("Disks")

        self.add_paragraph(
            "Per-device read/write rates and per-mount usage, with live plug "
            "events. This page is a Phase-1 shell; the tables land in Phase 6."
        )
