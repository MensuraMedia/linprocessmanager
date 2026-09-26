"""
Theme Selector Widget
Visual theme selector with smaller color circles
"""

from ..compat import Gtk, Gdk, events, layout
from ..compat.charts import ChartArea
import cairo


class ThemeColorButton(ChartArea):
    """
    Custom widget that displays a colored circle for theme selection
    Updated: Smaller 25x25 circles

    Draw + click go through the compat seams (charts.ChartArea, events) so no
    toolkit signal is named here — see upgrade-architecture.md §3.
    """

    def __init__(self, theme_id, theme_def, callback):
        """
        Initialize theme color button

        Args:
            theme_id: Theme identifier
            theme_def: ThemeDefinition instance
            callback: Function to call when clicked
        """
        super().__init__()

        self.theme_id = theme_id
        self.theme_def = theme_def
        self.callback = callback
        self.is_selected = False

        # Set size - reduced to 25x25
        self.set_size_request(25, 25)

        # Draw via the charts seam (connect("draw") ↔ set_draw_func)
        self.set_draw_callback(self.on_draw)
        # Click via the events seam (GestureMultiPress ↔ GestureClick)
        self._click = events.click_gesture(self, self.on_pressed)

        # Tooltip
        self.set_tooltip_text(theme_def.name)

    def on_draw(self, widget, cr, width, height):
        """Draw the colored circle"""
        # Center point
        cx = width / 2
        cy = height / 2
        
        # Circle radius
        radius = min(width, height) / 2 - 2
        
        # Parse accent color
        color = Gdk.RGBA()
        color.parse(self.theme_def.accent_color)
        
        # Draw circle
        cr.arc(cx, cy, radius, 0, 2 * 3.14159)
        cr.set_source_rgb(color.red, color.green, color.blue)
        cr.fill()
        
        # Draw selection ring if selected
        if self.is_selected:
            cr.arc(cx, cy, radius + 1, 0, 2 * 3.14159)
            cr.set_source_rgb(1, 1, 1)
            cr.set_line_width(1.5)
            cr.stroke()
        
        return False
    
    def on_pressed(self, gesture, n_press, x, y):
        """Handle click gesture (normalized 'pressed' signature)"""
        if self.callback:
            self.callback(self.theme_id)
    
    def set_selected(self, selected):
        """Set selection state"""
        self.is_selected = selected
        self.queue_draw()


class ThemeSelectorWidget(Gtk.Box):
    """
    Theme selector widget with small color circles
    """
    
    def __init__(self, themes_dict, current_theme='default', on_theme_changed=None):
        """
        Initialize theme selector
        
        Args:
            themes_dict: Dictionary of theme_id -> ThemeDefinition
            current_theme: Currently selected theme ID
            on_theme_changed: Callback when theme changes
        """
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        self.themes_dict = themes_dict
        self.current_theme = current_theme
        self.on_theme_changed = on_theme_changed
        self.color_buttons = {}
        
        # Create color buttons for each theme
        for theme_id, theme_def in themes_dict.items():
            button = ThemeColorButton(theme_id, theme_def, self.theme_clicked)
            button.set_selected(theme_id == current_theme)
            layout.box_add(self, button, False, False, 0)
            self.color_buttons[theme_id] = button
    
    def theme_clicked(self, theme_id):
        """Handle theme selection"""
        # Update selection state
        for tid, button in self.color_buttons.items():
            button.set_selected(tid == theme_id)
        
        self.current_theme = theme_id
        
        # Trigger callback
        if self.on_theme_changed:
            self.on_theme_changed(theme_id)
    
    def get_selected_theme(self):
        """Get currently selected theme ID"""
        return self.current_theme
