"""
Content Area Component
Stack container for pages with individual scroll states
Updated: linprocman nav shell — Processes, Resources, Disks, Logs, About, Settings
"""

from .compat import Gtk, css, layout

from pages.page_processes import ProcessesPage
from pages.page_resources import ResourcesPage
from pages.page_disks import DisksPage
from pages.page_logs import LogsPage
from pages.page_about import AboutPage
from pages.page_settings import SettingsPage


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

        # Create page instances
        processes_page = ProcessesPage()
        resources_page = ResourcesPage()
        disks_page = DisksPage()
        logs_page = LogsPage()
        about_page = AboutPage()
        settings_page = SettingsPage()

        # Wrap each page in its own ScrolledWindow
        processes_scrolled = self.wrap_page_in_scrolled_window(processes_page)
        resources_scrolled = self.wrap_page_in_scrolled_window(resources_page)
        disks_scrolled = self.wrap_page_in_scrolled_window(disks_page)
        logs_scrolled = self.wrap_page_in_scrolled_window(logs_page)
        about_scrolled = self.wrap_page_in_scrolled_window(about_page)
        settings_scrolled = self.wrap_page_in_scrolled_window(settings_page)

        # Add wrapped pages to stack (child name == nav page_id)
        self.stack.add_named(processes_scrolled, "processes")
        self.stack.add_named(resources_scrolled, "resources")
        self.stack.add_named(disks_scrolled, "disks")
        self.stack.add_named(logs_scrolled, "logs")
        self.stack.add_named(about_scrolled, "about")
        self.stack.add_named(settings_scrolled, "settings")

        # Register original pages with navigation manager
        self.nav_manager.register_page("processes", processes_page)
        self.nav_manager.register_page("resources", resources_page)
        self.nav_manager.register_page("disks", disks_page)
        self.nav_manager.register_page("logs", logs_page)
        self.nav_manager.register_page("about", about_page)
        self.nav_manager.register_page("settings", settings_page)

    def show_page(self, page_id):
        """Show a specific page"""
        self.nav_manager.navigate_to(page_id)
