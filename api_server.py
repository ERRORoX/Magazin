"""
HTTP API для админ-панели: заказы, товары, просмотр чека.
Вход: имя пользователя + секретный ключ (один раз). Токен в X-Admin-Token (JWT или legacy ADMIN_SECRET).
"""
import base64
import csv
import hashlib
import hmac
import io
import json
import logging
import os
import time
from pathlib import Path

import aiohttp
from aiohttp import web

from config import APP_ROOT
from database import get_db
from database.db import STATUS_LABELS, CATEGORY_LABELS
from services.notification_service import get_admin_ids

ADMIN_FOLDER = APP_ROOT / "admin"
JWT_EXP_DAYS = 7

# Отключаем access логи aiohttp (они слишком шумные)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


def _jwt_secret() -> bytes:
    s = os.getenv("ADMIN_SECRET", "master_nosirov_jwt")
    return s.encode() if isinstance(s, str) else s


def _create_jwt(user_id: int, username: str) -> str:
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": int(time.time()) + JWT_EXP_DAYS * 86400,
    }
    b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(_jwt_secret(), b64.encode(), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def _verify_jwt(token: str) -> dict | None:
    try:
        if "." not in token:
            return None
        b64, sig = token.rsplit(".", 1)
        pad = 4 - len(b64) % 4
        if pad != 4:
            b64 += "=" * pad
        payload_b = base64.urlsafe_b64decode(b64)
        expected = hmac.new(_jwt_secret(), b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(payload_b)
        if data.get("exp", 0) < int(time.time()):
            return None
        return data
    except Exception:
        return None


def _check_token(request: web.Request) -> bool:
    """Проверка: JWT или legacy ADMIN_SECRET."""
    raw = request.headers.get("X-Admin-Token") or request.query.get("token", "")
    raw = raw.strip()
    if not raw:
        return False
    if "." in raw:
        return _verify_jwt(raw) is not None
    secret = os.getenv("ADMIN_SECRET", "")
    if not secret:
        return True
    return raw == secret.strip()


def _get_client_ip(request: web.Request) -> str:
    """IP клиента (учёт X-Forwarded-For при прокси)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.remote:
        return request.remote
    return ""


def _check_allowed_ip(request: web.Request) -> bool:
    """Если задан ADMIN_ALLOWED_IPS — доступ только с этих IP. Иначе разрешено всем."""
    allowed = os.getenv("ADMIN_ALLOWED_IPS", "").strip()
    if not allowed:
        return True
    client_ip = _get_client_ip(request)
    if not client_ip:
        return False
    allowed_list = [a.strip() for a in allowed.split(",") if a.strip()]
    return client_ip in allowed_list


async def _require_admin(request: web.Request) -> web.Response | None:
    if not _check_token(request):
        return web.json_response({"error": "Forbidden"}, status=403)
    if not _check_allowed_ip(request):
        return web.json_response({"error": "Forbidden: IP not allowed"}, status=403)
    return None


def _row_to_dict(row):
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row) if hasattr(row, "keys") else row


# Rate limit для логина: по IP, 5 попыток в минуту
_login_attempts: dict = {}  # ip -> list of timestamps
LOGIN_RATE_LIMIT = 5
LOGIN_RATE_WINDOW = 60  # seconds


def _check_login_rate_limit(ip: str) -> bool:
    now = time.time()
    if ip not in _login_attempts:
        _login_attempts[ip] = []
    times = _login_attempts[ip]
    times[:] = [t for t in times if now - t < LOGIN_RATE_WINDOW]
    if len(times) >= LOGIN_RATE_LIMIT:
        return False
    times.append(now)
    return True


# ——— Авторизация ———
async def api_auth_login(request: web.Request) -> web.Response:
    """POST { "username": "...", "secret_key": "..." } -> { "token": "jwt..." }."""
    ip = _get_client_ip(request)
    if not _check_login_rate_limit(ip):
        return web.json_response(
            {"error": "Слишком много попыток входа. Подождите минуту."},
            status=429,
        )
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    username = (body.get("username") or "").strip()
    secret_key = body.get("secret_key") or ""
    if not username or not secret_key:
        return web.json_response({"error": "Укажите имя пользователя и секретный ключ"}, status=400)
    db = get_db()
    user_id = await db.verify_admin_user(username, secret_key)
    if not user_id:
        return web.json_response({"error": "Неверное имя пользователя или ключ"}, status=401)
    token = _create_jwt(user_id, username)
    return web.json_response({"token": token, "username": username})


async def api_admin_users_list(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    db = get_db()
    users = await db.list_admin_users()
    for u in users:
        u.pop("secret_key_hash", None)
    return web.json_response(users)


async def api_admin_users_create(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    username = (body.get("username") or "").strip()
    secret_key = body.get("secret_key") or body.get("password") or ""
    if not username:
        return web.json_response({"error": "Укажите имя пользователя"}, status=400)
    if len(secret_key) < 4:
        return web.json_response({"error": "Секретный ключ не менее 4 символов"}, status=400)
    db = get_db()
    uid = await db.create_admin_user(username, secret_key)
    if not uid:
        return web.json_response({"error": "Пользователь с таким именем уже есть"}, status=409)
    return web.json_response({"id": uid, "username": username}, status=201)


async def api_admin_users_delete(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    try:
        user_id = int(request.match_info["id"])
    except (ValueError, KeyError):
        return web.json_response({"error": "Invalid id"}, status=400)
    db = get_db()
    ok = await db.delete_admin_user(user_id)
    if not ok:
        return web.json_response({"error": "Пользователь не найден"}, status=404)
    return web.Response(status=204)


# ——— Настройки (.env) ———
ENV_PATH = APP_ROOT / ".env"
ENV_KEYS = [
    # group "env" — переменные окружения
    ("TELEGRAM_BOT_TOKEN", "Токен бота Telegram", True, "env"),
    ("ADMIN_IDS", "ID админов через запятую", False, "env"),
    ("ADMIN_SECRET", "Секретный ключ входа в админку", True, "env"),
    ("ADMIN_PORT", "Порт админ-панели (8080)", False, "env"),
    ("ADMIN_HOST", "Хост (оставьте пусто — только этот ПК)", False, "env"),
    ("ADMIN_ALLOWED_IPS", "Разрешённые IP через запятую (пусто = все)", False, "env"),
    ("STORAGE_CHAT_ID", "Чат для файлов товаров (пусто = в личку админу)", False, "env"),
    ("OPENROUTER_API_KEY", "Ключ OpenRouter (AI-консультант)", True, "env"),
    ("PAYMENT_REQUISITES", "Реквизиты для оплаты (карта и т.д.)", False, "env"),
    ("SUPPORT_TELEGRAM", "Telegram (t.me/username или @username)", False, "env"),
    ("SUPPORT_PHONE", "Номер телефона (+992...)", False, "env"),
    ("SUPPORT_WHATSAPP", "WhatsApp (номер или ссылка wa.me/...)", False, "env"),
    ("SUPPORT_INSTAGRAM", "Instagram (@username или ссылка)", False, "env"),
    # group "bot" — тексты бота
    ("BOT_WELCOME_MESSAGE", "Приветствие (при /start)", False, "bot"),
    ("BOT_ORDER_THANKS", "Текст после оформления заказа", False, "bot"),
    ("BOT_CATALOG_TITLE", "Заголовок каталога", False, "bot"),
]


def _read_env_lines():
    if not ENV_PATH.exists():
        return []
    try:
        return ENV_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []


def _parse_env():
    result = {}
    for line in _read_env_lines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            key = k.strip()
            val = v.strip()
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1].replace('\\"', '"')
            elif val.startswith("'") and val.endswith("'"):
                val = val[1:-1].replace("\\'", "'")
            result[key] = val
    return result


def _mask_val(key: str, value: str) -> str:
    if not value:
        return ""
    for ek, _, mask, _ in ENV_KEYS:
        if ek == key and mask:
            return "••••••••" + value[-4:] if len(value) > 4 else "••••"
    return value


async def api_settings_env_get(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    env = _parse_env()
    out = []
    for key, label, masked, group in ENV_KEYS:
        val = env.get(key, "")
        out.append({
            "key": key,
            "label": label,
            "value": _mask_val(key, val) if masked else val,
            "masked": masked,
            "group": group,
        })
    return web.json_response(out)


async def api_settings_env_put(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Неверный JSON"}, status=400)
    allowed = {k for k, _, _, _ in ENV_KEYS}
    updates = {k: (v if isinstance(v, str) else str(v)) for k, v in body.items() if k in allowed}
    if not updates:
        return web.json_response({"ok": True})
    env = _parse_env()
    env.update(updates)
    lines = _read_env_lines()
    new_lines = []
    replaced = set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _, _ = stripped.partition("=")
            key = k.strip()
            if key in updates:
                new_lines.append(f'{key}={env[key]}')
                replaced.add(key)
                continue
        new_lines.append(line)
    for key in updates:
        if key not in replaced:
            new_lines.append(f"{key}={env[key]}")
    try:
        ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except Exception as e:
        logging.exception("Write .env: %s", e)
        return web.json_response({"error": "Не удалось записать файл .env: " + str(e)}, status=500)
    return web.json_response({"ok": True, "message": "Перезапустите бота для применения изменений."})


async def api_settings_env_raw(request: web.Request) -> web.Response:
    """Вернуть реальное значение переменной (для показа по нажатию «глаз»)."""
    err = await _require_admin(request)
    if err:
        return err
    key = (request.query.get("key") or "").strip()
    if not key:
        return web.json_response({"error": "Укажите key"}, status=400)
    allowed_masked = {k for k, _, m, _ in ENV_KEYS if m}
    if key not in allowed_masked:
        return web.json_response({"error": "Ключ не найден или не секретный"}, status=400)
    env = _parse_env()
    value = env.get(key, "")
    return web.json_response({"value": value})


# ——— Тексты бота (локали) ———
LOCALES_OVERRIDE_PATH = APP_ROOT / "locales_override.json"


def _load_locales_overrides():
    if not LOCALES_OVERRIDE_PATH.exists():
        return {}
    try:
        return json.loads(LOCALES_OVERRIDE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


async def api_settings_bot_texts_get(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    from utils.locales import TEXTS
    overrides = _load_locales_overrides()
    out = []
    for key in sorted(TEXTS.get("ru", {}).keys()):
        ru_val = overrides.get("ru", {}).get(key) or TEXTS.get("ru", {}).get(key) or ""
        tg_val = overrides.get("tg", {}).get(key) or TEXTS.get("tg", {}).get(key) or ""
        out.append({"key": key, "ru": ru_val, "tg": tg_val})
    return web.json_response(out)


async def api_settings_bot_texts_put(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Неверный JSON"}, status=400)
    from utils.locales import TEXTS
    overrides = _load_locales_overrides()
    ru_overrides = overrides.get("ru", {})
    tg_overrides = overrides.get("tg", {})
    for item in body.get("texts", []):
        key = (item.get("key") or "").strip()
        if not key or key not in TEXTS.get("ru", {}):
            continue
        if "ru" in item:
            ru_overrides[key] = item["ru"] if isinstance(item["ru"], str) else str(item["ru"])
        if "tg" in item:
            tg_overrides[key] = item["tg"] if isinstance(item["tg"], str) else str(item["tg"])
    data = {"ru": ru_overrides, "tg": tg_overrides}
    try:
        LOCALES_OVERRIDE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logging.exception("Write locales override: %s", e)
        return web.json_response({"error": "Не удалось записать файл: " + str(e)}, status=500)
    return web.json_response({"ok": True, "message": "Тексты сохранены. Перезапустите бота."})


# ——— Статика (админ-панель) ———
async def index(_request: web.Request) -> web.Response:
    path = ADMIN_FOLDER / "admin.html"
    if not path.exists():
        raise web.HTTPNotFound()
    return web.FileResponse(path)


ALLOWED_STATIC = {"admin.css", "admin.js"}


async def static_file(request: web.Request) -> web.Response:
    name = request.match_info.get("name", "")
    if name not in ALLOWED_STATIC:
        raise web.HTTPNotFound()
    path = ADMIN_FOLDER / name
    if not path.exists() or not path.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(path)


# ——— API: статистика ———
async def api_stats(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    db = get_db()
    orders = await db.get_all_orders()
    products = await db.get_products()
    by_status = {}
    for o in orders:
        s = o.get("status", "new")
        by_status[s] = by_status.get(s, 0) + 1
    orders_today = await db.get_orders_count_today()
    low_stock_count = await db.get_products_low_stock_count(2)
    out_of_stock_count = await db.get_products_out_of_stock_count()
    return web.json_response({
        "orders_total": len(orders),
        "products_total": len(products),
        "orders_by_status": by_status,
        "orders_today": orders_today,
        "low_stock_count": low_stock_count,
        "out_of_stock_count": out_of_stock_count,
    })


# ——— API: заказы ———
async def api_order_create(request: web.Request) -> web.Response:
    """POST /api/orders — создать заказ вручную."""
    err = await _require_admin(request)
    if err:
        return err
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    user_id = body.get("user_id")
    product_id = body.get("product_id")
    full_name = body.get("full_name", "").strip()
    phone = body.get("phone", "").strip()
    city = body.get("city", "").strip()
    address = body.get("address", "").strip()
    if not all([user_id, product_id, full_name, phone, city, address]):
        return web.json_response({"error": "Все поля обязательны"}, status=400)
    try:
        user_id = int(user_id)
        product_id = int(product_id)
    except (ValueError, TypeError):
        return web.json_response({"error": "user_id и product_id должны быть числами"}, status=400)
    db = get_db()
    product = await db.get_product(product_id)
    if not product:
        return web.json_response({"error": "Товар не найден"}, status=404)
    order = await db.create_order(
        user_id=user_id,
        product_id=product_id,
        full_name=full_name,
        phone=phone,
        city=city,
        address=address,
    )
    return web.json_response(_row_to_dict(order), status=201)


def _parse_period(period: str) -> tuple:
    """period=today|week|month -> (date_from, date_to) или (None, None)."""
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    if period == "today":
        d = now.strftime("%Y-%m-%d")
        return (d, d)
    if period == "week":
        start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        return (start, now.strftime("%Y-%m-%d"))
    if period == "month":
        start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        return (start, now.strftime("%Y-%m-%d"))
    return (None, None)


async def api_orders_list(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    db = get_db()
    status = request.query.get("status")
    search = request.query.get("search", "").strip() or None
    sort_order = request.query.get("sort", "desc")
    exclude_status = request.query.get("exclude_status")
    period = request.query.get("period", "").strip() or None
    date_from = request.query.get("date_from", "").strip() or None
    date_to = request.query.get("date_to", "").strip() or None
    if period and not date_from:
        date_from, date_to = _parse_period(period)
    limit = request.query.get("limit")
    offset = request.query.get("offset")
    if limit is not None:
        try:
            limit = int(limit)
            limit = min(max(1, limit), 500)
        except (ValueError, TypeError):
            limit = None
    if offset is not None:
        try:
            offset = int(offset)
            offset = max(0, offset)
        except (ValueError, TypeError):
            offset = None
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"
    orders = await db.get_all_orders(
        status=status or None,
        search=search,
        sort_order=sort_order,
        exclude_status=exclude_status or None,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    out = []
    for o in orders:
        row = _row_to_dict(o)
        product = await db.get_product(o["product_id"])
        row["product_title"] = product["title"] if product else ""
        row["product_price"] = product["price"] if product else 0
        row["status_label"] = STATUS_LABELS.get(o["status"], o["status"])
        out.append(row)
    return web.json_response(out)


async def api_orders_export(request: web.Request) -> web.Response:
    """Экспорт заказов в CSV (те же фильтры: status, search, exclude_status, period, date_from, date_to)."""
    err = await _require_admin(request)
    if err:
        return err
    db = get_db()
    status = request.query.get("status")
    search = request.query.get("search", "").strip() or None
    sort_order = request.query.get("sort", "desc")
    exclude_status = request.query.get("exclude_status")
    period = request.query.get("period", "").strip() or None
    date_from = request.query.get("date_from", "").strip() or None
    date_to = request.query.get("date_to", "").strip() or None
    if period and not date_from:
        date_from, date_to = _parse_period(period)
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"
    orders = await db.get_all_orders(
        status=status or None,
        search=search,
        sort_order=sort_order,
        exclude_status=exclude_status or None,
        date_from=date_from,
        date_to=date_to,
    )
    out = []
    for o in orders:
        row = _row_to_dict(o)
        product = await db.get_product(o["product_id"])
        row["product_title"] = product["title"] if product else ""
        row["product_price"] = product["price"] if product else 0
        row["status_label"] = STATUS_LABELS.get(o["status"], o["status"])
        out.append(row)
    buf = io.StringIO()
    if out:
        writer = csv.DictWriter(
            buf,
            fieldnames=[
                "id", "order_number", "full_name", "phone", "city", "address",
                "product_title", "product_price", "status", "status_label",
                "created_at", "updated_at",
            ],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(out)
    body = buf.getvalue().encode("utf-8-sig")
    return web.Response(
        body=body,
        headers={
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": 'attachment; filename="orders.csv"',
        },
    )


async def api_order_one(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    try:
        order_id = int(request.match_info["id"])
    except ValueError:
        raise web.HTTPBadRequest()
    db = get_db()
    order = await db.get_order(order_id)
    if not order:
        raise web.HTTPNotFound()
    row = _row_to_dict(order)
    product = await db.get_product(order["product_id"])
    row["product"] = _row_to_dict(product) if product else None
    row["status_label"] = STATUS_LABELS.get(order["status"], order["status"])
    return web.json_response(row)


async def api_order_status(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    try:
        order_id = int(request.match_info["id"])
    except ValueError:
        raise web.HTTPBadRequest()
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON")
    status = body.get("status")
    if not status or status not in STATUS_LABELS:
        return web.json_response({"error": "invalid status"}, status=400)
    db = get_db()
    order = await db.get_order(order_id)
    if not order:
        raise web.HTTPNotFound()
    await db.set_order_status(order_id, status)
    return web.json_response({"ok": True, "status": status})


async def api_order_receipt(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    try:
        order_id = int(request.match_info["id"])
    except ValueError:
        raise web.HTTPBadRequest()
    db = get_db()
    order = await db.get_order(order_id)
    if not order or not order.get("receipt_file_id"):
        raise web.HTTPNotFound()
    bot = request.app.get("bot")
    if not bot:
        return web.json_response({"file_id": order["receipt_file_id"], "message": "Open in Telegram bot"})
    try:
        file = await bot.get_file(order["receipt_file_id"])
        url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return web.json_response({"error": "Could not load image"}, status=502)
                body = await resp.read()
                content_type = resp.content_type or "image/jpeg"
        return web.Response(body=body, content_type=content_type)
    except Exception as e:
        logging.exception("Receipt image proxy: %s", e)
        return web.json_response({"error": "Could not get file"}, status=500)


async def api_order_delete(request: web.Request) -> web.Response:
    """Удалить заказ. Разрешено только для заказов со статусом «Отправлен»."""
    err = await _require_admin(request)
    if err:
        return err
    try:
        order_id = int(request.match_info["id"])
    except ValueError:
        raise web.HTTPBadRequest()
    db = get_db()
    ok = await db.delete_order(order_id, only_if_shipped=True)
    if not ok:
        order = await db.get_order(order_id)
        if not order:
            raise web.HTTPNotFound()
        return web.json_response(
            {"error": "Удалять можно только заказы со статусом «Отправлен»"},
            status=400,
        )
    return web.json_response({"ok": True})


# ——— API: товары ———
async def api_products_list(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    db = get_db()
    category = request.query.get("category")
    stock_filter = request.query.get("stock_filter")  # low | out
    if stock_filter not in ("low", "out"):
        stock_filter = None
    products = await db.get_products(category=category or None, stock_filter=stock_filter)
    out = []
    for p in products:
        row = _row_to_dict(p)
        row["category_label"] = CATEGORY_LABELS.get(p.get("category", ""), p.get("category", ""))
        out.append(row)
    return web.json_response(out)


async def api_product_one(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    try:
        product_id = int(request.match_info["id"])
    except ValueError:
        raise web.HTTPBadRequest()
    db = get_db()
    product = await db.get_product(product_id)
    if not product:
        raise web.HTTPNotFound()
    row = _row_to_dict(product)
    row["category_label"] = CATEGORY_LABELS.get(product.get("category", ""), product.get("category", ""))
    return web.json_response(row)


async def api_product_create(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON")
    title = body.get("title")
    price = body.get("price")
    category = body.get("category", "work")
    description = body.get("description", "")
    stock = body.get("stock", 0)
    if not title or price is None:
        return web.json_response({"error": "title and price required"}, status=400)
    try:
        price = int(price)
    except (TypeError, ValueError):
        return web.json_response({"error": "price must be number"}, status=400)
    try:
        stock = int(stock) if stock is not None else 0
    except (TypeError, ValueError):
        stock = 0
    db = get_db()
    pid = await db.add_product(title=title, price=price, category=category, description=description, stock=max(0, stock))
    product = await db.get_product(pid)
    return web.json_response(_row_to_dict(product), status=201)


async def api_product_update(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    try:
        product_id = int(request.match_info["id"])
    except ValueError:
        raise web.HTTPBadRequest()
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON")
    db = get_db()
    product = await db.get_product(product_id)
    if not product:
        raise web.HTTPNotFound()
    updates = {}
    if "title" in body:
        updates["title"] = body["title"]
    if "description" in body:
        updates["description"] = body["description"]
    if "price" in body:
        try:
            updates["price"] = int(body["price"])
        except (TypeError, ValueError):
            return web.json_response({"error": "price must be number"}, status=400)
    if "category" in body:
        updates["category"] = body["category"]
    if "stock" in body:
        try:
            updates["stock"] = max(0, int(body["stock"]))
        except (TypeError, ValueError):
            pass
    if updates:
        await db.update_product(product_id, **updates)
    product = await db.get_product(product_id)
    return web.json_response(_row_to_dict(product))


async def api_product_delete(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    try:
        product_id = int(request.match_info["id"])
    except ValueError:
        raise web.HTTPBadRequest()
    db = get_db()
    product = await db.get_product(product_id)
    if not product:
        raise web.HTTPNotFound()
    await db.delete_product(product_id)
    return web.json_response({"ok": True})


async def api_product_image_get(request: web.Request) -> web.Response:
    """GET фото товара по image_file_id через Telegram Bot API."""
    err = await _require_admin(request)
    if err:
        return err
    try:
        product_id = int(request.match_info["id"])
    except ValueError:
        raise web.HTTPBadRequest()
    db = get_db()
    product = await db.get_product(product_id)
    if not product or not product.get("image_file_id"):
        raise web.HTTPNotFound()
    bot = request.app.get("bot")
    if not bot:
        return web.json_response({"error": "Bot not available"}, status=503)
    try:
        file = await bot.get_file(product["image_file_id"])
        url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return web.json_response({"error": "Could not load image"}, status=502)
                body = await resp.read()
                content_type = resp.content_type or "image/jpeg"
        return web.Response(body=body, content_type=content_type)
    except Exception as e:
        logging.exception("Product image proxy: %s", e)
        return web.json_response({"error": "Could not get file"}, status=500)


async def _get_file_id_via_bot(bot, file_bytes: bytes, is_video: bool):
    """Отправляет файл в Telegram только чтобы получить file_id; в чат админу не слать.
    Если задан STORAGE_CHAT_ID (канал/чат), файл уходит туда — так он только привязывается к товару."""
    from aiogram.types import BufferedInputFile
    storage = (os.getenv("STORAGE_CHAT_ID") or "").strip()
    if storage:
        try:
            chat_id = int(storage)
        except ValueError:
            chat_id = None
    else:
        chat_id = None
    if chat_id is None:
        admin_ids = get_admin_ids()
        if not admin_ids:
            raise ValueError("ADMIN_IDS не заданы")
        chat_id = admin_ids[0]
    if is_video:
        msg = await bot.send_video(chat_id, BufferedInputFile(file_bytes, "video.mp4"))
        return msg.video.file_id if msg.video else None
    else:
        msg = await bot.send_photo(chat_id, BufferedInputFile(file_bytes, "photo.jpg"))
        return msg.photo[-1].file_id if msg.photo else None


def _is_image_content(content_type: str, filename: str) -> bool:
    if content_type and content_type.lower().startswith("image/"):
        return True
    ext = (filename or "").lower().split(".")[-1] if "." in (filename or "") else ""
    return ext in ("jpg", "jpeg", "png", "gif", "webp", "bmp")


def _is_video_content(content_type: str, filename: str) -> bool:
    if content_type and content_type.lower().startswith("video/"):
        return True
    ext = (filename or "").lower().split(".")[-1] if "." in (filename or "") else ""
    return ext in ("mp4", "mov", "webm", "avi", "mkv", "m4v")


async def _read_first_file_part(reader):
    # Returns (data, content_type, filename)
    """Читает первый part с name=file, возвращает (data, content_type, filename)."""
    data = None
    content_type = ""
    filename = ""
    async for part in reader:
        if part.name == "file":
            filename = part.filename or ""
            content_type = (part.headers.get("Content-Type") or "").split(";")[0].strip()
            data = await part.read()
            break
    return (data, content_type, filename)


async def api_product_upload_image(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    try:
        product_id = int(request.match_info["id"])
    except ValueError:
        raise web.HTTPBadRequest()
    bot = request.app.get("bot")
    if not bot:
        return web.json_response({"error": "Bot not available"}, status=503)
    reader = await request.multipart()
    data, content_type, filename = await _read_first_file_part(reader)
    if not data:
        return web.json_response({"error": "Отправьте файл (поле file)"}, status=400)
    if not _is_image_content(content_type, filename):
        return web.json_response(
            {"error": "Загрузите изображение (JPG, PNG и т.д.), не видео"},
            status=400,
        )
    try:
        file_id = await _get_file_id_via_bot(bot, data, is_video=False)
    except Exception as e:
        logging.exception("Upload image: %s", e)
        return web.json_response({"error": str(e)}, status=500)
    db = get_db()
    await db.update_product(product_id, image_file_id=file_id)
    product = await db.get_product(product_id)
    return web.json_response(_row_to_dict(product))


async def api_product_upload_video(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err:
        return err
    try:
        product_id = int(request.match_info["id"])
    except ValueError:
        raise web.HTTPBadRequest()
    bot = request.app.get("bot")
    if not bot:
        return web.json_response({"error": "Bot not available"}, status=503)
    reader = await request.multipart()
    data, content_type, filename = await _read_first_file_part(reader)
    if not data:
        return web.json_response({"error": "Отправьте файл (поле file)"}, status=400)
    if not _is_video_content(content_type, filename):
        return web.json_response(
            {"error": "Загрузите видео (MP4 и т.д.), не фото"},
            status=400,
        )
    try:
        file_id = await _get_file_id_via_bot(bot, data, is_video=True)
    except Exception as e:
        logging.exception("Upload video: %s", e)
        return web.json_response({"error": str(e)}, status=500)
    db = get_db()
    await db.update_product(product_id, video_file_id=file_id)
    product = await db.get_product(product_id)
    return web.json_response(_row_to_dict(product))


async def api_backup(request: web.Request) -> web.Response:
    """GET /api/backup — скачать копию БД (только для админа)."""
    err = await _require_admin(request)
    if err:
        return err
    db_path = APP_ROOT / "данные" / "laptops.db"
    if not db_path.exists() or not db_path.is_file():
        return web.json_response({"error": "Файл БД не найден"}, status=404)
    try:
        body = db_path.read_bytes()
    except Exception as e:
        logging.exception("Backup read: %s", e)
        return web.json_response({"error": "Не удалось прочитать БД"}, status=500)
    return web.Response(
        body=body,
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Disposition": 'attachment; filename="laptops.db"',
        },
    )


@web.middleware
async def admin_ip_middleware(request: web.Request, handler):
    """Если задан ADMIN_ALLOWED_IPS — доступ к админке только с этих IP."""
    if not _check_allowed_ip(request):
        return web.json_response(
            {"error": "Forbidden: доступ только с разрешённого устройства (IP)"},
            status=403,
        )
    return await handler(request)


def create_app(bot=None) -> web.Application:
    app = web.Application(middlewares=[admin_ip_middleware], logger=None)
    app["bot"] = bot

    # Статика
    app.router.add_get("/", index)
    app.router.add_get("/admin.html", index)
    app.router.add_get("/{name}", static_file)

    # Авторизация и пользователи админки
    app.router.add_post("/api/auth/login", api_auth_login)
    app.router.add_get("/api/admin/users", api_admin_users_list)
    app.router.add_post("/api/admin/users", api_admin_users_create)
    app.router.add_delete("/api/admin/users/{id}", api_admin_users_delete)
    app.router.add_get("/api/settings/env", api_settings_env_get)
    app.router.add_put("/api/settings/env", api_settings_env_put)
    app.router.add_get("/api/settings/env/raw", api_settings_env_raw)
    app.router.add_get("/api/settings/bot-texts", api_settings_bot_texts_get)
    app.router.add_put("/api/settings/bot-texts", api_settings_bot_texts_put)

    # API
    app.router.add_get("/api/backup", api_backup)
    app.router.add_get("/api/stats", api_stats)
    app.router.add_post("/api/orders", api_order_create)
    app.router.add_get("/api/orders", api_orders_list)
    app.router.add_get("/api/orders/export", api_orders_export)
    app.router.add_get("/api/orders/{id}", api_order_one)
    app.router.add_patch("/api/orders/{id}/status", api_order_status)
    app.router.add_get("/api/orders/{id}/receipt", api_order_receipt)
    app.router.add_delete("/api/orders/{id}", api_order_delete)
    app.router.add_get("/api/products", api_products_list)
    app.router.add_get("/api/products/{id}", api_product_one)
    app.router.add_post("/api/products", api_product_create)
    app.router.add_put("/api/products/{id}", api_product_update)
    app.router.add_delete("/api/products/{id}", api_product_delete)
    app.router.add_get("/api/products/{id}/image", api_product_image_get)
    app.router.add_post("/api/products/{id}/image", api_product_upload_image)
    app.router.add_post("/api/products/{id}/video", api_product_upload_video)

    return app


def run_app(app: web.Application, host: str = "127.0.0.1", port: int = 8080):
    web.run_app(app, host=host, port=port)
