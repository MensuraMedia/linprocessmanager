"""
Main Dashboard Window
Main application window — Gtk.ApplicationWindow under the Gtk.Application
lifecycle (upgrade-architecture.md §2 app layer; gtk4-port.md §4.1).
"""

from .compat import Gtk, Gdk, layout

from ui.sidebar import Sidebar
from ui.content_area import ContentArea
from config.config_layout import Layout


class DashboardWindow(Gtk.ApplicationWindow):
    """Main application window"""

    def __init__(self, navigation_manager, sampler=None, application=None):
        """Initialize window"""
        super().__init__(application=application, title="linprocman")

        self.nav_manager = navigation_manager
        self.sampler = sampler
        self._iconified = False

        self.set_default_size(
            Layout.dimensions.WINDOW_DEFAULT_WIDTH,
            Layout.dimensions.WINDOW_DEFAULT_HEIGHT
        )
        self.set_position(Gtk.WindowPosition.CENTER)

        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        layout.set_child(self, main_box)

        self.sidebar = Sidebar(self.nav_manager)
        self.sidebar.connect("page-changed", self.on_page_changed)
        # r081: watch the navigation manager once, at construction — moves
        # the active highlight and expands the destination's parent group
        # for EVERY navigation path (programmatic navigation used to leave
        # the sidebar unhighlighted).
        self.nav_manager.on_navigate(self.sidebar.on_navigated)
        layout.box_add(main_box, self.sidebar, False, False, 0)

        self.content_area = ContentArea(self.nav_manager)
        layout.box_add(main_box, self.content_area, True, True, 0)

        # Hand the sampler to the Processes page (ContentArea is out of scope,
        # so reach the page through the navigation registry it populated).
        if self.sampler is not None:
            page = self.nav_manager.get_page_widget("processes")
            if page is not None and hasattr(page, "attach_sampler"):
                page.attach_sampler(self.sampler, self.get_application())
            # Inject window activity/iconified state (sampler backoff input);
            # the sampler never reads GTK itself (r046).
            self.connect("notify::is-active", self._on_activity_changed)
            self.connect("window-state-event", self._on_window_state)
            self._push_activity()

    def on_page_changed(self, sidebar, page_name):
        """Handle page change"""
        self.content_area.show_page(page_name)
        # highlight + group expansion live in the nav_manager.on_navigate
        # hook (sidebar.on_navigated) — it covers every navigation path.

    def _on_activity_changed(self, *_args):
        self._push_activity()

    def _on_window_state(self, _widget, event):
        self._iconified = bool(event.new_window_state & Gdk.WindowState.ICONIFIED)
        self._push_activity()
        return False

    def _push_activity(self):
        if self.sampler is not None:
            self.sampler.set_activity_state(self.is_active(), self._iconified)
