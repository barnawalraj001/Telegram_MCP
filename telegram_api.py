# telegram_api.py

import os
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from tokens import get_telegram_session

load_dotenv()  # ✅ ADD THIS

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")



async def get_client(user_id: str):
    session = get_telegram_session(user_id)
    if not session:
        raise Exception("Telegram not connected for this user")

    client = TelegramClient(
        StringSession(session),
        API_ID,
        API_HASH
    )
    await client.connect()
    return client
