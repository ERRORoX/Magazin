import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode, ChatAction
from aiogram.utils.markdown import html_decoration as hd
from aiogram.exceptions import TelegramBadRequest

from database import get_db
from services.ai_consultant_service import ask_consultant
from utils.keyboards import build_main_keyboard
from utils.locales import t

router = Router()
logger = logging.getLogger(__name__)

class ConsultantStates(StatesGroup):
    waiting_question = State()


@router.message(Command("consult"))
async def cmd_consult(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    lang = await get_db().get_user_lang(message.from_user.id)
    await state.set_state(ConsultantStates.waiting_question)
    await message.answer("🤖 " + t("ai_prompt", lang), parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "ai_consult")
async def on_ai_consult(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    lang = await get_db().get_user_lang(callback.from_user.id)
    await state.set_state(ConsultantStates.waiting_question)
    consult_text = "🤖 " + t("ai_prompt", lang)
    try:
        await callback.message.edit_text(consult_text, parse_mode=ParseMode.HTML)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            await callback.message.answer(consult_text, parse_mode=ParseMode.HTML)
    except Exception:
        await callback.message.answer(consult_text, parse_mode=ParseMode.HTML)
    await callback.answer()


@router.message(ConsultantStates.waiting_question, F.text)
async def process_consultant_question(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    lang = await get_db().get_user_lang(message.from_user.id)
    user_text = message.text.strip()

    if len(user_text) < 3:
        await message.answer("ℹ️ " + t("ai_query_min", lang))
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    sent_msg = await message.answer("⏳ <i>" + t("ai_wait", lang) + "</i>", parse_mode=ParseMode.HTML)

    try:
        db = get_db()
        history = await db.get_ai_history(message.from_user.id, limit=10)
        reply = await ask_consultant(user_text, history=history)
        safe_reply = hd.quote(reply)
        await db.log_ai_message(message.from_user.id, "user", user_text)
        await db.log_ai_message(message.from_user.id, "assistant", reply)
        await state.clear()
        await sent_msg.delete()

        await message.answer(
            f"🤖 <b>{t('ai_recommendations', lang)}</b>\n\n{safe_reply}",
            reply_markup=build_main_keyboard(message.from_user.id, lang),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"AI Consultant Error: {e}")
        try:
            await sent_msg.edit_text(
                "❌ " + t("ai_error", lang),
                reply_markup=build_main_keyboard(message.from_user.id, lang),
            )
        except TelegramBadRequest as err:
            if "message is not modified" not in str(err).lower():
                await sent_msg.answer(
                    "❌ " + t("ai_error", lang),
                    reply_markup=build_main_keyboard(message.from_user.id, lang),
                )
        except Exception:
            await sent_msg.answer(
                "❌ " + t("ai_error", lang),
                reply_markup=build_main_keyboard(message.from_user.id, lang),
            )
        await state.clear()