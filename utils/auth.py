"""
Проверка прав администратора.
Читает ADMIN_IDS из .env. Если не указаны — для теста разрешает всем.
"""
import os
from pathlib import Path

from dotenv import load_dotenv


def is_admin(user_id: int) -> bool:
    """
    Проверяет, является ли пользователь администратором.

    Args:
        user_id: ID пользователя Telegram

    Returns:
        True если пользователь администратор, False иначе
    """
    try:
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            admin_ids_str = os.getenv("ADMIN_IDS", "")

            if admin_ids_str:
                admin_list = [
                    int(x.strip())
                    for x in admin_ids_str.split(",")
                    if x.strip().isdigit()
                ]
                return user_id in admin_list

        # Если не указаны админы — для теста разрешаем всем
        return True
    except Exception:
        return True
