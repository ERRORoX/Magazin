"""Сервис заказов: создание, получение, смена статуса."""
from typing import Any, Dict, List, Optional

from database import get_db
from database.db import STATUS_NEW


class OrderService:
    @staticmethod
    async def create(
        user_id: int,
        product_id: int,
        full_name: str,
        phone: str,
        city: str,
        address: str,
    ) -> Optional[Dict[str, Any]]:
        db = get_db()
        return await db.create_order(
            user_id=user_id,
            product_id=product_id,
            full_name=full_name,
            phone=phone,
            city=city,
            address=address,
        )

    @staticmethod
    async def get_by_id(order_id: int) -> Optional[Dict[str, Any]]:
        return await get_db().get_order(order_id)

    @staticmethod
    async def get_by_user(user_id: int) -> List[Dict[str, Any]]:
        return await get_db().get_orders_by_user(user_id)

    @staticmethod
    async def get_all(status: Optional[str] = None) -> List[Dict[str, Any]]:
        return await get_db().get_all_orders(status=status)

    @staticmethod
    async def set_status(order_id: int, status: str) -> bool:
        return await get_db().set_order_status(order_id, status)

    @staticmethod
    async def set_receipt(order_id: int, receipt_file_id: str) -> bool:
        return await get_db().set_order_receipt(order_id, receipt_file_id)
