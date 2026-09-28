"""
Sidebar Component
Fixed sidebar with logo and navigation
Updated: Home button has top border, Settings has top border
"""

from .compat import Gtk, GObject, css, icons, layout
from . import branding

from config.config_layout import Layout
from log import get_logger
log = get_logger("sidebar")


# Top-level navigation entries (label, page_id, is_top). Module-level so the
# retirement of Resources / arrival of Graphs (r061) is assertable headlessly.
# Graphs sits between Processes and Disks and supersedes the old Resources page.
NAV_ITEMS = [
    ("Processes", "processes", True),   # first item gets top border
    ("Graphs", "graphs", False),        # navigates to the hub (Basics on top)
    ("Disks", "disks", False),
    ("Peripherals", "peripherals", False),   # r092: connected devices + sensors
    ("Logs", "logs", False),
    ("About", "about", False),
]

# r092: the Graphs submenu (Basics child) is RETIRED — the Basics cards
# live at the top of the Graphs hub page and the sidebar is flat.
class Sidebar(Gtk.Box):
    """Fixed sidebar with logo and navigation buttons"""
    
    __gsignals__ = {
        'page-changed': (GObject.SignalFlags.RUN_FIRST, None, (str,))
    }
    
    def __init__(self, navigation_manager):
        """Initialize sidebar"""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        self.nav_manager = navigation_manager
        
        self.set_size_request(Layout.dimensions.SIDEBAR_WIDTH, -1)
        css.add_css_class(self, 'sidebar')
        
        self.active_button = None
        
        self.build_logo_area()
        self.build_navigation()
        
        if "processes" in self.nav_buttons:
            self.set_active_button(self.nav_buttons["processes"])
            self.nav_manager.navigate_to("processes")
    
    def build_logo_area(self):
        """Build logo area"""

        logo_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        logo_box.set_size_request(
            Layout.dimensions.LOGO_AREA_WIDTH,
            Layout.dimensions.LOGO_AREA_HEIGHT
        )
        css.add_css_class(logo_box, 'logo-area')

        # r082: the mark is owned by the branding module (one source for
        # sidebar / tray / ALT+Tab / menu); PNG first, SVG fallback, then
        # the text fallback.
        pixbuf = branding.logo_pixbuf(Layout.dimensions.LOGO_IMAGE_SIZE)
        if pixbuf is not None:
            layout.box_add(logo_box, icons.image_from_pixbuf(pixbuf),
                           True, True, 0)
        else:
            self.add_fallback_logo(logo_box)

        layout.box_add(self, logo_box, False, False, 0)
    
    def add_fallback_logo(self, container):
        """Add fallback logo text"""
        logo_label = Gtk.Label(label="LINPROCMAN")
        css.add_css_class(logo_label, 'logo-text')
        logo_label.set_xalign(0.5)
        layout.box_add(container, logo_label, True, True, 0)
    
    def build_navigation(self):
        """Build navigation area with Home and Settings having special borders"""
        
        # Top navigation container
        nav_box_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        # Main navigation items (linprocman nav shell) — see module NAV_ITEMS.
        # r092 (operator): the submenu experiment is RETIRED — no Basics
        # child, no caret on Graphs; the Basics cards live at the top of
        # the Graphs hub page.
        self.nav_buttons = {}
        for label, page_id, is_top in NAV_ITEMS:
            button = self.create_nav_button(label, page_id, is_top=is_top)
            layout.box_add(nav_box_top, button, False, False, 0)
            self.nav_buttons[page_id] = button

        # Add top navigation
        layout.box_add(self, nav_box_top, False, False, 0)

        # Add expanding spacer to push Settings to bottom
        spacer = Gtk.Box()
        layout.box_add(self, spacer, True, True, 0)

        # Bottom navigation container for Settings
        nav_box_bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Settings button with bottom styling (top border)
        settings_button = self.create_nav_button("Settings", "settings", is_bottom=True)
        layout.box_add(nav_box_bottom, settings_button, False, False, 0)
        self.nav_buttons["settings"] = settings_button

        # Add bottom navigation
        layout.box_add(self, nav_box_bottom, False, False, 0)
    
    def create_nav_button(self, label, page_id, is_top=False, is_bottom=False,
                          indent=False, is_group=False):
        """
        Create navigation button

        Args:
            label: Button label text
            page_id: Page identifier for navigation
            is_top: If True, applies top button styling (Home)
            is_bottom: If True, applies bottom button styling (Settings)
            indent: If True, submenu child styling (r062)

        Returns:
            Gtk.Button: Configured navigation button
        """
        button = Gtk.Button()
        if is_group:
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            lbl = Gtk.Label(label=label, xalign=0)
            # r080: NO set_hexpand here. GTK3 propagates a child's hexpand up
            # every ancestor, so the Sidebar itself became expansion-hungry:
            # the window's spare width was handed to the 171px sidebar, which
            # then floated centered (dead strips both flanks, table squeezed
            # to 537px). The pack flags below already expand the label within
            # the button — nothing else is needed.
            layout.box_add(hbox, lbl, True, True, 0)
            layout.set_child(button, hbox)  # GTK3 add / GTK4 set_child
        else:
            button.set_label(label)
        css.add_css_class(button, 'nav-button')
        if indent:
            css.add_css_class(button, 'nav-sub')

        # Add special class for top button (Home)
        if is_top:
            css.add_css_class(button, 'nav-button-top')

        # Add special class for bottom button (Settings)
        if is_bottom:
            css.add_css_class(button, 'nav-button-bottom')
        
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.connect("clicked", self.on_nav_clicked, page_id)
        
        button_label = button.get_child()
        if hasattr(button_label, "set_xalign"):  # HBox children pre-aligned
            button_label.set_xalign(0)
        
        return button
    
    def set_active_button(self, button):
        """Set button as active"""
        if self.active_button:
            css.remove_css_class(self.active_button, 'active')

        css.add_css_class(button, 'active')
        self.active_button = button
    
    def on_navigated(self, page_id):
        """r081: navigation-manager hook for ALL navigation paths — moves
        the active highlight (programmatic navigation used to leave the
        sidebar unhighlighted)."""
        button = self.nav_buttons.get(page_id)
        if button is not None:
            self.set_active_button(button)

    def on_nav_clicked(self, button, page_id):
        """Handle navigation click"""
        self.set_active_button(button)
        self.nav_manager.navigate_to(page_id)
        self.emit('page-changed', page_id)
