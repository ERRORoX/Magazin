"""Модели данных для магазина ноутбуков."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Product:
    id: int
    title: str
    description: str
    price: int
    category: str
    image_file_id: Optional[str] = None

    @property
    def price_formatted(self) -> str:
        return f"{self.price:,} сомони".replace(",", " ")


@dataclass
class Order:
    id: int
    order_number: str
    user_id: int
    product_id: int
    full_name: str
    phone: str
    city: str
    address: str
    status: str
    receipt_file_id: Optional[str] = None
    created_at: Optional[str] = None
