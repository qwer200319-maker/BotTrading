import os
from dotenv import load_dotenv
load_dotenv()

from notifier import send_telegram

send_telegram("✅ Render test: Telegram sending works!")
print("Sent test message.")