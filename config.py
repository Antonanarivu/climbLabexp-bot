import os

# Токен бота от @BotFather
BOT_TOKEN: str = os.environ["BOT_TOKEN"]

# Telegram chat_id ответственного за устранение
# Как узнать: написать боту /start в личке, затем открыть
# https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
RESPONSIBLE_CHAT_ID: int = int(os.environ["RESPONSIBLE_CHAT_ID"])
