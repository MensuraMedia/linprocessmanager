"""
Content Area Component
Stack container for pages with individual scroll states
Updated: linprocman nav shell — Processes, Graphs (+ detail pages), Disks, Logs,
Basics, About, Settings. Resources retired in favour of the Graphs hub (r061).
"""

from .compat import Gtk, css, layout

from pages.page_processes import ProcessesPage
from pages.page_graphs import GraphsHubPage
from pages import graph_details as gd
from pages.page_disks import DisksPage
from pages.page_logs import LogsPage
from pages.page_basics import BasicsPage
from pages.page_peripherals import PeripheralsPage
from pages.page_about import AboutPage
from pages.page_settings import SettingsPage

from modules import manager_history


class ContentArea(Gtk.Box):
    """Content area with page navigation and individual scroll states"""

    def __init__(self, navigation_manager):
        """Initialize content area"""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self.nav_manager = navigation_manager

        # Style class for content area
        css.add_css_class(self, 'content-area')

        # Create stack for pages - NO transitions
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        layout.box_add(self, self.stack, True, True, 0)

        # Register stack with navigation manager
        self.nav_manager.set_page_stack(self.stack)

        # Register pages
        self.register_pages()

    def wrap_page_in_scrolled_window(self, page):
        """
        Wrap a page in its own ScrolledWindow
        This ensures each page maintains its own scroll state

        Args:
            page: Page widget to wrap

        Returns:
            Gtk.ScrolledWindow containing the page
        """
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        layout.set_child(scrolled_window, page)
        return scrolled_window

    def register_pages(self):
        """Register all application pages with individual scroll states"""

        # The shared history ring store (Phase 5). One writer, fed on the
        # Processes-page drain thread; every graph/basics surface reads it.
        self.history = manager_history.History()

        # Create page instances
        processes_page = ProcessesPage()
        graphs_page = GraphsHubPage()
        # Graphs ▸ X detail pages, one per DetailSpec (sub-pages of the hub).
        detail_pages = [(spec.page_id, gd.GraphDetailPage(spec))
                        for spec in gd.DETAIL_SPECS]
        disks_page = DisksPage()
        peripherals_page = PeripheralsPage()
        logs_page = LogsPage()
        basics_page = BasicsPage()
        # r092 (operator): Basics is no longer its own page — the cards live
        # at the top of the Graphs hub (submenu retired).
        graphs_page.add_basics_section(basics_page)
        about_page = AboutPage()
        settings_page = SettingsPage()

        # Register the top-level + hub pages in stack order (child name ==
        # nav page_id). Detail pages are stacked too, reachable via the hub.
        top_pages = [
            ("processes", processes_page),
            ("graphs", graphs_page),
            ("disks", disks_page),
            ("peripherals", peripherals_page),
            ("logs", logs_page),
            ("about", about_page),
            ("settings", settings_page),
        ]
        for page_id, page in top_pages + detail_pages:
            scrolled = self.wrap_page_in_scrolled_window(page)
            self.stack.add_named(scrolled, page_id)
            self.nav_manager.register_page(page_id, page)

        # Single-drain law (r046): the Processes page owns the one sampler
        # drain and forwards every snapshot to observers. Register the history
        # writer FIRST so pages read populated rings on the same tick.
        graph_observers = [basics_page.on_snapshot, graphs_page.on_snapshot]
        graph_observers += [page.on_snapshot for _pid, page in detail_pages]
        if hasattr(processes_page, "add_snapshot_observer"):
            processes_page.add_snapshot_observer(
                lambda snap: manager_history.record(self.history, snap))
            for observer in graph_observers:
                processes_page.add_snapshot_observer(observer)

        # Inject the shared rings into every reader.
        basics_page.set_history(self.history)
        graphs_page.set_history(self.history)
        for _pid, page in detail_pages:
            page.set_history(self.history)

        def _jump_to_process(key):
            self.nav_manager.navigate_to("processes")
            processes_page.select_process(key)

        def _navigate(page_id):
            self.nav_manager.navigate_to(page_id)

        # Contributor clicks jump to Processes; hub/detail navigation moves
        # between the hub and its detail pages.
        basics_page.set_jump_callback(_jump_to_process)
        graphs_page.set_navigate(_navigate)
        for _pid, page in detail_pages:
            page.set_navigate(_navigate)
            page.set_jump_callback(_jump_to_process)

    def show_page(self, page_id):
        """Show a specific page"""
        self.nav_manager.navigate_to(page_id)
