"""Асинхронный слой базы данных для бота магазина ноутбуков."""
from .db import get_db, init_db, Database

__all__ = ["get_db", "init_db", "Database"]
