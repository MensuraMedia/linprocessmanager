"""
Settings Page
Dashboard configuration and technical details
Updated: Accurate tree structure after cleanup
"""

from ui.compat import layout

from pages.page_base import BasePage
from config.config_themes import get_all_themes, get_theme
from ui.components.component_theme_selector import ThemeSelectorWidget
from modules.manager_theme_applicator import ThemeApplicator
from log import get_logger
log = get_logger("settings")


class SettingsPage(BasePage):
    """Settings page with theme selector and configuration information"""
    
    def __init__(self):
        """Initialize settings page"""
        self.theme_applicator = ThemeApplicator()
        self.current_theme_id = 'default'
        super().__init__()
    
    def build_content(self):
        """Build settings page content"""
        
        self.add_title("Dashboard Configuration")
        
        self.add_paragraph(
            "Customize your dashboard appearance and view technical details."
        )
        
        # Theme selector section
        self.add_subtitle("Theme")
        
        # Create theme selector widget
        themes = get_all_themes()
        theme_selector = ThemeSelectorWidget(
            themes,
            current_theme=self.current_theme_id,
            on_theme_changed=self.on_theme_changed
        )
        layout.box_add(self, theme_selector, False, False, 10)
        
        # Technical specs section
        self.add_subtitle("Technical Specifications")
        
        self.add_paragraph(
            "• GTK Version: GTK+ 3.0 (compat layer keeps the tree GTK4-ready)\n"
            "• Python: 3.10+ (system python3; stdlib-only core)\n"
            "• Dependencies: PyGObject, pycairo, Pillow (system packages)\n"
            "• Architecture: Modular, page-based routing over a compat seam\n"
            "• Data source: /proc read directly (no psutil)\n"
            "• Sidebar Width: 150px\n"
            "• Logo Area: 150x150px (square)\n"
            "• Navigation Button Height: 28px\n"
            "• Navigation Pages: 7 (Processes, Graphs, Disks, Logs, Basics, About, Settings)\n"
            "• Themes: 7 popular dark themes available\n"
            "• License: Free for personal and educational use"
        )
        
        # Project structure section
        self.add_subtitle("Project Structure")
        
        self.add_markup_label(
            "<span font_family='monospace' foreground='#d0d0d0'>"
            "linprocman/\n"
            "├── src/                     # Application source code\n"
            "│   ├── main.py              # Gtk.Application entry point\n"
            "│   ├── config/              # Configuration modules\n"
            "│   │   ├── config_theme.py  # Theme colors/fonts\n"
            "│   │   ├── config_layout.py # Layout dimensions\n"
            "│   │   └── config_themes.py # Theme definitions\n"
            "│   ├── ui/                  # UI components\n"
            "│   │   ├── dashboard_window.py\n"
            "│   │   ├── sidebar.py\n"
            "│   │   ├── content_area.py\n"
            "│   │   ├── compat/          # GTK version seam (one file/seam)\n"
            "│   │   │   ├── gtk_env.py    # the only gi.repository import\n"
            "│   │   │   ├── layout.py     # box pack / child-add\n"
            "│   │   │   ├── menu.py       # model-driven menus\n"
            "│   │   │   ├── events.py     # gestures / accels\n"
            "│   │   │   ├── dialogs.py    # confirm windows\n"
            "│   │   │   ├── charts.py     # cairo draw hookup\n"
            "│   │   │   ├── icons.py      # pixbuf → image\n"
            "│   │   │   └── css.py        # provider + class helpers\n"
            "│   │   └── components/      # UI widgets\n"
            "│   │       └── component_theme_selector.py\n"
            "│   ├── pages/               # Page modules\n"
            "│   │   ├── page_base.py     # Base page class\n"
            "│   │   ├── page_processes.py\n"
            "│   │   ├── page_graphs.py   # Graphs hub (live mini-charts)\n"
            "│   │   ├── graph_details.py # Graphs ▸ X detail pages\n"
            "│   │   ├── page_disks.py\n"
            "│   │   ├── page_logs.py\n"
            "│   │   ├── page_about.py\n"
            "│   │   └── page_settings.py\n"
            "│   ├── modules/             # Feature modules\n"
            "│   │   ├── procfs.py        # /proc readers (stdlib-only)\n"
            "│   │   ├── sysfs.py         # /sys readers (stdlib-only)\n"
            "│   │   ├── manager_navigation.py\n"
            "│   │   └── manager_theme_applicator.py\n"
            "│   └── utils/               # Utility functions\n"
            "│       └── manager_theme.py # CSS loader\n"
            "├── resources/               # Static resources (icons, images)\n"
            "├── docs/                    # Documentation\n"
            "├── tests/                   # pytest suite (gates + parsers)\n"
            "├── changelog.md             # Append-only change log\n"
            "└── requirements.txt         # System-package manifest (comment)"
            "</span>",
            selectable=True
        )
    
    def on_theme_changed(self, theme_id):
        """
        Handle theme change
        
        Args:
            theme_id: Selected theme identifier
        """
        self.current_theme_id = theme_id
        theme_def = get_theme(theme_id)
        
        # Apply theme
        self.theme_applicator.apply_theme(theme_def)
        
        log.info("theme changed: %s", theme_def.name)
