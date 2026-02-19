"""FSM оформления заказа: ФИО, телефон, город, адрес → реквизиты → фото чека."""
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.enums import ParseMode

from config import PAYMENT_REQUISITES, MAX_RECEIPT_PHOTO_BYTES
from database import get_db
from services.order_service import OrderService
from services.notification_service import notify_admin_new_order
from utils.keyboards import build_main_keyboard, build_order_cancel_keyboard
from utils.locales import t

router = Router()


class OrderStates(StatesGroup):
    waiting_fio = State()
    waiting_phone = State()
    waiting_city = State()
    waiting_address = State()
    waiting_receipt = State()


@router.message(OrderStates.waiting_fio, F.text)
async def process_fio(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    lang = await get_db().get_user_lang(message.from_user.id)
    fio = (message.text or "").strip()
    if len(fio) < 3:
        await message.answer(t("order_fio_min", lang))
        return
    await state.update_data(full_name=fio)
    await state.set_state(OrderStates.waiting_phone)
    data = await state.get_data()
    product_hint = data.get("product_title") or t("product_default", lang)
    contact_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("btn_send_phone", lang), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(
        f"<b>{t('order_step', lang, step=2)}</b> — {t('order_phone', lang)}\n\n<i>{product_hint}</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=contact_kb,
    )


def _normalize_phone(phone: str) -> str:
    """Оставляет только цифры и ведущий +."""
    s = (phone or "").strip()
    if not s:
        return ""
    digits = "".join(c for c in s if c.isdigit())
    if s.startswith("+"):
        return "+" + digits
    return digits


def _is_valid_phone(phone: str) -> bool:
    """Проверка: не пусто, достаточно цифр (9+)."""
    p = _normalize_phone(phone)
    if not p:
        return False
    digits = "".join(c for c in p if c.isdigit())
    return len(digits) >= 9


def _city_keyboard(lang: str, has_last: bool) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    if has_last:
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=t("btn_last_address", lang))]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
    return ReplyKeyboardRemove()


@router.message(OrderStates.waiting_phone, F.contact)
async def process_phone_contact(message: Message, state: FSMContext) -> None:
    if not message.contact or not message.from_user:
        return
    lang = await get_db().get_user_lang(message.from_user.id)
    phone = message.contact.phone_number or ""
    if not phone.startswith("+"):
        phone = "+" + phone
    await state.update_data(phone=phone)
    await state.set_state(OrderStates.waiting_city)
    data = await state.get_data()
    product_hint = data.get("product_title") or t("product_default", lang)
    last = await get_db().get_user_last_address(message.from_user.id)
    await message.answer(
        f"<b>{t('order_step', lang, step=3)}</b> — {t('order_city', lang)}\n\n<i>{product_hint}</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=_city_keyboard(lang, bool(last)),
    )


@router.message(OrderStates.waiting_phone, F.text)
async def process_phone(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    lang = await get_db().get_user_lang(message.from_user.id)
    phone = (message.text or "").strip()
    if not _is_valid_phone(phone):
        await message.answer(t("order_phone_invalid", lang), parse_mode=ParseMode.HTML)
        return
    phone = _normalize_phone(phone)
    if not phone.startswith("+"):
        phone = "+" + phone
    await state.update_data(phone=phone)
    await state.set_state(OrderStates.waiting_city)
    data = await state.get_data()
    product_hint = data.get("product_title") or t("product_default", lang)
    last = await get_db().get_user_last_address(message.from_user.id)
    await message.answer(
        f"<b>{t('order_step', lang, step=3)}</b> — {t('order_city', lang)}\n\n<i>{product_hint}</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=_city_keyboard(lang, bool(last)),
    )


@router.message(OrderStates.waiting_city, F.text)
async def process_city(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    lang = await get_db().get_user_lang(message.from_user.id)
    text = (message.text or "").strip()
    if text == t("btn_last_address", lang):
        last = await get_db().get_user_last_address(message.from_user.id)
        if not last or not last.get("city"):
            await message.answer(t("order_city_min", lang), reply_markup=ReplyKeyboardRemove())
            return
        await state.update_data(city=last["city"], address=last.get("address") or "")
        await state.set_state(OrderStates.waiting_address)
        await _finish_order_from_state(message, state)
        return
    city = text
    if len(city) < 2:
        await message.answer(t("order_city_min", lang))
        return
    await state.update_data(city=city)
    await state.set_state(OrderStates.waiting_address)
    data = await state.get_data()
    product_hint = data.get("product_title") or t("product_default", lang)
    await message.answer(
        f"<b>{t('order_step', lang, step=4)}</b> — {t('order_address', lang)}\n\n<i>{product_hint}</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=build_order_cancel_keyboard(lang),
    )


async def _finish_order_from_state(message: Message, state: FSMContext) -> None:
    """Создать заказ из данных state (city, address в data), отправить реквизиты, уведомить админа."""
    if not message.from_user:
        return
    bot = message.bot
    lang = await get_db().get_user_lang(message.from_user.id)
    data = await state.get_data()
    address = (data.get("address") or "").strip()
    city = (data.get("city") or "").strip()
    if len(address) < 5 or len(city) < 2:
        await message.answer(t("order_address_min", lang), reply_markup=build_order_cancel_keyboard(lang))
        return
    user = message.from_user
    await get_db().ensure_user(user.id, username=user.username, full_name=user.full_name)
    product_id = data.get("product_id")
    if not product_id:
        await state.clear()
        await message.answer(t("order_session_reset", lang), reply_markup=build_main_keyboard(user.id, lang))
        return
    stock = await get_db().get_product_stock(product_id)
    if stock <= 0:
        await state.clear()
        await message.answer(t("order_out_of_stock", lang), reply_markup=build_main_keyboard(user.id, lang))
        return
    order = await OrderService.create(
        user_id=user.id,
        product_id=product_id,
        full_name=data["full_name"],
        phone=data["phone"],
        city=city,
        address=address,
    )
    if not order:
        await message.answer(t("order_error_later", lang), reply_markup=build_main_keyboard(user.id, lang))
        await state.clear()
        return
    await get_db().decrement_product_stock(product_id)
    product = await get_db().get_product(product_id)
    product_title = product["title"] if product else f"{t('product_default', lang)} #{product_id}"
    price = product["price"] if product else 0
    await state.set_state(OrderStates.waiting_receipt)
    await state.update_data(order_id=order["id"])
    text = (
        f"<b>{t('order_step', lang, step=5)}</b> — {t('order_step_payment', lang)}\n\n"
        f"✅ {t('order_created', lang)} <b>{order['order_number']}</b>.\n\n"
        f"🖥 {product_title}\n"
        f"💰 {price:,} сомони\n\n"
        f"💳 {t('order_send_receipt', lang)}\n\n"
        f"{PAYMENT_REQUISITES}"
    ).replace(",", " ")
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
    await notify_admin_new_order(bot, order, product or {"title": product_title, "price": price, "category": ""})


@router.message(OrderStates.waiting_address, F.text)
async def process_address(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.from_user:
        return
    lang = await get_db().get_user_lang(message.from_user.id)
    address = (message.text or "").strip()
    if len(address) < 5:
        await message.answer(t("order_address_min", lang))
        return
    await state.update_data(address=address)
    await _finish_order_from_state(message, state)


@router.message(OrderStates.waiting_receipt, F.photo)
async def process_receipt_photo(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    lang = await get_db().get_user_lang(message.from_user.id)
    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        await state.clear()
        await message.answer(t("order_not_found", lang), reply_markup=build_main_keyboard(message.from_user.id, lang))
        return
    photo = message.photo[-1]
    if photo.file_size and photo.file_size > MAX_RECEIPT_PHOTO_BYTES:
        await message.answer(t("order_receipt_photo_too_large", lang), parse_mode=ParseMode.HTML)
        return
    file_id = photo.file_id
    await OrderService.set_receipt(order_id, file_id)
    await state.clear()
    await message.answer(
        f"✅ <b>{t('order_thanks', lang)}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=build_main_keyboard(message.from_user.id, lang),
    )


@router.message(OrderStates.waiting_receipt)
async def process_receipt_not_photo(message: Message) -> None:
    if not message.from_user:
        return
    lang = await get_db().get_user_lang(message.from_user.id)
    await message.answer(t("order_send_receipt_photo", lang), parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "order_cancel")
async def on_order_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    lang = await get_db().get_user_lang(callback.from_user.id)
    await state.clear()
    msg = t("order_cancel_done", lang)
    from aiogram.exceptions import TelegramBadRequest
    try:
        await callback.message.edit_text(msg, reply_markup=build_main_keyboard(callback.from_user.id, lang))
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(msg, reply_markup=build_main_keyboard(callback.from_user.id, lang))
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(msg, reply_markup=build_main_keyboard(callback.from_user.id, lang))
    await callback.answer()


