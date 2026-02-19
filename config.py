"""
Конфигурация приложения. Все переменные окружения и лимиты в одном месте.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

APP_ROOT = Path(__file__).resolve().parent
load_dotenv(APP_ROOT / ".env")

# Бот
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

# Админ-панель
ADMIN_PORT = int(os.getenv("ADMIN_PORT", "8080"))
ADMIN_HOST = (os.getenv("ADMIN_HOST", "127.0.0.1") or "127.0.0.1").strip()
ADMIN_SECRET = (os.getenv("ADMIN_SECRET") or "").strip()
ADMIN_ALLOWED_IPS = [x.strip() for x in os.getenv("ADMIN_ALLOWED_IPS", "").split(",") if x.strip()]

# Логи
LOG_DIR = APP_ROOT / "logs"
LOG_FILE = LOG_DIR / "bot.log"
LOG_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
LOG_BACKUP_COUNT = 3

# Заказы и чеки
MAX_RECEIPT_PHOTO_BYTES = 10 * 1024 * 1024  # 10 MB
RECEIPT_REMINDER_HOURS = 6  # Напоминание про чек через N часов

# Реквизиты для оплаты
PAYMENT_REQUISITES = os.getenv(
    "PAYMENT_REQUISITES",
    "Оплата на карту <b>Душанбе Сити</b>.\n"
    "Номер карты: укажите в .env (PAYMENT_REQUISITES)\n"
    "Получатель: укажите ФИО в .env",
)

# Контакты поддержки (для кнопки «Связаться с нами»)
SUPPORT_TELEGRAM = (os.getenv("SUPPORT_TELEGRAM") or "").strip()
SUPPORT_PHONE = (os.getenv("SUPPORT_PHONE") or "").strip()
SUPPORT_WHATSAPP = (os.getenv("SUPPORT_WHATSAPP") or "").strip()
SUPPORT_INSTAGRAM = (os.getenv("SUPPORT_INSTAGRAM") or "").strip()
