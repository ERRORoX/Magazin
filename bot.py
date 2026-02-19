"""
Точка входа: Telegram-бот магазина ноутбуков (Таджикистан).
Aiogram 3, async, SQLite (aiosqlite).
Админ-панель: HTTP API на порту ADMIN_PORT (по умолчанию 8080).
При завершении (Ctrl+C, закрытие окна, kill) порт освобождается автоматически.
"""
import asyncio
import logging
import os
import signal
from logging.handlers import RotatingFileHandler

from aiohttp import web
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import (
    APP_ROOT,
    TELEGRAM_BOT_TOKEN,
    ADMIN_PORT,
    ADMIN_HOST,
    LOG_DIR,
    LOG_FILE,
    LOG_MAX_BYTES,
    LOG_BACKUP_COUNT,
    RECEIPT_REMINDER_HOURS,
)
from обработчики import router
from database.db import db

from api_server import create_app
from utils.locales import t


async def receipt_reminder_loop(bot) -> None:
    """Каждые 30 минут напоминает клиентам с заказами «ожидает оплату» отправить чек."""
    while True:
        await asyncio.sleep(30 * 60)  # 30 мин
        try:
            orders = await db.get_orders_for_receipt_reminder(RECEIPT_REMINDER_HOURS)
            for o in orders:
                uid = o.get("user_id")
                if not uid:
                    continue
                lang = await db.get_user_lang(uid)
                text = t("receipt_reminder", lang, order_number=o.get("order_number", ""))
                try:
                    await bot.send_message(uid, text)
                except Exception:
                    pass
        except Exception as e:
            logging.exception("Receipt reminder: %s", e)


def _setup_logging() -> None:
    load_dotenv(dotenv_path=APP_ROOT / ".env", override=False)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        h = logging.StreamHandler()
        h.setFormatter(fmt)
        root.addHandler(h)
        fh = RotatingFileHandler(LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)


async def main() -> None:
    _setup_logging()
    pid_file = APP_ROOT / "bot.pid"
    try:
        pid_file.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass
    
    token = TELEGRAM_BOT_TOKEN
    bot = None
    dp = None
    
    # Проверяем токен, но не падаем если его нет — админ-сайт всё равно запустится
    if token and token not in ("PASTE_YOUR_TOKEN", "ВСТАВЬТЕ_СЮДА") and not token.startswith("••••"):
        try:
            dp = Dispatcher(storage=MemoryStorage())
            dp.include_router(router)
            bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
            try:
                me = await bot.get_me()
                logging.info("Бот запущен: @%s", me.username)
            except Exception as e:
                logging.warning("Токен неверный или недоступен: %r. Админ-панель будет работать без бота.", e)
                bot = None
                dp = None
        except Exception as e:
            logging.warning("Ошибка инициализации бота: %r. Админ-панель будет работать без бота.", e)
            bot = None
            dp = None
    else:
        logging.warning("TELEGRAM_BOT_TOKEN не указан в .env. Админ-панель запустится, но бот не будет работать. Добавьте токен через админ-панель: Настройки → Переменные .env")

    await db.init()

    runner = None
    main_task = asyncio.current_task()

    def _request_shutdown(*_args):
        """По сигналу завершения — останавливаем бота, затем в finally закроется сервер и порт."""
        if main_task and not main_task.done():
            main_task.cancel()

    # При Ctrl+C или kill — корректно завершаем; в finally закроется сервер и освободится порт
    try:
        signal.signal(signal.SIGINT, _request_shutdown)
    except (ValueError, OSError):
        pass
    try:
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _request_shutdown)
    except (ValueError, OSError):
        pass

    try:
        # Админ-сайт запускается всегда, даже без бота
        admin_app = create_app(bot=bot)
        runner = web.AppRunner(admin_app)
        await runner.setup()
        site = web.TCPSite(runner, ADMIN_HOST, ADMIN_PORT)
        try:
            await site.start()
        except OSError as e:
            if e.errno == 98 or "address already in use" in str(e).lower():
                logging.error(
                    "Порт %s занят. Закройте другой экземпляр бота или программу, использующую этот порт. "
                    "Или в .env укажите другой порт: ADMIN_PORT=8081. "
                    "На Linux освободить порт: fuser -k %s/tcp",
                    ADMIN_PORT,
                    ADMIN_PORT,
                )
            raise
        if ADMIN_HOST == "0.0.0.0":
            logging.warning("Админ-панель доступна по сети: http://<ваш_IP>:%s (установите ADMIN_SECRET в .env)", ADMIN_PORT)
        else:
            logging.info("Админ-панель: http://%s:%s", ADMIN_HOST, ADMIN_PORT)
        
        # Если бот есть — запускаем его и напоминания про чеки
        if bot and dp:
            asyncio.create_task(receipt_reminder_loop(bot))
            async with bot:
                await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        else:
            # Если бота нет — просто ждём завершения (Ctrl+C)
            logging.info("Админ-панель работает. Добавьте TELEGRAM_BOT_TOKEN в .env через панель и перезапустите бота.")
            try:
                while True:
                    await asyncio.sleep(3600)  # Ждём час или до сигнала завершения
            except asyncio.CancelledError:
                pass
    except asyncio.CancelledError:
        logging.info("Получен сигнал завершения, останавливаю...")
    finally:
        if bot:
            try:
                await bot.session.close()
            except Exception:
                pass
        if runner is not None:
            await runner.cleanup()
            logging.info("Админ-сервер остановлен, порт %s освобождён.", ADMIN_PORT)
        try:
            await db.close()
        except Exception:
            pass
        try:
            if pid_file.exists():
                pid_file.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        pass
    except Exception as e:
        logging.exception("Критическая ошибка: %s", e)
        raise
