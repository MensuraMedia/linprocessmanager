"""
Processes Page
Phase-1 shell for the live process table (concept §4). The table model,
sorting, filtering and details pane arrive in Phase 2 — this is the nav
placeholder so the shell compiles and launches.
"""

from pages.page_base import BasePage


class ProcessesPage(BasePage):
    """Processes page (nav shell placeholder)"""

    def build_content(self):
        """Build page content"""

        self.add_title("Processes")

        self.add_paragraph(
            "Live process table, tree view, filtering and control actions. "
            "This page is a Phase-1 shell; the table lands in Phase 2."
        )
