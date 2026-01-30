"""Bot and dispatcher initialization"""
from aiogram import Bot, Dispatcher
from .config import config

# Initialize bot and dispatcher
bot = Bot(config.BOT_TOKEN)
dp = Dispatcher()
