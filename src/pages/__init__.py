"""Page modules"""
from .page_base import BasePage
from .page_processes import ProcessesPage
from .page_graphs import GraphsHubPage
from .graph_details import GraphDetailPage
from .page_disks import DisksPage
from .page_logs import LogsPage
from .page_basics import BasicsPage
from .page_about import AboutPage
from .page_settings import SettingsPage

__all__ = [
    'BasePage',
    'ProcessesPage',
    'GraphsHubPage',
    'GraphDetailPage',
    'DisksPage',
    'LogsPage',
    'BasicsPage',
    'AboutPage',
    'SettingsPage'
]
