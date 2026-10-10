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
from .config import settings
from .db import Session, User
from .handlers import (
    attendance_kb,
    cfg_from_user,
    get_user,
    parse_date,
    reply,
    settings_kb,
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


def shift_kb() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="⏱ Сколько осталось",   callback_data="mn:skolko")
    kb.button(text="📅 График на 14 дней",  callback_data="mn:grafik")
    kb.button(text="✅ Отметиться",          callback_data="mn:otmetka")
    kb.button(text="🏖 Отпуск",             callback_data="mn:otpusk_info")
    kb.button(text="🔄 Перенастроить",      callback_data="set:reconf")
    kb.adjust(1)
    return kb


def stats_kb() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Карточка стажа",    callback_data="mn:stazh")
    kb.button(text="✅ Отметиться сегодня", callback_data="mn:otmetka")
    kb.button(text="🤒 Отметить пропуск",  callback_data="mn:bolnichny_info")
    kb.button(text="📅 Дата устройства",   callback_data="mn:hired_info")
    kb.adjust(1)
    return kb


def beer_kb_menu(event_id: int | None) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    if event_id:
        kb.button(text="🍺 Я за",         callback_data=f"beer:yes:{event_id}")
        kb.button(text="🏠 Сегодня домой", callback_data=f"beer:no:{event_id}")
        kb.adjust(2)
    else:
        kb.button(text="ℹ️ Как работает опрос", callback_data="mn:beer_info")
    return kb


# ─────────────────────────── /start и /menu ──────────────────────────────


@router.message(Command("menu", "меню", "start"))
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
    await message.answer(text, reply_markup=shift_kb().as_markup())


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
            reply_markup=kb.as_markup(),
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
            await message.answer(text, reply_markup=beer_kb_menu(event.id).as_markup())
        else:
            await message.answer(
                "🍺 <b>После смены</b>\n\n"
                f"Опрос придёт за {settings.beer_lead_min} мин до конца дневной смены.\n"
                "Тут появится список тех, кто согласился.",
                reply_markup=beer_kb_menu(None).as_markup(),
            )


@router.message(F.text == "📈 Мой стаж")
async def menu_stats(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await reply(message, "Сначала настрой график: /start")
        return
    async with Session() as s:
        text = await stats_text(s, user)
    await message.answer(text, reply_markup=stats_kb().as_markup())


@router.message(F.text == "⚙️ Настройки")
async def menu_settings(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await reply(message, "Сначала настрой график: /start")
        return
    await message.answer("<b>⚙️ Настройки</b>", reply_markup=settings_kb(user).as_markup())


# ─────────────────────────── колбэки подменю ─────────────────────────────


@router.callback_query(F.data == "mn:skolko")
async def cb_skolko(cb: CallbackQuery) -> None:
    async with Session() as s:
        user = await s.get(User, cb.from_user.id)
        if not user:
            await cb.answer("Сначала /start", show_alert=True)
            return
        text = await status_text(s, user)
    await cb.message.answer(text)
    await cb.answer()


@router.callback_query(F.data == "mn:grafik")
async def cb_grafik(cb: CallbackQuery) -> None:
    user = await get_user(cb.from_user.id)
    if not user:
        await cb.answer("Сначала /start", show_alert=True)
        return
    await cb.message.answer(calendar_text(user))
    await cb.answer()


@router.callback_query(F.data == "mn:otmetka")
async def cb_otmetka(cb: CallbackQuery) -> None:
    user = await get_user(cb.from_user.id)
    if not user:
        await cb.answer("Сначала /start", show_alert=True)
        return
    cfg = cfg_from_user(user)
    today = cfg.now().date()
    kind = cfg.kind(today)
    if kind not in sch.WORK:
        await cb.answer(f"Сегодня {sch.SHIFT_LABEL[kind]} — отмечать нечего", show_alert=True)
        return
    await cb.message.answer(
        f"<b>Отметка за {today:%d.%m}</b>\n{sch.SHIFT_LABEL[kind]} смена",
        reply_markup=attendance_kb(today).as_markup(),
    )
    await cb.answer()


@router.callback_query(F.data == "mn:stazh")
async def cb_stazh(cb: CallbackQuery) -> None:
    async with Session() as s:
        user = await s.get(User, cb.from_user.id)
        if not user:
            await cb.answer("Сначала /start", show_alert=True)
            return
        text = await stats_text(s, user)
    await cb.message.answer(text)
    await cb.answer()


@router.callback_query(F.data == "mn:otpusk_info")
async def cb_otpusk_info(cb: CallbackQuery) -> None:
    await cb.message.answer(
        "🏖 <b>Отпуск</b>\n\n"
        "Добавить: <code>/otpusk 10.10.2026 24.10.2026</code>\n"
        "В период отпуска уведомления не приходят.\n"
        "Очистить: <code>/otpusk clear</code>"
    )
    await cb.answer()


@router.callback_query(F.data == "mn:bolnichny_info")
async def cb_bolnichny_info(cb: CallbackQuery) -> None:
    await cb.message.answer(
        "🤒 <b>Отметить пропуск</b>\n\n"
        "Один день: <code>/bolnichny 10.10.2026</code>\n"
        "Период: <code>/bolnichny 10.10.2026 20.10.2026</code>\n\n"
        "Статусы: больничный, отгул или прогул — "
        "бот проставит только на рабочие смены в диапазоне."
    )
    await cb.answer()


@router.callback_query(F.data == "mn:hired_info")
async def cb_hired_info(cb: CallbackQuery) -> None:
    user = await get_user(cb.from_user.id)
    if user and user.hired_at:
        await cb.message.answer(
            f"📅 Дата устройства: <b>{user.hired_at:%d.%m.%Y}</b>\n\n"
            "Изменить: <code>/ustroilsya 15.03.2024</code>"
        )
    else:
        await cb.message.answer(
            "📅 <b>Дата устройства не указана</b>\n\n"
            "Укажи: <code>/ustroilsya 15.03.2024</code>\n"
            "После этого посчитаю стаж и часы за весь период."
        )
    await cb.answer()


@router.callback_query(F.data == "mn:beer_info")
async def cb_beer_info(cb: CallbackQuery) -> None:
    await cb.message.answer(
        "🍺 <b>Как работает опрос</b>\n\n"
        f"За {settings.beer_lead_min} минут до конца каждой дневной смены "
        "всем приходит вопрос — идёшь после смены или нет.\n\n"
        "Ответившие «да» видят друг друга. В момент конца смены "
        "участники получают итоговый список и место встречи.\n\n"
        f"Место: <b>{settings.beer_place}</b>"
    )
    await cb.answer()
