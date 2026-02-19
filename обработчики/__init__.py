"""Обработчики бота магазина ноутбуков."""
from aiogram import Router

from .commands import router as commands_router
from .callbacks import router as callbacks_router
from .order_handlers import router as order_router
from .admin_orders import router as admin_orders_router
from .ai import router as ai_router
from .errors import router as errors_router

router = Router()

router.include_router(commands_router)
router.include_router(callbacks_router)
router.include_router(order_router)
router.include_router(admin_orders_router)
router.include_router(ai_router)
router.include_router(errors_router)

__all__ = ["router"]

