"""
Resources Page
Phase-1 shell for CPU/memory/network history and sensor chips (concept §4).
Cairo graphs, ring buffers and PSI/temperature/frequency chips arrive in
Phase 5.
"""

from pages.page_base import BasePage


class ResourcesPage(BasePage):
    """Resources page (nav shell placeholder)"""

    def build_content(self):
        """Build page content"""

        self.add_title("Resources")

        self.add_paragraph(
            "Per-core CPU, memory and swap, network history, pressure (PSI) "
            "chips, and temperature/frequency sensors. Graphs land in Phase 5."
        )
