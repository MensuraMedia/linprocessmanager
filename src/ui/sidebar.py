"""
Sidebar Component
Fixed sidebar with logo and navigation
Updated: Home button has top border, Settings has top border
"""

from .compat import Gtk, GdkPixbuf, GObject, css, icons, layout, events
import os

from config.config_layout import Layout
from log import get_logger
log = get_logger("sidebar")


# Top-level navigation entries (label, page_id, is_top). Module-level so the
# retirement of Resources / arrival of Graphs (r061) is assertable headlessly.
# Graphs sits between Processes and Disks and supersedes the old Resources page.
NAV_ITEMS = [
    ("Processes", "processes", True),   # first item gets top border
    ("Graphs", "graphs", False),        # group: navigates to the hub
    ("Disks", "disks", False),
    ("Logs", "logs", False),
    ("About", "about", False),
]

# r062: Graphs carries a submenu (indented children, one level deep).
# Basics moved here per operator instruction — the standalone button is gone.
SUBMENUS = {
    "graphs": [
        ("Basics", "basics"),
    ],
}


class Sidebar(Gtk.Box):
    """Fixed sidebar with logo and navigation buttons"""
    
    __gsignals__ = {
        'page-changed': (GObject.SignalFlags.RUN_FIRST, None, (str,))
    }
    
    def __init__(self, navigation_manager):
        """Initialize sidebar"""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        self.nav_manager = navigation_manager
        self.submenus = {}
        self.submenu_boxes = {}
        
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
                log.exception(f"logo candidate failed ({logo_path}): {e}")
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
        
        # Main navigation items (linprocman nav shell) — see module NAV_ITEMS.
        self.nav_buttons = {}
        for label, page_id, is_top in NAV_ITEMS:
            button = self.create_nav_button(label, page_id, is_top=is_top,
                                            is_group=True)
            children = SUBMENUS.get(page_id)
            if children:
                # r073: collapsible group — expands DOWNWARD, caret rotates;
                # clicking the group navigates to the hub and expands.
                css.add_css_class(button, "nav-group")
                # r075: pixbuf-at-size — Gtk.Image.set_pixel_size does not
                # scale SVG-file images here (the logo path proves the API)
                caret_pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "..", "resources", "icons", "regular",
                                 "caret-right.svg"), 11, 11)
                caret = Gtk.Image.new_from_pixbuf(caret_pixbuf)
                caret.set_halign(Gtk.Align.END)
                css.add_css_class(caret, "nav-caret")
                # r075: group buttons carry an HBox child so the caret can
                # sit RIGHT-ALIGNED as a persistent submenu indicator (the
                # label-only child silently dropped it — r073 defect).
                gbox = button.get_child()  # HBox from is_group=True
                # r081: the caret is the expand/collapse TOGGLE — click it
                # to expand the children downward or contract them upward
                # without navigating. press_swallow (compat seam) STOPS the
                # press at the EventBox: a real-event test proved the plain
                # gesture route still activated the group button (the click
                # toggled AND navigated — cross-review P2-1).
                toggle = Gtk.EventBox(above_child=True)
                layout.set_child(toggle, caret)
                gesture = events.press_swallow(
                    toggle, lambda x, y, pid=page_id:
                        self._on_caret_toggle(pid), button=1)
                layout.box_add(gbox, toggle, False, False, 0)
                self.submenus[page_id] = {"caret": caret, "gesture": gesture,
                                          "children": []}
                layout.box_add(nav_box_top, button, False, False, 0)
                self.nav_buttons[page_id] = button

                child_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                    spacing=0)
                child_box.set_visible(False)   # collapsed until expanded
                for child_label, child_id in children:
                    child = self.create_nav_button(
                        child_label, child_id, is_top=False, indent=True)
                    layout.box_add(child_box, child, False, False, 0)
                    self.nav_buttons[child_id] = child
                    self.submenus[page_id]["children"].append(child)
                layout.box_add(nav_box_top, child_box, False, False, 0)
                self.submenu_boxes[page_id] = child_box
            else:
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

        # r081: window show_all() force-shows every descendant, overriding
        # the constructed collapsed state — groups shipped EXPANDED and
        # (before the caret toggle existed) could never be collapsed. On
        # the first map, re-assert the designed collapsed start.
        self._collapse_pending = True
        self.connect('map', self._on_sidebar_map)

    def _on_sidebar_map(self, *_args):
        if not self._collapse_pending:
            return False
        self._collapse_pending = False
        for page_id in self.submenu_boxes:
            self.expand_submenu(page_id, False)
        return False
    
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
    
    def expand_submenu(self, page_id, expanded=True):
        """Show/hide a group's children; caret rotates to point down/up."""
        info = self.submenus.get(page_id)
        box = self.submenu_boxes.get(page_id)
        if info is None or box is None:
            return
        box.set_visible(expanded)
        caret_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..",
            "resources", "icons", "regular",
            "caret-down.svg" if expanded else "caret-right.svg")
        info["caret"].set_from_pixbuf(
            GdkPixbuf.Pixbuf.new_from_file_at_size(caret_path, 11, 11))

    def _on_caret_toggle(self, page_id):
        """r081: caret click toggles the group's submenu — expands the
        children downward, contracts them upward. The EventBox sits above
        the group button, so the click never navigates."""
        box = self.submenu_boxes.get(page_id)
        self.expand_submenu(page_id,
                            not (box.get_visible() if box else False))

    def ensure_group_expanded(self, page_id):
        """r081: when navigation lands on a submenu child (Basics via a
        band-chart click), expand its parent group so the destination is
        visible in the sidebar."""
        for parent, children in SUBMENUS.items():
            if any(child_id == page_id for _label, child_id in children):
                box = self.submenu_boxes.get(parent)
                if box is not None and not box.get_visible():
                    self.expand_submenu(parent, True)
                return

    def on_navigated(self, page_id):
        """r081: navigation-manager hook for ALL navigation paths — moves
        the active highlight (programmatic navigation used to leave the
        sidebar unhighlighted) and expands the destination's parent group.
        Idempotent for clicks that already did both."""
        self.ensure_group_expanded(page_id)
        button = self.nav_buttons.get(page_id)
        if button is not None:
            self.set_active_button(button)

    def on_nav_clicked(self, button, page_id):
        """Handle navigation click"""
        # r075: expansion persists across navigation — no auto-collapse.
        self.set_active_button(button)
        self.nav_manager.navigate_to(page_id)
        # r073: a child click expands its parent's submenu (downward)
        for parent, info in self.submenus.items():
            if any(child is button for child in info["children"]):
                self.expand_submenu(parent, True)
        self.emit('page-changed', page_id)
