from __future__ import annotations

import random
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import phrases as ph
from . import schedule as sch
from . import shuttle as sh
from . import weather as wx
from . import stats as stt
from .db import Phrase, User


def cfg_from_user(user: User) -> sch.ShiftConfig:
    return sch.ShiftConfig(
        pattern=user.pattern,
        anchor=user.anchor,
        tz=user.tz,
        day_start=user.day_start,
        day_hours=user.day_hours,
        night_start=user.night_start,
        night_hours=user.night_hours,
        weekend_min_days=user.weekend_min_days,
        vacations=tuple((v.start, v.finish) for v in user.vacations),
    )


async def render(session: AsyncSession, category: str, level: int, **fmt) -> str:
    """Берёт фразу из БД (можно править на лету), иначе — из модуля."""
    rows = (
        await session.execute(
            select(Phrase.text).where(
                Phrase.category == category, Phrase.level == level, Phrase.enabled.is_(True)
            )
        )
    ).scalars().all()
    template = random.choice(rows) if rows else None
    if template is None:
        return ph.pick(category, level, **fmt)
    try:
        return template.format(**fmt)
    except KeyError:
        return ph.pick(category, level, **fmt)


def user_route(user: User) -> sh.Route | None:
    return sh.ROUTES.get(user.shuttle_route) if user.shuttle_route else None


def bus_hint(user: User, st: sch.Status) -> str:
    """Строка про ближайшую развозку — подклеивается к статусу."""
    route = user_route(user)
    if route is None:
        return ""

    if st.working and st.shift_end:
        buses = sh.from_work_buses(route, st.shift_end)
        if buses:
            times = ", ".join(hhmm(b) for b in buses)
            return f"\n🚌 С завода до {route.station}: {times}"
    elif st.next_start:
        buses = sh.to_work_buses(route, st.next_start, user.bus_buffer_min)
        if buses:
            times = ", ".join(hhmm(b) for b in buses)
            return f"\n🚌 От {route.station} на смену: {times}"
    return ""


def shuttle_text(user: User) -> str:
    """Ответ на /razvozka: ближайшие рейсы под смену + полное расписание."""
    route = user_route(user)
    if route is None:
        return "Маршрут развозки не выбран. Открой /nastroiki и укажи свою станцию."

    cfg = cfg_from_user(user)
    st = sch.status(cfg)
    lines = []

    if st.working and st.shift_end:
        buses = sh.from_work_buses(route, st.shift_end, limit=3)
        if buses:
            lines.append(
                f"<b>После смены</b> (конец в {hhmm(st.shift_end)}):\n"
                + "  ".join(hhmm(b) for b in buses)
            )
    if st.next_start:
        buses = sh.to_work_buses(route, st.next_start, user.bus_buffer_min, limit=3)
        if buses:
            lines.append(
                f"<b>На смену {dm(st.next_start)} к {hhmm(st.next_start)}</b>:\n"
                + "  ".join(hhmm(b) for b in buses)
            )

    head = "\n\n".join(lines)
    table = sh.timetable_text(route, cfg.now().date())
    return (head + "\n\n" + table) if head else table



async def weather_line(user: User, st: sch.Status) -> str:
    """Одна строка про погоду — к статусу и уведомлениям. Молчит при сбое."""
    if not user.show_weather:
        return ""
    w = await wx.fetch(tz=user.tz)
    if w is None:
        return ""
    return "\n" + wx.line_now(w)


async def weather_text(user: User) -> str:
    """Ответ на /pogoda: сейчас + прогноз на границы ближайшей смены."""
    w = await wx.fetch(tz=user.tz)
    if w is None:
        return "Не смог получить погоду — сервис не отвечает. Попробуй через пару минут."

    cfg = cfg_from_user(user)
    st = sch.status(cfg)
    if st.working:
        return wx.full_text(w, None, st.shift_end)
    if st.next_start:
        cur = cfg.bounds(st.next_start.date())
        return wx.full_text(w, st.next_start, cur[1] if cur else None)
    return wx.full_text(w)



async def stats_text(session, user: User) -> str:
    if user.hired_at is None:
        return (
            "Дата устройства не указана.\n\n"
            "Пришли её командой: <code>/ustroilsya 15.03.2024</code>\n"
            "После этого посчитаю стаж, отработанные часы и пропуски."
        )
    cfg = cfg_from_user(user)
    data = await stt.build(session, user, cfg)
    if data is None:
        return "Дата устройства позже сегодняшней — проверь: /ustroilsya"
    name = user.first_name or (f"@{user.username}" if user.username else "Боец")
    return stt.render(data, name)


def hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def dm(dt: datetime) -> str:
    return dt.strftime("%d.%m")


async def status_text(session: AsyncSession, user: User) -> str:
    cfg = cfg_from_user(user)
    st = sch.status(cfg)
    lvl = user.sarcasm

    if st.next_start is None and not st.working:
        return "Не могу найти ближайшую смену — проверь настройки: /nastroiki"

    if st.working:
        left = sch.human_delta(st.shift_end - st.now)
        weekend = sch.human_delta(st.weekend_start - st.now) if st.weekend_start else "—"
        body = await render(
            session, "counting", lvl,
            left=left, weekend=weekend,
            kind=ph.KIND_WORD.get(st.shift_kind, "смена"), when=hhmm(st.shift_end),
        )
        head = f"{sch.SHIFT_LABEL[st.shift_kind]} смена · до {hhmm(st.shift_end)}"
        tail = ""
        if st.weekend_start:
            tail = f"\n\n🏁 Выходные с {dm(st.weekend_start)} {hhmm(st.weekend_start)}"
            if st.weekend_end:
                tail += f" по {dm(st.weekend_end)} {hhmm(st.weekend_end)}"
        return f"<b>{head}</b>\n\n{body}{tail}{bus_hint(user, st)}" + await weather_line(user, st)

    left = sch.human_delta(st.next_start - st.now)
    kind = ph.KIND_WORD.get(st.next_kind, "смена")

    if st.in_weekend:
        body = await render(session, "resting", lvl, left=left, kind=kind, when=hhmm(st.next_start))
        head = "🏠 Выходные"
    else:
        weekend = sch.human_delta(st.weekend_start - st.now) if st.weekend_start else "—"
        body = await render(
            session, "between", lvl,
            left=left, kind=kind, when=hhmm(st.next_start), weekend=weekend,
        )
        head = "😴 Передышка между сменами"

    tail = f"\n\n▶️ Следующая: {sch.SHIFT_LABEL[st.next_kind]} {dm(st.next_start)} в {hhmm(st.next_start)}"
    if not st.in_weekend and st.weekend_start:
        tail += f"\n🏁 Выходные с {dm(st.weekend_start)} {hhmm(st.weekend_start)}"
    return f"<b>{head}</b>\n\n{body}{tail}{bus_hint(user, st)}" + await weather_line(user, st)


def calendar_text(user: User, days: int = 14) -> str:
    cfg = cfg_from_user(user)
    today = cfg.now().date()
    rows = sch.calendar(cfg, today, days)
    wd = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    lines = []
    for d, k in rows:
        mark = "👉" if d == today else "  "
        vac = " (отпуск)" if cfg.on_vacation(d) else ""
        lines.append(f"{mark} {d.strftime('%d.%m')} {wd[d.weekday()]}  {sch.SHIFT_LABEL[k]}{vac}")
    return "<b>График на " + str(days) + " дней</b>\n<code>" + "\n".join(lines) + "</code>"
