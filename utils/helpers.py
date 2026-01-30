"""Helper utility functions"""
import os
import glob
import random
import asyncio
from pathlib import Path
from typing import Optional
from aiogram.types import User

def mention(user: User) -> str:
    """Create HTML mention for user"""
    return f'<a href="tg://user?id={user.id}">{user.first_name}</a>'

def get_random_cookie(folder: str) -> Optional[str]:
    """Get random cookie file from folder"""
    if not os.path.exists(folder):
        return None
    cookies = glob.glob(f"{folder}/*.txt")
    if not cookies:
        return None
    return random.choice(cookies)

async def resolve_pin_url(url: str) -> str:
    """Resolve shortened Pinterest URL"""
    if "pin.it/" not in url:
        return url
    
    try:
        # Use async subprocess to resolve URL
        proc = await asyncio.create_subprocess_exec(
            'curl', '-Ls', '-o', '/dev/null', '-w', '%{url_effective}', url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        resolved = stdout.decode().strip()
        return resolved if resolved else url
    except:
        return url
