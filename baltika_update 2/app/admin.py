"""Админ-панель. Доступ по списку ADMIN_IDS из .env."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select

from . import beer as be
from . import cleanup as cl
from . import schedule as sch
from .config import settings
from .db import BeerEvent, BeerVote, PendingDelete, Phrase, Session, User

log = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


class Broadcast(StatesGroup):
    pick = State()      # выбор получателей (только для выборочной рассылки)
    text = State()
    confirm = State()


def panel_kb() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика", callback_data="adm:stats")
    kb.button(text="👥 Пользователи", callback_data="adm:users")
    kb.button(text="📢 Рассылка", callback_data="adm:cast")
    kb.button(text="🍺 События", callback_data="adm:beer")
    kb.button(text="🧹 Очередь удаления", callback_data="adm:queue")
    kb.adjust(2, 2, 1)
    return kb


@router.message(Command("admin", "админка"))
async def cmd_admin(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("<b>Панель управления</b>", reply_markup=panel_kb().as_markup())


@router.callback_query(F.data == "adm:stats")
async def adm_stats(cb: CallbackQuery) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer()
        return

    async with Session() as s:
        total = (await s.execute(select(func.count(User.tg_id)))).scalar_one()
        active = (
            await s.execute(select(func.count(User.tg_id)).where(User.is_active.is_(True)))
        ).scalar_one()
        with_bus = (
            await s.execute(
                select(func.count(User.tg_id)).where(User.shuttle_route.isnot(None))
            )
        ).scalar_one()
        phrases = (await s.execute(select(func.count(Phrase.id)))).scalar_one()
        queued = (await s.execute(select(func.count(PendingDelete.id)))).scalar_one()
        week_ago = datetime.now().astimezone() - timedelta(days=7)
        votes = (
            await s.execute(
                select(func.count(BeerVote.id)).where(
                    BeerVote.yes.is_(True), BeerVote.voted_at >= week_ago
                )
            )
        ).scalar_one()
        patterns = (
            await s.execute(
                select(User.pattern, func.count(User.tg_id))
                .group_by(User.pattern)
                .order_by(func.count(User.tg_id).desc())
            )
        ).all()

    lines = [
        "<b>📊 Статистика</b>",
        f"Пользователей: {total} (активных {active})",
        f"С развозкой: {with_bus}",
        f'Согласий "по пиву" за неделю: {votes}',
        f"Фраз в банке: {phrases}",
        f"В очереди на удаление: {queued}",
    ]
    if patterns:
        lines.append("\n<b>Графики</b>")
        lines += [f"<code>{p}</code> — {n}" for p, n in patterns]

    await cb.message.edit_text("\n".join(lines), reply_markup=panel_kb().as_markup())
    await cb.answer()


@router.callback_query(F.data == "adm:users")
async def adm_users(cb: CallbackQuery) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer()
        return

    async with Session() as s:
        users = (
            await s.execute(select(User).order_by(User.created_at.desc()).limit(20))
        ).scalars().all()

    if not users:
        text = "Пока никого."
    else:
        rows = []
        for u in users:
            cfg = sch.ShiftConfig(pattern=u.pattern, anchor=u.anchor, tz=u.tz)
            today = sch.SHIFT_LABEL[cfg.kind(cfg.now().date())]
            mark = "" if u.is_active else " ⛔️"
            rows.append(f"{be.display_name(u, u.tg_id)} — {today}{mark}")
        text = "<b>👥 Последние 20</b>\n\n" + "\n".join(rows)

    await cb.message.edit_text(text, reply_markup=panel_kb().as_markup())
    await cb.answer()


@router.callback_query(F.data == "adm:beer")
async def adm_beer(cb: CallbackQuery) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer()
        return

    async with Session() as s:
        events = (
            await s.execute(select(BeerEvent).order_by(BeerEvent.shift_end.desc()).limit(7))
        ).scalars().all()
        rows = []
        for e in events:
            yes = sum(1 for v in e.votes if v.yes)
            no = sum(1 for v in e.votes if not v.yes)
            rows.append(f"{e.shift_end:%d.%m %H:%M} — да {yes}, нет {no} · {e.place}")

    text = "<b>🍺 Последние события</b>\n\n" + ("\n".join(rows) if rows else "Пока пусто.")
    await cb.message.edit_text(text, reply_markup=panel_kb().as_markup())
    await cb.answer()


@router.callback_query(F.data == "adm:queue")
async def adm_queue(cb: CallbackQuery, bot: Bot) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer()
        return

    async with Session() as s:
        total = (await s.execute(select(func.count(PendingDelete.id)))).scalar_one()
        removed = await cl.sweep(bot, s, limit=500)

    await cb.answer(f"В очереди было {total}, удалено сейчас {removed}", show_alert=True)


# ─────────────────────────── рассылка ───────────────────────────────────


@router.callback_query(F.data == "adm:cast")
async def adm_cast(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer()
        return
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Всем активным", callback_data="cast:all")
    kb.button(text="🎯 Выборочно", callback_data="cast:pick")
    kb.adjust(1)
    await cb.message.edit_text("Кому отправить?", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data == "cast:all")
async def cast_all(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer()
        return
    await state.set_state(Broadcast.text)
    await state.update_data(ids=None)
    await cb.message.edit_text(
        "Пришли текст рассылки одним сообщением.\n"
        "HTML поддерживается. Отмена — /otmena"
    )
    await cb.answer()


PICK_LIMIT = 60


async def _pick_markup(ids: set[int]) -> InlineKeyboardMarkup:
    async with Session() as s:
        users = (
            await s.execute(
                select(User)
                .where(User.is_active.is_(True))
                .order_by(User.first_name, User.tg_id)
                .limit(PICK_LIMIT)
            )
        ).scalars().all()
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for u in users:
        name = u.first_name or (f"@{u.username}" if u.username else str(u.tg_id))
        mark = "✅" if u.tg_id in ids else "⬜"
        row.append(InlineKeyboardButton(text=f"{mark} {name}"[:60], callback_data=f"castpick:{u.tg_id}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text=f"Далее · выбрано {len(ids)}", callback_data="castpick:go")])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="cast:no")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "cast:pick")
async def cast_pick(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer()
        return
    await state.set_state(Broadcast.pick)
    await state.update_data(ids=[])
    await cb.message.edit_text(
        f"Отметь получателей (первые {PICK_LIMIT} активных), потом нажми «Далее».",
        reply_markup=await _pick_markup(set()),
    )
    await cb.answer()


@router.callback_query(Broadcast.pick, F.data.startswith("castpick:"))
async def cast_toggle(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer()
        return
    value = cb.data.split(":", 1)[1]
    ids = set((await state.get_data()).get("ids") or [])

    if value == "go":
        if not ids:
            await cb.answer("Никого не выбрано", show_alert=True)
            return
        await state.update_data(ids=sorted(ids))
        await state.set_state(Broadcast.text)
        await cb.message.edit_text(
            f"Получателей выбрано: {len(ids)}.\n"
            "Пришли текст рассылки одним сообщением. HTML поддерживается. Отмена — /otmena"
        )
        await cb.answer()
        return

    ids.symmetric_difference_update({int(value)})
    await state.update_data(ids=sorted(ids))
    await cb.message.edit_reply_markup(reply_markup=await _pick_markup(ids))
    await cb.answer()


@router.callback_query(Broadcast.pick, F.data == "cast:no")
async def cast_pick_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.message.edit_text("Рассылка отменена.")
    await cb.answer()


@router.message(Command("otmena", "отмена"))
async def cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        return
    await state.clear()
    await message.answer("Отменено.")


@router.message(Broadcast.text)
async def cast_preview(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.update_data(text=message.html_text)
    await state.set_state(Broadcast.confirm)

    ids = (await state.get_data()).get("ids")
    async with Session() as s:
        if ids:
            count = len(ids)
        else:
            count = (
                await s.execute(select(func.count(User.tg_id)).where(User.is_active.is_(True)))
            ).scalar_one()

    kb = InlineKeyboardBuilder()
    kb.button(text=f"📢 Отправить ({count})", callback_data="cast:go")
    kb.button(text="Отмена", callback_data="cast:no")
    kb.adjust(1)
    await message.answer(
        f"<b>Предпросмотр</b>\n\n{message.html_text}\n\n"
        f"Получателей: {count}",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(Broadcast.confirm, F.data == "cast:no")
async def cast_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.message.edit_text("Рассылка отменена.")
    await cb.answer()


@router.callback_query(Broadcast.confirm, F.data == "cast:go")
async def cast_send(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer()
        return

    data = await state.get_data()
    await state.clear()
    text = data.get("text", "")
    if not text:
        await cb.answer("Пустой текст", show_alert=True)
        return

    ids = data.get("ids")
    query = select(User).where(User.is_active.is_(True))
    if ids:                                   # выборочная рассылка: только отмеченные
        query = query.where(User.tg_id.in_(ids))
    async with Session() as s:
        users = (await s.execute(query)).scalars().all()
        targets = [(u.tg_id, u.autoclean, u.clean_after_min) for u in users]

    await cb.message.edit_text(f"Отправляю {len(targets)}…")

    sem = asyncio.Semaphore(settings.send_concurrency)
    ok = failed = 0

    async def one(uid: int, autoclean: bool, ttl: int) -> None:
        nonlocal ok, failed
        async with sem:
            try:
                sent = await bot.send_message(uid, text)
                ok += 1
            except Exception:
                failed += 1
                return
        if autoclean and ttl:
            async with Session() as s:
                await cl.schedule(
                    s, sent.chat.id, sent.message_id,
                    datetime.now().astimezone() + timedelta(minutes=ttl * 4),
                )

    await asyncio.gather(*(one(*t) for t in targets), return_exceptions=True)
    await cb.message.edit_text(f"Готово. Доставлено {ok}, не дошло {failed}.")
    await cb.answer()
