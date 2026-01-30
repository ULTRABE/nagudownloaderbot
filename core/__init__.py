"""Core module for bot initialization and configuration"""
from .config import config
from .bot import bot, dp

__all__ = ['config', 'bot', 'dp']
