"""
Асинхронная SQLite-база для магазина ноутбуков.
Таблицы: products (каталог), orders (заказы со статусами), admin_users (пользователи админки).
"""
import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

from config import APP_ROOT

DB_PATH = APP_ROOT / "данные" / "laptops.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Статусы заказа
STATUS_NEW = "new"
STATUS_AWAITING_PAYMENT = "awaiting_payment"
STATUS_RECEIPT_RECEIVED = "receipt_received"
STATUS_PAID = "paid"
STATUS_SHIPPED = "shipped"

STATUS_LABELS = {
    STATUS_NEW: "Новый",
    STATUS_AWAITING_PAYMENT: "Ожидает оплату",
    STATUS_RECEIPT_RECEIVED: "Чек получен",
    STATUS_PAID: "Оплачен",
    STATUS_SHIPPED: "Отправлен",
}

# Категории товаров
CATEGORY_GAMING = "gaming"
CATEGORY_STUDY = "study"
CATEGORY_WORK = "work"

CATEGORY_LABELS = {
    CATEGORY_GAMING: "Игровые",
    CATEGORY_STUDY: "Учёба",
    CATEGORY_WORK: "Работа",
}


class Database:
    """Асинхронная работа с SQLite."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def get_connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA foreign_keys = ON;")
        return self._conn

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def init(self) -> None:
        conn = await self.get_connection()

        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                price INTEGER NOT NULL,
                category TEXT NOT NULL,
                image_file_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                city TEXT NOT NULL,
                address TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                receipt_file_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                lang TEXT NOT NULL DEFAULT 'ru',
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
            CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);

            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                secret_key_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ai_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE INDEX IF NOT EXISTS idx_ai_history_user ON ai_history(user_id, created_at DESC);
        """)
        try:
            await conn.execute("ALTER TABLE products ADD COLUMN video_file_id TEXT")
        except Exception:
            pass
        try:
            await conn.execute("ALTER TABLE products ADD COLUMN stock INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN lang TEXT NOT NULL DEFAULT 'ru'")
        except Exception:
            pass
        for col in ("last_city", "last_address"):
            try:
                await conn.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
            except Exception:
                pass
        try:
            await conn.execute(
                """CREATE TABLE IF NOT EXISTS favorites (
                    user_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, product_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (product_id) REFERENCES products(id)
                )"""
            )
        except Exception:
            pass
        try:
            await conn.execute(
                """CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    order_id INTEGER,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )"""
            )
        except Exception:
            pass
        await self._bootstrap_admin_users(conn)
        await conn.commit()

    def _hash_secret(self, secret_key: str) -> str:
        salt = os.getenv("ADMIN_SECRET", "master_nosirov")[:32]
        return hashlib.sha256((salt + secret_key.strip()).encode()).hexdigest()

    async def _bootstrap_admin_users(self, conn: aiosqlite.Connection) -> None:
        cursor = await conn.execute("SELECT COUNT(*) FROM admin_users")
        (n,) = (await cursor.fetchone()) or (0,)
        if n > 0:
            return
        default_secret = os.getenv("ADMIN_SECRET", "").strip()
        if default_secret:
            h = self._hash_secret(default_secret)
            await conn.execute(
                "INSERT INTO admin_users (username, secret_key_hash) VALUES (?, ?)",
                ("admin", h),
            )

    async def verify_admin_user(self, username: str, secret_key: str) -> Optional[int]:
        """Проверка логина. Возвращает id пользователя или None."""
        conn = await self.get_connection()
        h = self._hash_secret(secret_key)
        cursor = await conn.execute(
            "SELECT id FROM admin_users WHERE username = ? AND secret_key_hash = ?",
            (username.strip(), h),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def create_admin_user(self, username: str, secret_key: str) -> Optional[int]:
        """Создать пользователя админки. Возвращает id или None при дубликате."""
        conn = await self.get_connection()
        username = username.strip()
        if not username or len(secret_key) < 4:
            return None
        h = self._hash_secret(secret_key)
        try:
            cursor = await conn.execute(
                "INSERT INTO admin_users (username, secret_key_hash) VALUES (?, ?)",
                (username, h),
            )
            await conn.commit()
            return cursor.lastrowid
        except Exception:
            await conn.rollback()
            return None

    async def list_admin_users(self) -> List[Dict[str, Any]]:
        conn = await self.get_connection()
        cursor = await conn.execute(
            "SELECT id, username, created_at FROM admin_users ORDER BY id"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def delete_admin_user(self, user_id: int) -> bool:
        """Удалить пользователя админки по id. Возвращает True если удалён."""
        conn = await self.get_connection()
        cursor = await conn.execute("DELETE FROM admin_users WHERE id = ?", (user_id,))
        await conn.commit()
        return cursor.rowcount > 0

    async def ensure_user(self, user_id: int, username: Optional[str] = None, full_name: Optional[str] = None) -> None:
        conn = await self.get_connection()
        now = datetime.utcnow().isoformat()
        await conn.execute(
            """INSERT INTO users (user_id, username, full_name, last_active)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
               username = excluded.username,
               full_name = excluded.full_name,
               last_active = excluded.last_active;
            """,
            (user_id, username or "", full_name or "", now),
        )
        await conn.commit()

    async def get_user_lang(self, user_id: int) -> str:
        conn = await self.get_connection()
        cursor = await conn.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row and row[0]:
            return row[0] if row[0] in ("ru", "tg") else "ru"
        return "ru"

    async def set_user_lang(self, user_id: int, lang: str) -> None:
        if lang not in ("ru", "tg"):
            lang = "ru"
        conn = await self.get_connection()
        now = datetime.utcnow().isoformat()
        await conn.execute(
            """INSERT INTO users (user_id, lang, last_active) VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET lang = excluded.lang, last_active = excluded.last_active""",
            (user_id, lang, now),
        )
        await conn.commit()

    async def update_user_last_address(self, user_id: int, city: str, address: str) -> None:
        """Сохранить последний город и адрес для кнопки «Как в прошлый раз»."""
        conn = await self.get_connection()
        now = datetime.utcnow().isoformat()
        await conn.execute(
            """INSERT INTO users (user_id, last_city, last_address, last_active) VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET last_city = excluded.last_city,
               last_address = excluded.last_address, last_active = excluded.last_active""",
            (user_id, (city or "")[:200], (address or "")[:500], now),
        )
        await conn.commit()

    async def get_user_last_address(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить последние город и адрес пользователя (если есть)."""
        conn = await self.get_connection()
        cursor = await conn.execute(
            "SELECT last_city, last_address FROM users WHERE user_id = ? AND (last_city IS NOT NULL AND last_city != '')",
            (user_id,),
        )
        row = await cursor.fetchone()
        if not row or not row[0]:
            return None
        return {"city": row[0], "address": row[1] or ""}

    async def get_products(
        self,
        category: Optional[str] = None,
        stock_filter: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """stock_filter: 'low' | 'out'. search: поиск по title и description (LIKE)."""
        conn = await self.get_connection()
        conditions = []
        params: List[Any] = []
        if category:
            conditions.append("category = ?")
            params.append(category)
        if stock_filter == "low":
            conditions.append("COALESCE(stock, 0) <= 2")
        elif stock_filter == "out":
            conditions.append("COALESCE(stock, 0) = 0")
        if search and search.strip():
            q = f"%{search.strip()}%"
            conditions.append("(title LIKE ? OR description LIKE ?)")
            params.extend([q, q])
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        cursor = await conn.execute(
            f"SELECT * FROM products{where} ORDER BY category, id",
            params,
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_product(self, product_id: int) -> Optional[Dict[str, Any]]:
        conn = await self.get_connection()
        cursor = await conn.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def add_product(
        self,
        title: str,
        price: int,
        category: str,
        description: str = "",
        image_file_id: Optional[str] = None,
        stock: int = 0,
    ) -> int:
        conn = await self.get_connection()
        cursor = await conn.execute(
            """INSERT INTO products (title, description, price, category, image_file_id, stock)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, description, price, category, image_file_id, max(0, stock)),
        )
        await conn.commit()
        return cursor.lastrowid

    async def update_product(
        self,
        product_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        price: Optional[int] = None,
        category: Optional[str] = None,
        image_file_id: Optional[str] = None,
        video_file_id: Optional[str] = None,
        stock: Optional[int] = None,
    ) -> bool:
        conn = await self.get_connection()
        updates = []
        params = []
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if price is not None:
            updates.append("price = ?")
            params.append(price)
        if category is not None:
            updates.append("category = ?")
            params.append(category)
        if image_file_id is not None:
            updates.append("image_file_id = ?")
            params.append(image_file_id)
        if video_file_id is not None:
            updates.append("video_file_id = ?")
            params.append(video_file_id)
        if stock is not None:
            updates.append("stock = ?")
            params.append(max(0, stock))
        if not updates:
            return False
        params.append(product_id)
        await conn.execute(
            f"UPDATE products SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        await conn.commit()
        return True

    async def delete_product(self, product_id: int) -> bool:
        conn = await self.get_connection()
        cursor = await conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        await conn.commit()
        return cursor.rowcount > 0

    async def get_product_stock(self, product_id: int) -> int:
        """Возвращает остаток на складе (0 если товар не найден)."""
        p = await self.get_product(product_id)
        if not p:
            return 0
        return int(p.get("stock", 0) or 0)

    async def decrement_product_stock(self, product_id: int, by: int = 1) -> bool:
        """Уменьшает остаток на складе. Не уходит в минус."""
        conn = await self.get_connection()
        await conn.execute(
            "UPDATE products SET stock = max(0, COALESCE(stock, 0) - ?) WHERE id = ?",
            (by, product_id),
        )
        await conn.commit()
        return True

    def _generate_order_number(self) -> str:
        from datetime import date
        d = date.today().strftime("%Y%m%d")
        return f"ORD-{d}-{datetime.utcnow().strftime('%H%M%S')}"

    async def create_order(
        self,
        user_id: int,
        product_id: int,
        full_name: str,
        phone: str,
        city: str,
        address: str,
    ) -> Dict[str, Any]:
        conn = await self.get_connection()
        order_number = self._generate_order_number()
        now = datetime.utcnow().isoformat()
        cursor = await conn.execute(
            """INSERT INTO orders (order_number, user_id, product_id, full_name, phone, city, address, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (order_number, user_id, product_id, full_name, phone, city, address, STATUS_NEW, now, now),
        )
        await conn.commit()
        order_id = cursor.lastrowid
        await self.update_user_last_address(user_id, city, address)
        return await self.get_order(order_id)

    async def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        conn = await self.get_connection()
        cursor = await conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_order_by_number(self, order_number: str) -> Optional[Dict[str, Any]]:
        conn = await self.get_connection()
        cursor = await conn.execute("SELECT * FROM orders WHERE order_number = ?", (order_number,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_orders_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        conn = await self.get_connection()
        cursor = await conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_all_orders(
        self,
        status: Optional[str] = None,
        search: Optional[str] = None,
        sort_order: str = "desc",
        exclude_status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """date_from/date_to: YYYY-MM-DD. limit/offset для пагинации."""
        conn = await self.get_connection()
        conditions = []
        params: List[Any] = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if exclude_status:
            conditions.append("status != ?")
            params.append(exclude_status)
        if search and search.strip():
            q = f"%{search.strip()}%"
            conditions.append("(order_number LIKE ? OR phone LIKE ?)")
            params.extend([q, q])
        if date_from:
            conditions.append("date(created_at) >= date(?)")
            params.append(date_from)
        if date_to:
            conditions.append("date(created_at) <= date(?)")
            params.append(date_to)
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        order = "ASC" if sort_order == "asc" else "DESC"
        sql = f"SELECT * FROM orders{where} ORDER BY created_at {order}"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        if offset is not None:
            sql += " OFFSET ?"
            params.append(offset)
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_orders_count_today(self) -> int:
        """Количество заказов, созданных сегодня (по локальной дате SQLite)."""
        conn = await self.get_connection()
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM orders WHERE date(created_at) = date('now', 'localtime')"
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def get_orders_for_receipt_reminder(self, hours_old: int = 6) -> List[Dict[str, Any]]:
        """Заказы в статусе new или awaiting_payment, созданные более hours_old часов назад."""
        conn = await self.get_connection()
        cursor = await conn.execute(
            """SELECT * FROM orders WHERE status IN (?, ?) AND datetime(created_at) < datetime('now', ?)""",
            (STATUS_NEW, STATUS_AWAITING_PAYMENT, f"-{hours_old} hours"),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_products_low_stock_count(self, max_stock: int = 2) -> int:
        """Количество товаров с остатком <= max_stock (по умолчанию 2 — «низкий остаток»)."""
        conn = await self.get_connection()
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM products WHERE COALESCE(stock, 0) <= ?",
            (max_stock,),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def get_products_out_of_stock_count(self) -> int:
        """Количество товаров с нулевым остатком."""
        conn = await self.get_connection()
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM products WHERE COALESCE(stock, 0) = 0"
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def set_order_status(self, order_id: int, status: str) -> bool:
        conn = await self.get_connection()
        now = datetime.utcnow().isoformat()
        await conn.execute(
            "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, order_id),
        )
        await conn.commit()
        return True

    async def set_order_receipt(self, order_id: int, receipt_file_id: str) -> bool:
        conn = await self.get_connection()
        now = datetime.utcnow().isoformat()
        await conn.execute(
            "UPDATE orders SET receipt_file_id = ?, status = ?, updated_at = ? WHERE id = ?",
            (receipt_file_id, STATUS_RECEIPT_RECEIVED, now, order_id),
        )
        await conn.commit()
        return True

    async def delete_order(self, order_id: int, only_if_shipped: bool = True) -> bool:
        """Удаляет заказ. Если only_if_shipped=True — только со статусом «Отправлен»."""
        order = await self.get_order(order_id)
        if not order:
            return False
        if only_if_shipped and order.get("status") != STATUS_SHIPPED:
            return False
        conn = await self.get_connection()
        cursor = await conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        await conn.commit()
        return cursor.rowcount > 0

    async def add_favorite(self, user_id: int, product_id: int) -> bool:
        """Добавить товар в избранное. Возвращает True если добавлен."""
        conn = await self.get_connection()
        try:
            await conn.execute(
                "INSERT OR IGNORE INTO favorites (user_id, product_id) VALUES (?, ?)",
                (user_id, product_id),
            )
            await conn.commit()
            return True
        except Exception:
            await conn.rollback()
            return False

    async def remove_favorite(self, user_id: int, product_id: int) -> bool:
        conn = await self.get_connection()
        cursor = await conn.execute(
            "DELETE FROM favorites WHERE user_id = ? AND product_id = ?",
            (user_id, product_id),
        )
        await conn.commit()
        return cursor.rowcount > 0

    async def is_favorite(self, user_id: int, product_id: int) -> bool:
        conn = await self.get_connection()
        cursor = await conn.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND product_id = ?",
            (user_id, product_id),
        )
        row = await cursor.fetchone()
        return row is not None

    async def get_favorite_product_ids(self, user_id: int) -> List[int]:
        conn = await self.get_connection()
        cursor = await conn.execute(
            "SELECT product_id FROM favorites WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def get_favorites_products(self, user_id: int) -> List[Dict[str, Any]]:
        """Список товаров в избранном пользователя (с актуальными данными)."""
        ids = await self.get_favorite_product_ids(user_id)
        if not ids:
            return []
        out = []
        for pid in ids:
            p = await self.get_product(pid)
            if p:
                out.append(p)
        return out

    async def add_review(self, user_id: int, content: str, order_id: Optional[int] = None) -> int:
        """Сохранить отзыв. Возвращает id отзыва."""
        conn = await self.get_connection()
        cursor = await conn.execute(
            "INSERT INTO reviews (user_id, order_id, content, created_at) VALUES (?, ?, ?, ?)",
            (user_id, order_id, (content or "")[:2000], datetime.utcnow().isoformat()),
        )
        await conn.commit()
        return cursor.lastrowid or 0

    async def log_ai_message(self, user_id: int, role: str, content: str) -> None:
        """Сохранить сообщение в историю AI-консультанта (role: user или assistant)."""
        conn = await self.get_connection()
        await conn.execute(
            "INSERT INTO ai_history (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (user_id, role, content[:8000], datetime.utcnow().isoformat()),
        )
        await conn.commit()

    async def get_ai_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Последние сообщения диалога для контекста (старые в начале)."""
        conn = await self.get_connection()
        cursor = await conn.execute(
            """SELECT role, content FROM ai_history
               WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        out = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
        return out

    async def seed_products_if_empty(self) -> None:
        products = await self.get_products()
        if products:
            return
        # Примеры товаров по категориям
        await self.add_product(
            "ASUS ROG Strix G15",
            price=4500,
            category=CATEGORY_GAMING,
            description="Игровой ноутбук, RTX 4060, 16 GB RAM, 512 GB SSD",
            stock=5,
        )
        await self.add_product(
            "Lenovo Legion 5",
            price=4200,
            category=CATEGORY_GAMING,
            description="Игры и стриминг, Ryzen 7, RTX 4050, 16 GB",
            stock=5,
        )
        await self.add_product(
            "Acer Aspire 5",
            price=1800,
            category=CATEGORY_STUDY,
            description="Учёба и офис, Ryzen 5, 8 GB RAM, 256 GB SSD",
            stock=5,
        )
        await self.add_product(
            "HP Pavilion 15",
            price=2200,
            category=CATEGORY_STUDY,
            description="Универсальный ноутбук для учёбы, 15.6\", 8 GB",
            stock=5,
        )
        await self.add_product(
            "ThinkPad E15",
            price=3200,
            category=CATEGORY_WORK,
            description="Работа и бизнес, надёжная клавиатура, 16 GB",
            stock=5,
        )
        await self.add_product(
            "Dell Vostro 15",
            price=2800,
            category=CATEGORY_WORK,
            description="Офис и удалённая работа, Intel i5, 8 GB",
            stock=5,
        )


# Глобальный экземпляр (используется через get_db для инициализации в main)
# Добавьте это в самый низ файла database/db.py
db = Database()

def get_db():
    return db


async def init_db() -> None:
    db = get_db()
    await db.init()
    await db.seed_products_if_empty()