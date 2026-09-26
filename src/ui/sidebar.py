"""
Sidebar Component
Fixed sidebar with logo and navigation
Updated: Home button has top border, Settings has top border
"""

from .compat import Gtk, GdkPixbuf, GObject, css, icons, layout
import os

from config.config_layout import Layout


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

        logo_image = None
        for logo_path in self.get_logo_paths():
            if not os.path.exists(logo_path):
                continue
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    logo_path,
                    Layout.dimensions.LOGO_IMAGE_SIZE,
                    Layout.dimensions.LOGO_IMAGE_SIZE,
                    True
                )
                logo_image = icons.image_from_pixbuf(pixbuf)
                break
            except Exception as e:
                print(f"logo candidate failed ({logo_path}): {e}")
        if logo_image is not None:
            layout.box_add(logo_box, logo_image, True, True, 0)
        else:
            self.add_fallback_logo(logo_box)

        layout.box_add(self, logo_box, False, False, 0)
    
    def get_logo_paths(self):
        """Logo candidates in preference order (r054 adversarial fix: svg needs
        the optional librsvg pixbuf loader — fall through to png, then text)."""
        base = os.path.join(os.path.dirname(__file__), '..', '..', 'resources', 'images')
        return [os.path.join(base, 'logo.svg'), os.path.join(base, 'logo.png')]
    
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
        
        # Main navigation items (linprocman nav shell)
        nav_items = [
            ("Processes", "processes", True),   # first item gets top border
            ("Resources", "resources", False),
            ("Disks", "disks", False),
            ("Logs", "logs", False),
            ("About", "about", False)
        ]
        
        self.nav_buttons = {}
        for label, page_id, is_top in nav_items:
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
    
    def create_nav_button(self, label, page_id, is_top=False, is_bottom=False):
        """
        Create navigation button
        
        Args:
            label: Button label text
            page_id: Page identifier for navigation
            is_top: If True, applies top button styling (Home)
            is_bottom: If True, applies bottom button styling (Settings)
        
        Returns:
            Gtk.Button: Configured navigation button
        """
        button = Gtk.Button(label=label)
        css.add_css_class(button, 'nav-button')

        # Add special class for top button (Home)
        if is_top:
            css.add_css_class(button, 'nav-button-top')

        # Add special class for bottom button (Settings)
        if is_bottom:
            css.add_css_class(button, 'nav-button-bottom')
        
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.connect("clicked", self.on_nav_clicked, page_id)
        
        button_label = button.get_child()
        button_label.set_xalign(0)
        
        return button
    
    def set_active_button(self, button):
        """Set button as active"""
        if self.active_button:
            css.remove_css_class(self.active_button, 'active')

        css.add_css_class(button, 'active')
        self.active_button = button
    
    def on_nav_clicked(self, button, page_id):
        """Handle navigation click"""
        self.set_active_button(button)
        self.nav_manager.navigate_to(page_id)
        self.emit('page-changed', page_id)
