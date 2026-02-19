"""Улучшенные клавиатуры для магазина ноутбуков."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db import CATEGORY_GAMING, CATEGORY_STUDY, CATEGORY_WORK
from utils.locales import t

def _btn_home(lang: str = "ru"):
    return InlineKeyboardButton(text=t("btn_home", lang), callback_data="home")

def _btn_catalog(lang: str = "ru"):
    return InlineKeyboardButton(text=t("btn_back_catalog", lang), callback_data="catalog")

def build_main_keyboard(user_id: int = 0, lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("btn_catalog", lang), callback_data="catalog"))
    builder.row(InlineKeyboardButton(text=t("btn_ai", lang), callback_data="ai_consult"))
    builder.row(
        InlineKeyboardButton(text=t("btn_how_order", lang), callback_data="order_start"),
        InlineKeyboardButton(text=t("btn_my_orders", lang), callback_data="my_orders"),
    )
    builder.row(
        InlineKeyboardButton(text=t("btn_faq", lang), callback_data="faq"),
        InlineKeyboardButton(text=t("btn_contacts", lang), callback_data="contacts"),
    )
    builder.row(
        InlineKeyboardButton(text=t("btn_favorites", lang), callback_data="my_favorites"),
        InlineKeyboardButton(text=t("btn_search", lang), callback_data="search"),
    )
    builder.row(InlineKeyboardButton(text=t("btn_settings", lang), callback_data="settings"))
    return builder.as_markup()

def build_catalog_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # Кнопки категорий в одну строку для компактности
    builder.row(
        InlineKeyboardButton(text=t("cat_gaming", lang), callback_data=f"cat:{CATEGORY_GAMING}"),
        InlineKeyboardButton(text=t("cat_study", lang), callback_data=f"cat:{CATEGORY_STUDY}"),
    )
    builder.row(InlineKeyboardButton(text=t("cat_work", lang), callback_data=f"cat:{CATEGORY_WORK}"))
    builder.row(_btn_home(lang))
    return builder.as_markup()

# Сортировка и вид списка товаров
SORT_PRICE_ASC = "price_asc"
SORT_PRICE_DESC = "price_desc"
SORT_TITLE = "title_asc"
SORT_ID = "id"
VIEW_LIST = "list"
VIEW_TILE = "tile"


def _sort_products(products: list, sort: str) -> list:
    """Сортировка списка товаров. Не изменяет исходный список."""
    key_map = {
        SORT_PRICE_ASC: lambda p: (int(p.get("price") or 0), p.get("title", "")),
        SORT_PRICE_DESC: lambda p: (-int(p.get("price") or 0), p.get("title", "")),
        SORT_TITLE: lambda p: (p.get("title", "").lower(), int(p.get("price") or 0)),
        SORT_ID: lambda p: (int(p.get("id") or 0),),
    }
    key = key_map.get(sort, key_map[SORT_ID])
    return sorted(products, key=key)


def build_products_keyboard(
    products: list,
    category: str,
    sort: str = SORT_PRICE_ASC,
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    sorted_list = _sort_products(products, sort)
    builder = InlineKeyboardBuilder()
    for p in sorted_list:
        stock = int(p.get("stock", 0) or 0)
        icon = "✅" if stock > 0 else "❌"
        price = f"{int(p.get('price', 0)):,}".replace(",", " ")
        title = (p.get("title") or ("Без названия" if lang == "ru" else "Без ном"))
        # Улучшенное форматирование в одну строку: название, цена, остаток
        if stock > 0:
            stock_txt = f" • {stock} шт" if lang == "ru" else f" • {stock}"
            btn_text = f"{icon} {title} • {price} сом{stock_txt}"
        else:
            btn_text = f"{icon} {title} • {price} сом • Нет в наличии"
        builder.add(InlineKeyboardButton(
            text=btn_text,
            callback_data=f"product:{p['id']}"
        ))
    builder.row(
        InlineKeyboardButton(text=t("sort_cheaper", lang), callback_data=f"products:{category}:{SORT_PRICE_ASC}"),
        InlineKeyboardButton(text=t("sort_dearer", lang), callback_data=f"products:{category}:{SORT_PRICE_DESC}"),
        InlineKeyboardButton(text=t("sort_name", lang), callback_data=f"products:{category}:{SORT_TITLE}"),
    )
    builder.row(_btn_catalog(lang), _btn_home(lang), width=2)
    return builder.as_markup()

def build_product_detail_keyboard(
    product_id: int,
    in_stock: bool = True,
    is_admin: bool = False,
    lang: str = "ru",
    is_favorite: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if in_stock:
        builder.row(InlineKeyboardButton(
            text=t("btn_order_product", lang),
            callback_data=f"order_product:{product_id}",
        ))
    else:
        builder.row(InlineKeyboardButton(
            text=t("btn_notify_stock", lang),
            callback_data=f"notify_stock:{product_id}",
        ))
    builder.row(InlineKeyboardButton(
        text=(t("btn_remove_favorite", lang) if is_favorite else t("btn_add_favorite", lang)),
        callback_data=f"toggle_fav:{product_id}",
    ))
    if is_admin:
        builder.row(InlineKeyboardButton(
            text=t("btn_delete_product", lang),
            callback_data=f"delete_product:{product_id}",
        ))
    builder.row(_btn_catalog(lang), _btn_home(lang), width=2)
    return builder.as_markup()

def build_back_to_home_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(_btn_home(lang))
    return builder.as_markup()

def build_delete_confirm_keyboard(product_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t("btn_yes_delete", lang), callback_data=f"delete_product_yes:{product_id}"),
        InlineKeyboardButton(text=t("btn_no", lang), callback_data=f"product:{product_id}"),
    )
    return builder.as_markup()

def build_my_orders_keyboard(orders: list = None, lang: str = "ru") -> InlineKeyboardMarkup:
    """Создает клавиатуру для списка заказов с кнопками для каждого заказа."""
    builder = InlineKeyboardBuilder()
    if orders:
        for order in orders:
            order_id = order.get("id")
            order_number = order.get("order_number", "")
            status = order.get("status", "")
            # Кнопка "Детали заказа" для каждого заказа
            builder.row(
                InlineKeyboardButton(
                    text=f"📄 {order_number}",
                    callback_data=f"order_detail:{order_id}"
                )
            )
            # Для отправленных заказов добавляем кнопку "Оставить отзыв"
            if status == "shipped":
                builder.row(
                    InlineKeyboardButton(
                        text=t("btn_review", lang),
                        callback_data=f"review:{order_id}"
                    )
                )
    builder.row(InlineKeyboardButton(text=t("btn_refresh", lang), callback_data="my_orders"))
    builder.row(_btn_home(lang))
    return builder.as_markup()


def build_order_detail_keyboard(order_id: int, status: str, lang: str = "ru") -> InlineKeyboardMarkup:
    """Создает клавиатуру для деталей заказа."""
    builder = InlineKeyboardBuilder()
    # Кнопка "Повторить заказ" для всех статусов кроме "new"
    if status != "new":
        builder.row(
            InlineKeyboardButton(
                text=t("btn_reorder", lang),
                callback_data=f"reorder:{order_id}"
            )
        )
    # Для отправленных заказов добавляем кнопку "Оставить отзыв"
    if status == "shipped":
        builder.row(
            InlineKeyboardButton(
                text=t("btn_review", lang),
                callback_data=f"review:{order_id}"
            )
        )
    builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data="my_orders"))
    builder.row(_btn_home(lang))
    return builder.as_markup()

def build_order_cancel_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("btn_cancel_order", lang), callback_data="order_cancel"))
    return builder.as_markup()

def build_lang_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang:ru"),
        InlineKeyboardButton(text="🇹🇯 Тоҷикӣ", callback_data="set_lang:tg"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="home"))
    return builder.as_markup()
