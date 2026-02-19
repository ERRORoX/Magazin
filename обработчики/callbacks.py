"""Обработчики кнопок: каталог, товар, заказ, мои заказы, админ-статусы."""
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ParseMode, ChatAction
from aiogram.exceptions import TelegramBadRequest


class ReviewStates(StatesGroup):
    waiting_text = State()


class SearchStates(StatesGroup):
    waiting_query = State()

from database import get_db
from database.db import CATEGORY_LABELS, STATUS_LABELS
from services.notification_service import notify_client_order_status
from utils.keyboards import (
    build_main_keyboard,
    build_catalog_keyboard,
    build_products_keyboard,
    build_product_detail_keyboard,
    build_back_to_home_keyboard,
    build_my_orders_keyboard,
    build_order_detail_keyboard,
    build_delete_confirm_keyboard,
    build_lang_keyboard,
    _btn_home,
)
from config import SUPPORT_TELEGRAM, SUPPORT_PHONE, SUPPORT_WHATSAPP, SUPPORT_INSTAGRAM
from utils.auth import is_admin
from utils.locales import t

router = Router()


async def _get_lang(user_id: int) -> str:
    return await get_db().get_user_lang(user_id) if user_id else "ru"


async def _safe_edit_text(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = ParseMode.HTML,
) -> None:
    """Безопасное редактирование текста сообщения (игнорирует ошибку 'message is not modified')."""
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


async def _safe_edit_caption(
    message: Message,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = ParseMode.HTML,
) -> None:
    """Безопасное редактирование подписи сообщения (игнорирует ошибку 'message is not modified')."""
    try:
        await message.edit_caption(caption=caption, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


@router.callback_query(F.data == "home")
async def on_home(callback: CallbackQuery) -> None:
    from обработчики.commands import _first_name
    user_id = callback.from_user.id if callback.from_user else 0
    lang = await _get_lang(user_id)
    name = _first_name(callback.from_user) if callback.from_user else ""
    text = f"{t('main_menu', lang)}{', ' + name if name else ''}\n\n{t('main_menu_choose', lang)}"
    await _safe_edit_text(
        callback.message,
        text,
        reply_markup=build_main_keyboard(user_id, lang),
    )
    await callback.answer()


@router.callback_query(F.data == "catalog")
async def on_catalog(callback: CallbackQuery) -> None:
    if callback.from_user:
        await callback.message.bot.send_chat_action(callback.message.chat.id, ChatAction.TYPING)
    lang = await _get_lang(callback.from_user.id if callback.from_user else 0)
    await _safe_edit_text(
        callback.message,
        f"{t('catalog_title', lang)}\n\n{t('catalog_choose_cat', lang)}",
        reply_markup=build_catalog_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(F.data == "faq")
async def on_faq(callback: CallbackQuery) -> None:
    lang = await _get_lang(callback.from_user.id if callback.from_user else 0)
    text = (
        f"❓ <b>{t('faq_title', lang)}</b>\n\n"
        f"🚚 <b>Доставка:</b> {t('faq_delivery', lang)}\n\n"
        f"💳 <b>Оплата:</b> {t('faq_payment', lang)}\n\n"
        f"📋 <b>Гарантия:</b> {t('faq_guarantee', lang)}"
    )
    await _safe_edit_text(
        callback.message,
        text,
        reply_markup=build_main_keyboard(callback.from_user.id if callback.from_user else 0, lang),
    )
    await callback.answer()


@router.callback_query(F.data == "contacts")
async def on_contacts(callback: CallbackQuery) -> None:
    lang = await _get_lang(callback.from_user.id if callback.from_user else 0)
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    lines = [f"📞 <b>{t('contact_text', lang)}</b>\n"]
    has_any = False
    if SUPPORT_TELEGRAM:
        has_any = True
        tg_display = SUPPORT_TELEGRAM
        tg_link = tg_display.strip()
        if tg_link.startswith("http"):
            pass  # уже полная ссылка
        elif tg_link.startswith("t.me/"):
            tg_link = f"https://{tg_link}"
        elif tg_link.startswith("@"):
            tg_link = f"https://t.me/{tg_link[1:]}"
        else:
            # просто username без @
            tg_link = f"https://t.me/{tg_link}"
        lines.append(f"\n💬 <b>Telegram:</b> {tg_display}")
        builder.row(InlineKeyboardButton(text="💬 Telegram", url=tg_link))
    if SUPPORT_PHONE:
        has_any = True
        phone_display = SUPPORT_PHONE
        # Форматируем номер для отображения (Telegram автоматически сделает его кликабельным)
        phone_clean = phone_display.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not phone_clean.startswith("+"):
            if phone_clean.startswith("992"):
                phone_clean = "+" + phone_clean
            else:
                phone_clean = "+992" + phone_clean.lstrip("0")
        # Показываем номер в правильном формате - Telegram автоматически сделает его кликабельным
        # При клике на номер откроется набор номера в телефоне с уже введенным номером
        lines.append(f"\n📱 <b>{t('contact_phone', lang)}:</b> {phone_clean}")
        # Не добавляем кнопку - Telegram автоматически распознает номер и сделает его кликабельным
    if SUPPORT_WHATSAPP:
        has_any = True
        wa_link = SUPPORT_WHATSAPP
        if not wa_link.startswith("http"):
            wa_num = wa_link.replace(" ", "").replace("-", "").replace("+", "").replace("(", "").replace(")", "")
            if not wa_num.startswith("992"):
                wa_num = "992" + wa_num.lstrip("0")
            wa_link = f"https://wa.me/{wa_num}"
        lines.append(f"\n💚 <b>WhatsApp:</b> {SUPPORT_WHATSAPP}")
        builder.row(InlineKeyboardButton(text="💚 WhatsApp", url=wa_link))
    if SUPPORT_INSTAGRAM:
        has_any = True
        ig_link = SUPPORT_INSTAGRAM
        if not ig_link.startswith("http"):
            if ig_link.startswith("@"):
                ig_link = f"https://instagram.com/{ig_link[1:]}"
            else:
                ig_link = f"https://instagram.com/{ig_link}"
        lines.append(f"\n📷 <b>Instagram:</b> {SUPPORT_INSTAGRAM}")
        builder.row(InlineKeyboardButton(text="📷 Instagram", url=ig_link))
    if not has_any:
        text = t("contact_no_link", lang)
        builder = None
    else:
        text = "\n".join(lines)
        builder.row(_btn_home(lang))
        builder = builder.as_markup()
    await _safe_edit_text(
        callback.message,
        text,
        reply_markup=builder or build_main_keyboard(callback.from_user.id if callback.from_user else 0, lang),
    )
    await callback.answer()


@router.callback_query(F.data == "search")
async def on_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    lang = await _get_lang(callback.from_user.id)
    await state.set_state(SearchStates.waiting_query)
    await _safe_edit_text(
        callback.message,
        t("search_placeholder", lang),
    )
    await callback.answer()


@router.callback_query(F.data == "my_favorites")
async def on_my_favorites(callback: CallbackQuery) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    lang = await _get_lang(callback.from_user.id)
    db = get_db()
    products = await db.get_favorites_products(callback.from_user.id)
    if not products:
        await _safe_edit_text(
            callback.message,
            t("favorites_empty", lang),
            reply_markup=build_main_keyboard(callback.from_user.id, lang),
        )
        await callback.answer()
        return
    from utils.keyboards import build_products_keyboard
    category = products[0].get("category", "")
    await _safe_edit_text(
        callback.message,
        f"⭐ <b>{t('favorites_title', lang)}</b>\n\n{t('choose_laptop', lang)}",
        reply_markup=build_products_keyboard(products, category or "gaming", lang=lang),
    )
    await callback.answer()


@router.callback_query(F.data == "settings")
async def on_settings(callback: CallbackQuery) -> None:
    lang = await _get_lang(callback.from_user.id if callback.from_user else 0)
    await _safe_edit_text(
        callback.message,
        f"{t('settings_title', lang)}\n\n{t('settings_lang', lang)}",
        reply_markup=build_lang_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_lang:"))
async def on_set_lang(callback: CallbackQuery) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    lang_code = callback.data.split(":", 1)[1]
    if lang_code not in ("ru", "tg"):
        lang_code = "ru"
    db = get_db()
    await db.set_user_lang(callback.from_user.id, lang_code)
    msg = t("lang_changed_ru", lang_code) if lang_code == "ru" else t("lang_changed_tg", lang_code)
    await _safe_edit_text(
        callback.message,
        msg,
        reply_markup=build_main_keyboard(callback.from_user.id, lang_code),
    )
    await callback.answer()


async def _show_category_products(
    callback: CallbackQuery,
    category: str,
    sort: str = "price_asc",
    lang: str = "ru",
) -> None:
    db = get_db()
    products = await db.get_products(category=category)
    label = CATEGORY_LABELS.get(category, category)
    if not products:
        await _safe_edit_text(
            callback.message,
            f"📂 <b>{label}</b>\n\n{t('category_empty', lang)}",
            reply_markup=build_back_to_home_keyboard(lang),
        )
        return
    count = len(products)
    count_text = f" ({count} {t('products_count', lang)})"
    await _safe_edit_text(
        callback.message,
        f"📂 <b>{label}{count_text}</b>\n\n{t('choose_laptop', lang)}",
        reply_markup=build_products_keyboard(products, category, sort=sort, lang=lang),
    )


@router.callback_query(F.data.startswith("cat:"))
async def on_category(callback: CallbackQuery) -> None:
    lang = await _get_lang(callback.from_user.id if callback.from_user else 0)
    category = callback.data.split(":", 1)[1]
    await _show_category_products(callback, category, sort="price_asc", lang=lang)
    await callback.answer()


@router.callback_query(F.data.startswith("products:"))
async def on_products_sort(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    lang = await _get_lang(callback.from_user.id if callback.from_user else 0)
    _, category, sort = parts
    await _show_category_products(callback, category, sort=sort, lang=lang)
    await callback.answer()


def _product_caption(product: dict, cat_label: str, lang: str = "ru") -> str:
    title = product.get("title", "")
    price = product.get("price", 0)
    desc = (product.get("description") or "—")[:380]
    stock = int(product.get("stock", 0) or 0)
    if stock > 0:
        stock_str = t("product_stock", lang, n=stock)
        if stock <= 2:
            stock_str += "\n" + t("product_stock_urgent", lang)
    else:
        stock_str = t("product_out_of_stock", lang)
    try:
        price_str = f"{int(price):,} сомони".replace(",", " ")
    except (TypeError, ValueError):
        price_str = str(price)
    text = (
        f"🖥 <b>{title}</b>\n\n"
        f"📂 {cat_label}\n"
        f"💰 <b>{price_str}</b>\n"
        f"{stock_str}\n\n"
        f"{desc}\n\n"
        f"{t('product_delivery', lang)}"
    )
    if len(text) > 1020:
        text = text[:1017] + "..."
    return text.replace(",", " ")


@router.callback_query(F.data.startswith("product:"))
async def on_product(callback: CallbackQuery) -> None:
    product_id = int(callback.data.split(":", 1)[1])
    lang = await _get_lang(callback.from_user.id if callback.from_user else 0)
    db = get_db()
    product = await db.get_product(product_id)
    if not product:
        await callback.answer(t("product_not_found", lang), show_alert=True)
        return
    cat = product.get("category", "")
    cat_label = CATEGORY_LABELS.get(cat, cat)
    caption = _product_caption(product, cat_label, lang)
    in_stock = (int(product.get("stock", 0) or 0)) > 0
    admin = callback.from_user and is_admin(callback.from_user.id)
    is_fav = callback.from_user and await db.is_favorite(callback.from_user.id, product_id)
    keyboard = build_product_detail_keyboard(
        product_id, in_stock=in_stock, is_admin=admin, lang=lang, is_favorite=is_fav
    )
    image_id = product.get("image_file_id")
    video_id = product.get("video_file_id")
    try:
        await callback.message.delete()
        has_media = image_id or video_id
        if has_media:
            # Если есть и фото и видео — отправляем оба: сначала фото, потом видео с клавиатурой
            if image_id and video_id:
                await callback.message.answer_photo(
                    photo=image_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
                await callback.message.answer_video(
                    video=video_id,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
            elif video_id:
                await callback.message.answer_video(
                    video=video_id,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
            else:
                await callback.message.answer_photo(
                    photo=image_id,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
        else:
            await callback.message.answer(
                caption,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
    except Exception:
        try:
            await callback.message.answer(
                caption,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_fav:"))
async def on_toggle_favorite(callback: CallbackQuery) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    product_id = int(callback.data.split(":", 1)[1])
    lang = await _get_lang(callback.from_user.id)
    db = get_db()
    product = await db.get_product(product_id)
    if not product:
        await callback.answer(t("product_not_found", lang), show_alert=True)
        return
    is_fav = await db.is_favorite(callback.from_user.id, product_id)
    if is_fav:
        await db.remove_favorite(callback.from_user.id, product_id)
        is_fav = False
    else:
        await db.add_favorite(callback.from_user.id, product_id)
        is_fav = True
    in_stock = (int(product.get("stock", 0) or 0)) > 0
    admin = is_admin(callback.from_user.id)
    keyboard = build_product_detail_keyboard(
        product_id, in_stock=in_stock, is_admin=admin, lang=lang, is_favorite=is_fav
    )
    try:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("review:"))
async def on_review_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Начать ввод отзыва по заказу."""
    if not callback.from_user:
        await callback.answer()
        return
    try:
        order_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer()
        return
    lang = await _get_lang(callback.from_user.id)
    await state.set_state(ReviewStates.waiting_text)
    await state.update_data(review_order_id=order_id)
    await _safe_edit_text(
        callback.message,
        t("review_prompt", lang),
    )
    await callback.answer()


@router.message(SearchStates.waiting_query, F.text)
async def on_search_query(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    lang = await _get_lang(message.from_user.id)
    query = (message.text or "").strip()
    await state.clear()
    if len(query) < 2:
        await message.answer(
            t("search_empty", lang),
            reply_markup=build_main_keyboard(message.from_user.id, lang),
            parse_mode=ParseMode.HTML,
        )
        return
    db = get_db()
    products = await db.get_products(search=query)
    if not products:
        await message.answer(
            t("search_empty", lang),
            reply_markup=build_main_keyboard(message.from_user.id, lang),
            parse_mode=ParseMode.HTML,
        )
        return
    category = products[0].get("category", "gaming")
    await message.answer(
        f"🔍 <b>{t('catalog_title', lang)}</b>\n\n{t('choose_laptop', lang)}",
        reply_markup=build_products_keyboard(products, category, lang=lang),
        parse_mode=ParseMode.HTML,
    )


@router.message(ReviewStates.waiting_text, F.text)
async def on_review_text(message: Message, state: FSMContext) -> None:
    """Сохранить отзыв и выйти из состояния."""
    if not message.from_user:
        return
    lang = await _get_lang(message.from_user.id)
    data = await state.get_data()
    order_id = data.get("review_order_id")
    text = (message.text or "").strip()[:2000]
    if not text:
        await message.answer(t("review_prompt", lang))
        return
    await get_db().add_review(message.from_user.id, text, order_id=order_id)
    await state.clear()
    await message.answer(
        t("review_thanks", lang),
        reply_markup=build_main_keyboard(message.from_user.id, lang),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data.startswith("order_product:"))
async def on_order_product(callback: CallbackQuery, state: FSMContext) -> None:
    from обработчики.order_handlers import OrderStates

    product_id = int(callback.data.split(":", 1)[1])
    db = get_db()
    stock = await db.get_product_stock(product_id)
    
    lang = await _get_lang(callback.from_user.id if callback.from_user else 0)
    if stock <= 0:
        await callback.answer(t("order_out_of_stock", lang), show_alert=True)
        return

    product = await db.get_product(product_id)
    product_title = product.get("title", t("product_default", lang)) if product else t("product_default", lang)
    await state.set_state(OrderStates.waiting_fio)
    await state.update_data(product_id=product_id, product_title=product_title)

    from utils.keyboards import build_order_cancel_keyboard

    text = f"🛒 <b>{t('order_checkout_title', lang)}</b>\n\n<i>{product_title}</i>\n\n<b>{t('order_step', lang, step=1)}</b> — {t('order_fio', lang)}"
    cancel_kb = build_order_cancel_keyboard(lang)

    if callback.message.photo or callback.message.video:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=cancel_kb)
    else:
        await _safe_edit_text(callback.message, text, reply_markup=cancel_kb)
    await callback.answer()



@router.callback_query(F.data.startswith("notify_stock:"))
async def on_notify_stock(callback: CallbackQuery) -> None:
    lang = await _get_lang(callback.from_user.id if callback.from_user else 0)
    await callback.answer(t("notify_thanks", lang), show_alert=True)


@router.callback_query(F.data.startswith("delete_product:"))
async def on_delete_product_ask(callback: CallbackQuery) -> None:
    if not callback.from_user or not is_admin(callback.from_user.id):
        lang = await _get_lang(callback.from_user.id if callback.from_user else 0)
        await callback.answer(t("admin_only", lang), show_alert=True)
        return
    lang = await _get_lang(callback.from_user.id)
    product_id = int(callback.data.split(":", 1)[1])
    db = get_db()
    product = await db.get_product(product_id)
    if not product:
        await callback.answer(t("product_not_found", lang), show_alert=True)
        return
    title = product.get("title", t("product_default", lang))
    try:
        await _safe_edit_caption(
            callback.message,
            caption=f"🗑 <b>{t('delete_confirm_title', lang)}</b>\n\n«{title}»",
            reply_markup=build_delete_confirm_keyboard(product_id, lang),
        )
    except Exception:
        await _safe_edit_text(
            callback.message,
            f"🗑 <b>{t('delete_confirm_title', lang)}</b>\n\n«{title}»",
            reply_markup=build_delete_confirm_keyboard(product_id, lang),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_product_yes:"))
async def on_delete_product_confirm(callback: CallbackQuery) -> None:
    if not callback.from_user or not is_admin(callback.from_user.id):
        lang = await _get_lang(callback.from_user.id if callback.from_user else 0)
        await callback.answer(t("admin_only", lang), show_alert=True)
        return
    lang = await _get_lang(callback.from_user.id)
    product_id = int(callback.data.split(":", 1)[1])
    db = get_db()
    ok = await db.delete_product(product_id)
    if not ok:
        await callback.answer(t("product_not_found_deleted", lang), show_alert=True)
        return
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "✅ " + t("product_deleted", lang),
        reply_markup=build_catalog_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data == "order_start")
async def on_order_start(callback: CallbackQuery, state) -> None:
    lang = await _get_lang(callback.from_user.id if callback.from_user else 0)
    await _safe_edit_text(
        callback.message,
        t("order_start_hint", lang),
        reply_markup=build_catalog_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(F.data == "my_orders")
async def on_my_orders(callback: CallbackQuery) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    lang = await _get_lang(callback.from_user.id)
    db = get_db()
    orders = await db.get_orders_by_user(callback.from_user.id)
    if not orders:
        from обработчики.commands import _first_name
        name = _first_name(callback.from_user) or ""
        msg = f"{t('my_orders_empty', lang)}{', ' + name if name else ''}."
        await _safe_edit_text(
            callback.message,
            msg,
            reply_markup=build_my_orders_keyboard(lang),
        )
        await callback.answer()
        return
    STATUS_HINTS = {
        "new": t("order_status_new", lang),
        "awaiting_payment": t("order_status_awaiting", lang),
        "receipt_received": t("order_status_receipt", lang),
        "paid": t("order_status_paid", lang),
        "shipped": t("order_status_shipped", lang),
    }
    lines = []
    for o in orders:
        prod = await db.get_product(o["product_id"])
        title = prod["title"] if prod else f"#{o['product_id']}"
        st = STATUS_LABELS.get(o["status"], o["status"])
        hint = STATUS_HINTS.get(o["status"], "")
        lines.append(f"• <b>{o['order_number']}</b> — {title}\n  📌 {st}\n  <i>{hint}</i>")
    text = f"📋 <b>{t('btn_my_orders', lang)}</b>\n\n" + "\n\n".join(lines)
    await _safe_edit_text(
        callback.message,
        text,
        reply_markup=build_my_orders_keyboard(orders, lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("order_detail:"))
async def on_order_detail(callback: CallbackQuery) -> None:
    """Показать детали заказа."""
    if not callback.from_user:
        await callback.answer()
        return
    try:
        order_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer()
        return
    lang = await _get_lang(callback.from_user.id)
    db = get_db()
    order = await db.get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer(t("order_not_found", lang), show_alert=True)
        return
    product = await db.get_product(order["product_id"])
    product_title = product["title"] if product else f"#{order['product_id']}"
    product_price = product["price"] if product else 0
    
    # Форматируем дату
    from datetime import datetime
    try:
        created_at = datetime.fromisoformat(order.get("created_at", "")).strftime("%d.%m.%Y %H:%M")
    except:
        created_at = order.get("created_at", "—")
    
    status_label = STATUS_LABELS.get(order["status"], order["status"])
    status_hints = {
        "new": t("order_status_new", lang),
        "awaiting_payment": t("order_status_awaiting", lang),
        "receipt_received": t("order_status_receipt", lang),
        "paid": t("order_status_paid", lang),
        "shipped": t("order_status_shipped", lang),
    }
    status_hint = status_hints.get(order["status"], "")
    
    from config import PAYMENT_REQUISITES
    
    text = (
        f"📄 <b>{t('order_details_title', lang)}</b>\n\n"
        f"<b>{t('order_number_label', lang)}:</b> {order['order_number']}\n"
        f"<b>{t('order_status_label', lang)}:</b> {status_label}\n"
        f"<i>{status_hint}</i>\n\n"
        f"<b>{t('order_product_label', lang)}:</b> {product_title}\n"
        f"<b>{t('order_price_label', lang)}:</b> {product_price:,} сомони\n\n"
        f"<b>{t('order_date_label', lang)}:</b> {created_at}\n\n"
        f"<b>{t('order_delivery_label', lang)}:</b>\n"
        f"📍 {order['city']}, {order['address']}\n"
        f"👤 {order['full_name']}\n"
        f"📱 {order['phone']}\n"
    )
    
    # Добавляем реквизиты для оплаты, если заказ еще не оплачен
    if order["status"] in ("new", "awaiting_payment"):
        text += f"\n<b>{t('order_payment_info', lang)}:</b>\n{PAYMENT_REQUISITES}"
    
    text = text.replace(",", " ")
    
    await _safe_edit_text(
        callback.message,
        text,
        reply_markup=build_order_detail_keyboard(order_id, order["status"], lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("reorder:"))
async def on_reorder(callback: CallbackQuery, state: FSMContext) -> None:
    """Повторить заказ."""
    if not callback.from_user:
        await callback.answer()
        return
    try:
        order_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer()
        return
    lang = await _get_lang(callback.from_user.id)
    db = get_db()
    order = await db.get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer(t("order_not_found", lang), show_alert=True)
        return
    product_id = order["product_id"]
    product = await db.get_product(product_id)
    if not product:
        await callback.answer(t("product_not_found", lang), show_alert=True)
        return
    stock = await db.get_product_stock(product_id)
    if stock <= 0:
        await callback.answer(t("order_out_of_stock", lang), show_alert=True)
        return
    # Начинаем процесс заказа с теми же данными
    from обработчики.order_handlers import OrderStates
    product_title = product.get("title", t("product_default", lang))
    await state.set_state(OrderStates.waiting_fio)
    await state.update_data(
        product_id=product_id,
        product_title=product_title,
        reorder=True,
        last_fio=order["full_name"],
        last_phone=order["phone"],
        last_city=order["city"],
        last_address=order["address"],
    )
    from utils.keyboards import build_order_cancel_keyboard
    text = (
        f"🔄 <b>{t('order_reorder_started', lang)}</b>\n\n"
        f"<i>{product_title}</i>\n\n"
        f"<b>{t('order_step', lang, step=1)}</b> — {t('order_fio', lang)}\n"
        f"💡 <i>Можно использовать данные из предыдущего заказа</i>"
    )
    await _safe_edit_text(
        callback.message,
        text,
        reply_markup=build_order_cancel_keyboard(lang),
    )
    await callback.answer()


# ——— Админ: смена статуса заказа по кнопкам в уведомлении ———
@router.callback_query(F.data.startswith("admin_order_receipt:"))
async def admin_order_receipt(callback: CallbackQuery, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав", show_alert=True)
        return
    order_id = int(callback.data.split(":", 1)[1])
    await get_db().set_order_status(order_id, "receipt_received")
    await callback.answer("Статус: Чек получен")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("admin_order_paid:"))
async def admin_order_paid(callback: CallbackQuery, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав", show_alert=True)
        return
    order_id = int(callback.data.split(":", 1)[1])
    db = get_db()
    await db.set_order_status(order_id, "paid")
    order = await db.get_order(order_id)
    if order:
        await notify_client_order_status(bot, order, "paid")
    await callback.answer("Статус: Оплачен")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("admin_order_shipped:"))
async def admin_order_shipped(callback: CallbackQuery, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав", show_alert=True)
        return
    order_id = int(callback.data.split(":", 1)[1])
    db = get_db()
    await db.set_order_status(order_id, "shipped")
    order = await db.get_order(order_id)
    if order:
        await notify_client_order_status(bot, order, "shipped")
    await callback.answer("Статус: Отправлен")
    await callback.message.edit_reply_markup(reply_markup=None)
