"""Меню бота.

Архитектура:
  — ReplyKeyboardMarkup внизу экрана: 6 кнопок главного меню, всегда видны.
  — InlineKeyboard внутри каждого раздела: действия и навигация.
  — Все команды продолжают работать параллельно.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import attendance as att
from . import beer as be
from . import schedule as sch
from . import stats as stt
from .appkb import ATTEND_TEXT, app_only_kb
from .config import settings
from .db import Session, User
from .handlers import (
    app_only_kb,
    cfg_from_user,
    get_user,
    parse_date,
    reply,
)
from .service import (
    calendar_text,
    shuttle_text,
    stats_text,
    status_text,
    weather_text,
)

router = Router()

# ─────────────────────────── главная клавиатура ──────────────────────────


def main_kb() -> ReplyKeyboardRemove:
    """Старая нижняя клавиатура убрана: всё теперь в мини-приложении.

    Отправка ReplyKeyboardRemove прячет клавиатуру у пользователя.
    """
    return ReplyKeyboardRemove()


# ─────────────────────────── инлайн-подменю ─────────────────────────────


# ─────────────────────────── /start и /menu ──────────────────────────────


@router.message(Command("menu", "меню"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await get_user(message.from_user.id)

    if not user:
        # новый пользователь — онбординг из handlers.py перехватит /start
        # если это /menu — подсказываем
        if message.text and not message.text.startswith("/start"):
            await message.answer(
                "Сначала настрой график: /start",
                reply_markup=main_kb(),
            )
        return

    async with Session() as s:
        text = await status_text(s, user)

    await message.answer(
        "Всё управление теперь в приложении: кнопка «Приложение» слева от поля ввода.",
        reply_markup=main_kb(),
    )
    await message.answer(text)


# ─────────────────────────── кнопки главного меню ───────────────────────


@router.message(F.text == "📊 Моя смена")
async def menu_shift(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await reply(message, "Сначала настрой график: /start")
        return
    async with Session() as s:
        text = await status_text(s, user)
    await message.answer(text, reply_markup=app_only_kb())


@router.message(F.text == "🌤 Погода")
async def menu_weather(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await reply(message, "Сначала настрой график: /start")
        return
    await reply(message, await weather_text(user), ttl_min=60)


@router.message(F.text == "🚌 Развозка")
async def menu_shuttle(message: Message) -> None:
    from . import shuttle as sh

    user = await get_user(message.from_user.id)
    if not user:
        await reply(message, "Сначала настрой график: /start")
        return

    if not user.shuttle_route:
        kb = InlineKeyboardBuilder()
        for key, r in sh.ROUTES.items():
            kb.button(text=r.station, callback_data=f"route:{key}")
        kb.adjust(2)
        await message.answer(
            "Откуда ездишь на развозке?",
            reply_markup=app_only_kb(),
        )
        return
    await reply(message, shuttle_text(user), ttl_min=60)


@router.message(F.text == "🍺 После смены")
async def menu_beer(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await reply(message, "Сначала настрой график: /start")
        return
    async with Session() as s:
        cfg = cfg_from_user(user)
        event = await be.nearest_event(s, cfg.now())
        if event:
            text = await be.event_summary(s, event)
            await message.answer(text, reply_markup=app_only_kb())
        else:
            await message.answer(
                "🍺 <b>После смены</b>\n\n"
                f"Опрос придёт за {settings.beer_lead_min} мин до конца дневной смены.\n"
                "Тут появится список тех, кто согласился.",
                reply_markup=app_only_kb(),
            )


@router.message(F.text == "📈 Мой стаж")
async def menu_stats(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await reply(message, "Сначала настрой график: /start")
        return
    async with Session() as s:
        text = await stats_text(s, user)
    await message.answer(text, reply_markup=app_only_kb())


@router.message(F.text == "⚙️ Настройки")
async def menu_settings(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await reply(message, "Сначала настрой график: /start")
        return
    await message.answer("<b>⚙️ Настройки</b>", reply_markup=app_only_kb())


# ─────────────────────────── колбэки подменю ─────────────────────────────

