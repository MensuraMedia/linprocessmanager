"""Page modules"""
from .page_base import BasePage
from .page_processes import ProcessesPage
from .page_resources import ResourcesPage
from .page_disks import DisksPage
from .page_logs import LogsPage
from .page_about import AboutPage
from .page_settings import SettingsPage

__all__ = [
    'BasePage',
    'ProcessesPage',
    'ResourcesPage',
    'DisksPage',
    'LogsPage',
    'AboutPage',
    'SettingsPage'
]
