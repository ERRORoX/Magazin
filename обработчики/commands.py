"""Команды бота магазина ноутбуков."""
import os

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode

from database import get_db
from database.db import STATUS_LABELS
from utils.keyboards import build_main_keyboard
from utils.auth import is_admin
from utils.locales import t

router = Router()


def _first_name(user) -> str:
    if not user:
        return ""
    if user.first_name:
        return user.first_name.strip()
    if user.full_name:
        return user.full_name.split()[0].strip() if user.full_name else ""
    return ""


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    user = message.from_user
    if not user:
        return
    user_id = user.id
    db = get_db()
    await db.ensure_user(
        user_id=user_id,
        username=user.username,
        full_name=user.full_name,
    )
    lang = await db.get_user_lang(user_id)
    name = _first_name(user)
    custom_welcome = (os.getenv("BOT_WELCOME_MESSAGE") or "").strip()
    if custom_welcome:
        text = custom_welcome.replace("{name}", name or "").replace("{lang}", lang or "ru")
    else:
        greeting = t("welcome", lang, name=name) if name else t("welcome_no_name", lang)
        text = f"{greeting}\n\n<b>{t('welcome_sub', lang)}</b>"
    await message.answer(
        text,
        reply_markup=build_main_keyboard(user_id, lang),
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    if not message.from_user:
        return
    db = get_db()
    lang = await db.get_user_lang(message.from_user.id)
    name = _first_name(message.from_user)
    admin_hint = ""
    if is_admin(message.from_user.id):
        admin_hint = "\n<b>/stats</b> — статистика (админ)\n"
    msg = f"{t('help_title', lang)}{', ' + name if name else ''}\n\n"
    msg += f"{t('help_catalog', lang)}\n{t('help_ai', lang)}\n{t('help_order_flow', lang)}\n{t('help_my_orders', lang)}\n{t('help_cancel', lang)}" + admin_hint
    await message.answer(msg, parse_mode=ParseMode.HTML)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    db = get_db()
    lang = await db.get_user_lang(message.from_user.id)
    current = await state.get_state()
    if not current:
        await message.answer(
            t("cancel_nothing", lang),
            reply_markup=build_main_keyboard(message.from_user.id, lang),
        )
        return
    await state.clear()
    await message.answer(
        t("cancel_done", lang),
        reply_markup=build_main_keyboard(message.from_user.id, lang),
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Краткая статистика для администратора (заказы по статусам, товары)."""
    if not message.from_user or not is_admin(message.from_user.id):
        return
    db = get_db()
    lang = await db.get_user_lang(message.from_user.id)
    orders = await db.get_all_orders()
    products = await db.get_products()
    by_status = {}
    for o in orders:
        s = o.get("status", "new")
        by_status[s] = by_status.get(s, 0) + 1
    lines = [
        f"📊 <b>{t('stats_title', lang)}</b>",
        "",
        f"📋 {t('stats_orders_total', lang)}: <b>{len(orders)}</b>",
        f"🖥 {t('stats_products_count', lang)}: <b>{len(products)}</b>",
        "",
        f"<b>{t('stats_by_status', lang)}:</b>",
    ]
    for sid, label in STATUS_LABELS.items():
        cnt = by_status.get(sid, 0)
        lines.append(f"  • {label}: {cnt}")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)
