"""Admin module for bot management features"""
from .permissions import is_admin, is_telegram_admin, sync_admins
from .moderation import mute_user, unmute_user, is_muted
from .filters import add_filter, remove_filter, get_filters, add_to_blocklist, remove_from_blocklist, get_blocklist, check_message_filters
from .handlers import register_admin_handlers

__all__ = [
    'is_admin', 'is_telegram_admin', 'sync_admins',
    'mute_user', 'unmute_user', 'is_muted',
    'add_filter', 'remove_filter', 'get_filters',
    'add_to_blocklist', 'remove_from_blocklist', 'get_blocklist',
    'check_message_filters', 'register_admin_handlers'
]
