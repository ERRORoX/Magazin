"""Уведомление администраторов о новых заказах."""
import logging
import os
from typing import List

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramForbiddenError

from database import get_db
from database.db import STATUS_LABELS, CATEGORY_LABELS


def get_admin_ids() -> List[int]:
    admin_ids_str = os.getenv("ADMIN_IDS", "")
    if not admin_ids_str:
        return []
    out = []
    for x in admin_ids_str.split(","):
        x = x.strip()
        if x.isdigit():
            out.append(int(x))
    return out

async def notify_admin_new_order(bot: Bot, order: dict, product: dict) -> None:
    """Отправляет всем админам сообщение о новом заказе."""
    admin_ids = get_admin_ids()
    if not admin_ids:
        logging.warning("ADMIN_IDS не заданы — уведомление не отправлено")
        return

    # 1. Сначала готовим данные для сообщения
    category_label = CATEGORY_LABELS.get(product.get("category", ""), product.get("category", ""))
    status_label = STATUS_LABELS.get(order.get("status", ""), order.get("status", ""))
    order_id = order.get("id")
    title = product.get("title", "—")
    price = product.get("price", 0)
    
    try:
        price_str = f"{int(price):,} сомони".replace(",", " ")
    except (TypeError, ValueError):
        price_str = str(price)

    # 2. Формируем текст
    text = (
        "🆕 <b>Новый заказ</b>\n\n"
        f"📋 Номер: <code>{order.get('order_number', '')}</code>\n"
        f"👤 ФИО: {order.get('full_name', '')}\n"
        f"📞 Телефон: {order.get('phone', '')}\n"
        f"🏙 Город: {order.get('city', '')}\n"
        f"📍 Адрес: {order.get('address', '')}\n\n"
        f"🖥 Товар: {title}\n"
        f"📂 Категория: {category_label}\n"
        f"💰 Цена: {price_str}\n\n"
        f"📌 Статус: {status_label}"
    )

    # 3. Создаем клавиатуру
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Чек получен", callback_data=f"admin_order_receipt:{order_id}")],
        [InlineKeyboardButton(text="Оплачен", callback_data=f"admin_order_paid:{order_id}")],
        [InlineKeyboardButton(text="Отправлен", callback_data=f"admin_order_shipped:{order_id}")],
    ])

    # 4. Рассылаем всем админам
    for admin_id in admin_ids:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except TelegramForbiddenError:
            logging.error(f"Бот заблокирован админом {admin_id}")
        except Exception as e:
            logging.error(f"Ошибка при отправке админу {admin_id}: {e}")


async def notify_client_order_status(bot: Bot, order: dict, new_status: str) -> None:
    """Уведомляет клиента (user_id из заказа) о смене статуса: оплачен / отправлен."""
    user_id = order.get("user_id")
    if not user_id:
        return
    order_number = order.get("order_number", "")
    if new_status == "paid":
        text = (
            f"✅ <b>Заказ {order_number} оплачен</b>\n\n"
            "Спасибо за оплату! Мы готовим ваш заказ к отправке."
        )
    elif new_status == "shipped":
        text = (
            f"🚚 <b>Заказ {order_number} отправлен</b>\n\n"
            "Ваш заказ передан в доставку. Ожидайте звонка курьера."
        )
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Оставить отзыв", callback_data=f"review:{order.get('id')}")],
        ])
        try:
            await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            logging.warning("Не удалось уведомить клиента %s: %s", user_id, e)
        return
    else:
        return
    try:
        await bot.send_message(user_id, text, parse_mode="HTML")
    except Exception as e:
        logging.warning("Не удалось уведомить клиента %s: %s", user_id, e)
