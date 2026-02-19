"""AI-консультант по подбору ноутбука по бюджету (OpenRouter)."""
import asyncio
import logging
import os
from typing import List, Optional

import aiohttp

from database import get_db


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-4o-mini"


def _build_system_prompt(products_text: str) -> str:
    return (
        "Ты — дружелюбный и компетентный консультант магазина ноутбуков в Таджикистане. "
        "Помогаешь подобрать ноутбук по бюджету и целям.\n\n"
        "Правила:\n"
        "1. Отвечай на том же языке, на котором пишет пользователь (русский, таджикский, английский и т.д.).\n"
        "2. Будь вежлив, кратко и по делу. Не придумывай товары — рекомендуй только из каталога ниже, указывай точное название и цену в сомони.\n"
        "3. Распознавай цели: игры / гейминг / бозӣ → игровые; учёба / таълим / студент → учёба; работа / офис / кор → работа. "
        "«Барои корхои офис», «для офиса», «офис» = работа. «Для игр», «барои бозӣ» = игры.\n"
        "4. Если назван бюджет (число или «до N сомони») — предложи 1–3 подходящих варианта из каталога с названием и ценой. "
        "Если бюджет низкий — вежливо предложи ближайшие по цене или скажи, что можно уточнить запрос.\n"
        "5. Формат ответа: короткое приветствие или вывод, затем список вариантов в виде «• Название — N сомони. Кратко почему подходит.» "
        "В конце напиши одну фразу: что можно открыть каталог в боте и оформить заказ, или уточнить бюджет.\n"
        "6. Не пиши длинные абзацы. Без вступления типа «Конечно!» — сразу по делу. Не используй эмодзи, если пользователь их не использовал.\n"
        "7. Если в каталоге нет подходящих по бюджету — честно скажи и предложи ближайшие по цене или другой категории.\n"
        "8. Рекомендуй только товары «в наличии» (есть N шт). Товары «нет в наличии» не предлагай.\n\n"
        "Каталог (цены в сомони, рекомендуй только эти товары):\n"
        + products_text
    )


async def get_products_text() -> str:
    db = get_db()
    products = await db.get_products()
    lines = []
    for p in products:
        cat = p.get("category", "")
        cat_label = {"gaming": "Игровые", "study": "Учёба", "work": "Работа"}.get(cat, cat)
        stock = int(p.get("stock") or 0)
        stock_note = f", в наличии {stock} шт" if stock > 0 else ", нет в наличии (не рекомендуй)"
        lines.append(
            f"- {p['title']}: {p['price']} сомони ({cat_label}){stock_note}. {p.get('description') or ''}"
        )
    return "\n".join(lines) if lines else "Пока нет товаров в каталоге."


async def ask_consultant(user_message: str, history: Optional[List[dict]] = None) -> str:
    raw_key = os.getenv("OPENROUTER_API_KEY") or ""
    api_key = raw_key.strip().rstrip(">").strip()  # убираем пробелы и случайный >
    if not api_key or api_key.startswith("••••"):
        return "⚠️ Сервис консультанта не настроен (OPENROUTER_API_KEY). Добавьте ключ в .env или в Настройках админки."

    products_text = await get_products_text()
    system = _build_system_prompt(products_text)

    messages = [{"role": "system", "content": system}]
    if history:
        for h in history[-10:]:
            role = h.get("role", "user")
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": (h.get("content") or "")[:2000]})
    messages.append({"role": "user", "content": user_message})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/",
    }
    payload = {"model": MODEL, "messages": messages, "temperature": 0.4}
    last_error = ""

    for attempt in range(2):  # один повтор при 502/503
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    OPENROUTER_URL,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 401:
                        return (
                            "⚠️ Неверный ключ OpenRouter (401). "
                            "Проверьте OPENROUTER_API_KEY в .env или в Настройках: ключ возьмите на https://openrouter.ai, без лишних символов в конце."
                        )
                    if resp.status in (502, 503, 504):
                        last_error = (
                            "⚠️ Сервис подбора временно недоступен (ошибка на стороне OpenRouter). "
                            "Попробуйте через 1–2 минуты или позже."
                        )
                        if attempt == 0:
                            await asyncio.sleep(1.5)
                            continue
                        return last_error
                    if resp.status != 200:
                        try:
                            err_body = await resp.text()
                            if len(err_body) > 200:
                                err_body = err_body[:200] + "..."
                        except Exception:
                            err_body = ""
                        return f"⚠️ Ошибка сервиса: {resp.status}. {err_body}"
                    data = await resp.json()
                    choice = data.get("choices", [{}])[0]
                    content = choice.get("message", {}).get("content", "")
                    return content.strip() or "Пустой ответ."
        except Exception as e:
            logging.exception("AI consultant error: %s", e)
            last_error = f"⚠️ Ошибка при запросе: {e}"
            if attempt == 0:
                await asyncio.sleep(1)
                continue
            return last_error

    return last_error or "⚠️ Сервис временно недоступен. Попробуйте позже."
