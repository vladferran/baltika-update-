from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import delete, select

from . import schedule as sch
from . import shuttle as sh
from . import beer as be
from . import cleanup as cl
from . import attendance as att
from . import stats as stt
from . import phrases as ph
from .config import settings
from .db import BeerEvent, Session, User, Vacation
from .appkb import ATTEND_TEXT, app_only_kb, with_app
from .service import (calendar_text, cfg_from_user, render, shuttle_text,
                      stats_text, status_text, weather_text)

router = Router()

DATE_RE = re.compile(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})$")
TIME_RE = re.compile(r"^(\d{1,2})[:.](\d{2})$")

HELP = (
    "<b>Что я умею</b>\n\n"
    "/skolko — сколько до конца смены и до выходных\n"
    "/grafik — календарь на 14 дней\n"
    "/razvozka — расписание развозки\n"
    "/pogoda — погода на заводе\n"
    "/pivo — кто идёт после смены\n"
    "/stazh — стаж, часы и пропуски\n"
    "/otmetka — отметиться по смене\n"
    "/bolnichny 10.09 14.09 — отметить пропуск\n"
    "/clean — вычистить чат прямо сейчас\n"
    "/nastroiki — уведомления и градус сарказма\n"
    "/otpusk — добавить отпуск (в отпуске молчу)\n"
    "/perenastroit — заново задать график\n"
    "/stop — отключить уведомления, /go — включить"
)


class Setup(StatesGroup):
    pattern = State()
    custom = State()
    anchor = State()
    times = State()


# ─────────────────────────── утилиты ────────────────────────────────────



DEFAULT_TTL_MIN = 180


async def reply(message: Message, text: str, reply_markup=None,
                ttl_min: int | None = None, keep: bool = False) -> Message:
    """Отвечает и ставит на автоудаление ответ вместе с командой пользователя."""
    sent = await message.answer(text, reply_markup=with_app(reply_markup))
    if keep:
        return sent

    async with Session() as s:
        user = await s.get(User, message.chat.id)
        if user is not None and not user.autoclean:
            return sent
        minutes = ttl_min if ttl_min is not None else (
            user.clean_after_min if user else DEFAULT_TTL_MIN
        )
        if not minutes:
            return sent
        die = datetime.now().astimezone() + timedelta(minutes=minutes)
        await cl.schedule(s, sent.chat.id, sent.message_id, die)
        if message.from_user and not message.from_user.is_bot:
            await cl.schedule(s, message.chat.id, message.message_id, die)
    return sent


async def get_user(tg_id: int) -> User | None:
    async with Session() as s:
        return await s.get(User, tg_id)


def parse_date(text: str) -> date:
    m = DATE_RE.match(text.strip())
    if not m:
        raise ValueError("формат ДД.ММ.ГГГГ")
    d, mo, y = (int(x) for x in m.groups())
    if y < 100:
        y += 2000
    return date(y, mo, d)


def parse_times(text: str) -> tuple[time, int, time, int]:
    """'8:00-20:00 20:00-8:00' -> (день, 12ч, ночь, 12ч)."""
    parts = re.findall(r"(\d{1,2})[:.](\d{2})", text)
    if len(parts) < 4:
        raise ValueError("нужно 4 времени: начало и конец дневной, начало и конец ночной")
    t = [time(int(h) % 24, int(m)) for h, m in parts[:4]]

    def span(a: time, b: time) -> int:
        delta = (datetime.combine(date(2000, 1, 2), b) - datetime.combine(date(2000, 1, 1), a))
        hours = int(delta.total_seconds() // 3600) % 24
        return hours or 24

    return t[0], span(t[0], t[1]), t[2], span(t[2], t[3])


def pattern_kb() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for key, (pat, title) in sch.PRESETS.items():
        kb.button(text=title, callback_data=f"pat:{key}")
    kb.button(text="✏️ Свой цикл", callback_data="pat:custom")
    kb.adjust(1)
    return kb


# ─────────────────────────── онбординг ──────────────────────────────────


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    user = await get_user(message.from_user.id)
    if user:
        async with Session() as s:
            user = await s.get(User, message.from_user.id)
            await reply(message, await status_text(s, user) + "\n\n" + HELP)
        return

    await state.set_state(Setup.pattern)
    await reply(
        message,
        "Привет! Я присылаю напоминания перед сменой, считаю дни до выходных "
        "и показываю развозку.\n\n"
        "Всё управление — в приложении: кнопка «📱 Открыть в приложении» ниже "
        "или слева от поля ввода.\n\n"
        "<b>Шаг 1 из 3.</b> Выбери свой цикл смен:",
        reply_markup=pattern_kb().as_markup(),
        keep=True,
    )


@router.callback_query(F.data.startswith("pat:"))
async def pick_pattern(cb: CallbackQuery, state: FSMContext) -> None:
    key = cb.data.split(":", 1)[1]
    if key == "custom":
        await state.set_state(Setup.custom)
        await cb.message.edit_text(
            "Напиши свой цикл буквами:\n"
            "<code>Д</code> — дневная, <code>Н</code> — ночная, <code>В</code> — выходной\n\n"
            "Например: <code>ДДВННВВВ</code>"
        )
        await cb.answer()
        return

    pattern = sch.PRESETS[key][0]
    await state.update_data(pattern=pattern)
    await ask_anchor(cb.message, state, pattern)
    await cb.answer()


@router.message(Setup.custom)
async def set_custom(message: Message, state: FSMContext) -> None:
    try:
        pattern = sch.normalize_pattern(message.text or "")
    except ValueError as e:
        await reply(message, f"Не понял цикл: {e}. Попробуй ещё раз, например <code>ДДВННВВВ</code>")
        return
    await state.update_data(pattern=pattern)
    await ask_anchor(message, state, pattern)


async def ask_anchor(message: Message, state: FSMContext, pattern: str) -> None:
    await state.set_state(Setup.anchor)
    first = pattern[0]
    word = {"Д": "дневная", "Н": "ночная", "В": "выходной"}[first]
    kb = InlineKeyboardBuilder()
    kb.button(text="Сегодня", callback_data="anchor:0")
    kb.button(text="Вчера", callback_data="anchor:-1")
    kb.button(text="Позавчера", callback_data="anchor:-2")
    kb.adjust(3)
    await reply(
        message,
        f"<b>Шаг 2 из 3.</b> Цикл: <code>{pattern}</code>\n\n"
        f"Когда была (или будет) первая позиция цикла — <b>{word}</b>?\n"
        "Кнопкой или датой в формате <code>ДД.ММ.ГГГГ</code>",
        reply_markup=kb.as_markup(),
        keep=True,
    )


@router.callback_query(Setup.anchor, F.data.startswith("anchor:"))
async def anchor_button(cb: CallbackQuery, state: FSMContext) -> None:
    shift = int(cb.data.split(":")[1])
    anchor = date.today() + timedelta(days=shift)
    await state.update_data(anchor=anchor.isoformat())
    await ask_times(cb.message, state)
    await cb.answer()


@router.message(Setup.anchor)
async def anchor_text(message: Message, state: FSMContext) -> None:
    try:
        anchor = parse_date(message.text or "")
    except ValueError:
        await reply(message, "Дата не читается. Напиши так: <code>30.08.2026</code>")
        return
    await state.update_data(anchor=anchor.isoformat())
    await ask_times(message, state)


async def ask_times(message: Message, state: FSMContext) -> None:
    await state.set_state(Setup.times)
    kb = InlineKeyboardBuilder()
    kb.button(text="08:00–20:00 / 20:00–08:00", callback_data="times:default")
    kb.button(text="✏️ Свои часы", callback_data="times:custom")
    kb.adjust(1)
    await reply(message, "<b>Шаг 3 из 3.</b> Часы смен:", reply_markup=kb.as_markup(), keep=True)


@router.callback_query(Setup.times, F.data == "times:default")
async def times_default(cb: CallbackQuery, state: FSMContext) -> None:
    await finish_setup(cb.message, cb.from_user, state, time(8, 0), 12, time(20, 0), 12)
    await cb.answer()


@router.callback_query(Setup.times, F.data == "times:custom")
async def times_custom(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.message.edit_text(
        "Напиши четыре времени: начало и конец дневной, потом ночной.\n"
        "Например: <code>8:00 20:00 20:00 8:00</code>"
    )
    await cb.answer()


@router.message(Setup.times)
async def times_text(message: Message, state: FSMContext) -> None:
    try:
        ds, dh, ns, nh = parse_times(message.text or "")
    except ValueError as e:
        await reply(message, f"Не разобрал: {e}\nПример: <code>8:00 20:00 20:00 8:00</code>")
        return
    await finish_setup(message, message.from_user, state, ds, dh, ns, nh)


async def finish_setup(message: Message, from_user, state: FSMContext,
                       ds: time, dh: int, ns: time, nh: int) -> None:
    data = await state.get_data()
    await state.clear()

    async with Session() as s:
        user = await s.get(User, from_user.id)
        if user is None:
            user = User(tg_id=from_user.id)
            s.add(user)
        user.username = from_user.username
        user.first_name = from_user.first_name
        user.pattern = data["pattern"]
        user.anchor = date.fromisoformat(data["anchor"])
        user.day_start, user.day_hours = ds, dh
        user.night_start, user.night_hours = ns, nh
        user.is_active = True
        await s.commit()
        await s.refresh(user)
        text = await status_text(s, user)

    await reply(message, "Готово, график записан.\n\n" + text + "\n\n" + HELP)
    await reply(message, calendar_text(user))


# ─────────────────────────── команды ────────────────────────────────────


@router.message(Command("skolko", "сколько", "s"))
async def cmd_skolko(message: Message) -> None:
    async with Session() as s:
        user = await s.get(User, message.from_user.id)
        if not user:
            await reply(message, "Сначала настрой график: /start")
            return
        await reply(message, await status_text(s, user))


@router.message(Command("grafik", "график"))
async def cmd_grafik(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await reply(message, "Сначала настрой график: /start")
        return
    await reply(message, calendar_text(user))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await reply(message, HELP)


@router.message(Command("razvozka", "развозка", "bus"))
async def cmd_shuttle(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await reply(message, "Сначала настрой график: /start")
        return
    if not user.shuttle_route:
        kb = InlineKeyboardBuilder()
        for key, r in sh.ROUTES.items():
            kb.button(text=r.station, callback_data=f"route:{key}")
        kb.adjust(2)
        await reply(message, "Откуда ездишь на развозке?", reply_markup=kb.as_markup())
        return
    await reply(message, shuttle_text(user))



@router.message(Command("pogoda", "погода", "weather"))
async def cmd_weather(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await reply(message, "Сначала настрой график: /start")
        return
    await reply(message, await weather_text(user))



@router.message(Command("pivo", "пиво", "beer"))
async def cmd_beer(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await reply(message, "Сначала настрой график: /start")
        return
    async with Session() as s:
        cfg = cfg_from_user(user)
        event = await be.nearest_event(s, cfg.now())
        if event is None:
            await reply(message, 
                "Пока ничего не запланировано. Опрос приходит сам "
                f"за {settings.beer_lead_min} минут до конца дневной смены."
            )
            return
        await reply(message, await be.event_summary(s, event))


@router.message(Command("pivo_mesto"))
async def cmd_beer_place(message: Message) -> None:
    """Сменить место встречи для ближайшего события. Только для админов."""
    if message.from_user.id not in settings.admin_ids:
        await reply(message, "Место меняет только админ бота.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await reply(message, "Куда идём? <code>/pivo_mesto Пятёрочка у проходной</code>")
        return

    async with Session() as s:
        user = await s.get(User, message.from_user.id)
        cfg = cfg_from_user(user) if user else None
        event = await be.nearest_event(s, cfg.now() if cfg else datetime.now().astimezone())
        if event is None:
            await reply(message, "Пока нет активного события.")
            return
        event.place = parts[1].strip()[:200]
        await s.commit()
        await reply(message, f"Место обновлено: {event.place}")



@router.message(Command("clean", "очистить"))
async def cmd_clean(message: Message, bot: Bot) -> None:
    async with Session() as s:
        await cl.schedule(s, message.chat.id, message.message_id,
                          datetime.now().astimezone())
        removed = await cl.purge_chat(bot, s, message.chat.id)
    note = await message.answer(f"🧹 Убрано сообщений: {removed}")
    async with Session() as s:
        await cl.schedule(s, note.chat.id, note.message_id,
                          datetime.now().astimezone() + timedelta(seconds=20))



@router.message(Command("stazh", "стаж", "statistika"))
async def cmd_stats(message: Message) -> None:
    async with Session() as s:
        user = await s.get(User, message.from_user.id)
        if not user:
            await reply(message, "Сначала настрой график: /start")
            return
        await reply(message, await stats_text(s, user), ttl_min=720)


@router.message(Command("ustroilsya", "устроился"))
async def cmd_hired(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await reply(message, "Когда устроился? <code>/ustroilsya 15.03.2024</code>")
        return
    try:
        hired = parse_date(parts[1].strip())
    except ValueError:
        await reply(message, "Дата не читается. Формат: <code>15.03.2024</code>")
        return

    async with Session() as s:
        user = await s.get(User, message.from_user.id)
        if not user:
            await reply(message, "Сначала настрой график: /start")
            return
        if hired > cfg_from_user(user).now().date():
            await reply(message, "Дата в будущем. Из будущего смены не засчитываются.")
            return
        user.hired_at = hired
        await s.commit()
        await s.refresh(user)
        await reply(message, await stats_text(s, user), ttl_min=720)


@router.message(Command("otmetka", "отметка"))
async def cmd_mark(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await reply(message, "Сначала настрой график: /start")
        return
    cfg = cfg_from_user(user)
    today = cfg.now().date()
    kind = cfg.kind(today)
    if kind not in sch.WORK:
        await reply(message, f"Сегодня {sch.SHIFT_LABEL[kind]} — отмечать нечего.")
        return
    await reply(
        message,
        f"<b>Отметка за {today:%d.%m}</b>\n{sch.SHIFT_LABEL[kind]} смена",
        reply_markup=app_only_kb(ATTEND_TEXT),
        ttl_min=720,
    )


@router.message(Command("bolnichny", "больничный", "propusk"))
async def cmd_sick(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await reply(message, "Сначала настрой график: /start")
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await reply(
            message,
            "Отметить пропуск:\n"
            "<code>/bolnichny 10.09.2026</code> — один день\n"
            "<code>/bolnichny 10.09.2026 14.09.2026</code> — период",
        )
        return
    try:
        start = parse_date(parts[1])
        finish = parse_date(parts[2]) if len(parts) > 2 else start
    except (ValueError, IndexError):
        await reply(message, "Даты не читаются. Формат: <code>10.09.2026</code>")
        return
    if finish < start:
        start, finish = finish, start

    async with Session() as s:
        n = await att.mark_range(s, user.tg_id, start, finish, stt.SICK, cfg_from_user(user))
    word = sch.plural(n, "смена", "смены", "смен")
    await reply(message, f"🤒 Отмечено как больничный: {n} {word} ({start:%d.%m} — {finish:%d.%m})")


@router.message(Command("nastroiki", "настройки"))
async def cmd_settings(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await reply(message, "Сначала настрой график: /start")
        return
    await reply(message, "<b>Настройки</b>", reply_markup=app_only_kb("⚙️ Открыть настройки в приложении"))


@router.message(Command("otpusk", "отпуск"))
async def cmd_vacation(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await reply(message, "Сначала настрой график: /start")
        return

    arg = (message.text or "").split(maxsplit=1)
    if len(arg) < 2:
        cur = "\n".join(f"• {v.start:%d.%m.%Y} — {v.finish:%d.%m.%Y}" for v in user.vacations)
        await reply(message, 
            "Добавить отпуск: <code>/otpusk 10.09.2026 24.09.2026</code>\n"
            "Очистить: <code>/otpusk clear</code>"
            + (f"\n\n<b>Сейчас записано:</b>\n{cur}" if cur else "")
        )
        return

    if arg[1].strip().lower() in ("clear", "очистить"):
        async with Session() as s:
            await s.execute(delete(Vacation).where(Vacation.user_id == user.tg_id))
            await s.commit()
        await reply(message, "Отпуска удалены.")
        return

    parts = arg[1].split()
    try:
        start, finish = parse_date(parts[0]), parse_date(parts[1])
    except (ValueError, IndexError):
        await reply(message, "Формат: <code>/otpusk 10.09.2026 24.09.2026</code>")
        return
    if finish < start:
        start, finish = finish, start

    async with Session() as s:
        s.add(Vacation(user_id=user.tg_id, start=start, finish=finish))
        await s.commit()
    await reply(message, 
        f"Отпуск {start:%d.%m.%Y} — {finish:%d.%m.%Y} записан. В эти дни не трогаю."
    )


@router.message(Command("perenastroit", "перенастроить"))
async def cmd_reconf(message: Message, state: FSMContext) -> None:
    await state.set_state(Setup.pattern)
    await reply(message, "Выбери цикл:", reply_markup=pattern_kb().as_markup())


@router.message(Command("stop"))
async def cmd_stop(message: Message) -> None:
    async with Session() as s:
        user = await s.get(User, message.from_user.id)
        if user:
            user.is_active = False
            await s.commit()
    await reply(message, "Уведомления выключены. Вернуть — /go")


@router.message(Command("go"))
async def cmd_go(message: Message) -> None:
    async with Session() as s:
        user = await s.get(User, message.from_user.id)
        if user:
            user.is_active = True
            await s.commit()
    await reply(message, "Уведомления снова включены.")


@router.callback_query(F.data.startswith(("att:", "beer:", "set:", "route:", "mn:")))
async def legacy_buttons(cb: CallbackQuery) -> None:
    """Старые кнопки в прошлых сообщениях: всё теперь делается только в приложении."""
    await cb.answer("Теперь это только в приложении: открой его слева от поля ввода", show_alert=True)
