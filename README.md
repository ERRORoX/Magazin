# Telegram Bot — магазин ноутбуков (Таджикистан)

Бот на Python (aiogram 3), каталог, заказы, админ-панель, AI-консультант.

## Сборка Windows .exe на GitHub

1. Загрузите этот репозиторий на GitHub (все папки и файлы, **кроме** `.env`, `venv`, `данные`, `logs`).
2. Вкладка **Actions** → workflow **Build Windows EXE** запустится сам (или нажмите Run workflow).
3. Через 5–10 минут в том же запуске внизу скачайте **Artifacts** → **TelegramBot-Windows** (внутри архив с `TelegramBot.exe`).

Подробно: файл **СБОРКА_НА_GITHUB.txt**.

## Локальный запуск

```bash
pip install -r requirements.txt
# Создайте .env с TELEGRAM_BOT_TOKEN и ADMIN_IDS
python bot.py
```

Админ-панель: http://localhost:8080
