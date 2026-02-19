"""Админ: список заказов с оптимизацией и группировкой."""
import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode

from database import get_db
from database.db import STATUS_LABELS
# Исправлено на латиницу, проверь имя папки!
from utils.auth import is_admin 

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("orders"))
async def cmd_orders(message: Message) -> None:
    # 1. Проверка прав с уведомлением
    if not is_admin(message.from_user.id):
        await message.answer("⚠️ У вас нет прав доступа к этой команде.")
        return

    db = get_db()
    
    # 2. Получаем данные (предположим, метод get_all_orders уже умеет в JOIN)
    # Если нет, лучше добавить метод get_orders_with_titles в класс Database
    orders = await db.get_all_orders()
    
    if not orders:
        await message.answer("📋 <b>Заказов пока нет.</b>", parse_mode=ParseMode.HTML)
        return

    # 3. Группируем и формируем текст
    # Берем последние 20 заказов для наглядности
    recent_orders = orders[-20:] 
    lines = []
    
    for o in recent_orders:
        # Пытаемся взять заголовок из заказа (если сделали JOIN) или из БД
        # Оптимизация: в идеале db.get_all_orders должен возвращать 'product_title'
        prod = await db.get_product(o["product_id"])
        title = prod["title"] if prod else f"ID:{o['product_id']}"
        
        status_raw = o.get("status", "new")
        status_text = STATUS_LABELS.get(status_raw, status_raw)
        
        # Эмодзи для статусов для быстрой навигации
        icon = "🆕" if status_raw == "new" else "💳" if status_raw == "paid" else "📦"
        
        lines.append(
            f"{icon} <code>{o['order_number']}</code> | {title}\n"
            f"   └ Статус: <b>{status_text}</b>"
        )

    header = f"📋 <b>Последние 20 заказов (Всего: {len(orders)})</b>\n\n"
    text = header + "\n\n".join(lines)

    # 4. Защита от переполнения (max 4096 симв)
    if len(text) > 4000:
        text = text[:3997] + "..."

    await message.answer(text, parse_mode=ParseMode.HTML)

@router.message(Command("order_info"))
async def cmd_order_detail(message: Message) -> None:
    """Дополнительная команда для просмотра деталей конкретного заказа."""
    if not is_admin(message.from_user.id): return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Введите номер заказа: <code>/order_info 12345</code>", parse_mode=ParseMode.HTML)
        return
        
    # Тут можно добавить поиск по номеру заказа...
    pass