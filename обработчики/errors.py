"""Глобальный обработчик ошибок: логирование и сообщение пользователю."""
import logging

from aiogram import Router
from aiogram.types import ErrorEvent

router = Router()
logger = logging.getLogger(__name__)

ERROR_MESSAGE = (
    "⚠️ Что-то пошло не так. Попробуйте позже или напишите в поддержку."
)


@router.errors()
async def global_error_handler(event: ErrorEvent) -> None:
    """Ловит все необработанные исключения в хендлерах."""
    logger.exception("Unhandled error: %s", event.exception)
    update = event.update
    chat_id = None
    if update.message:
        chat_id = update.message.chat.id
    elif update.callback_query and update.callback_query.message:
        chat_id = update.callback_query.message.chat.id
    if chat_id:
        try:
            await update.bot.send_message(chat_id, ERROR_MESSAGE)
        except Exception:
            pass
