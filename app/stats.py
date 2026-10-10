"""Стаж и посещаемость.

Принцип учёта: план берётся из графика, а руками отмечаются только
исключения. Прошедшая смена без отметки считается отработанной — иначе
один забытый день ломал бы всю статистику. Явная отметка «вышел» просто
подтверждает и убирает смену из числа неподтверждённых.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import schedule as sch
from .db import Attendance, User

WORKED = "worked"
SICK = "sick"
VACATION = "vacation"
DAYOFF = "dayoff"
ABSENT = "absent"

MISSED = (SICK, VACATION, DAYOFF, ABSENT)

STATUS_LABEL = {
    WORKED: ("✅", "Отработано"),
    SICK: ("🤒", "Больничный"),
    VACATION: ("🏖", "Отпуск"),
    DAYOFF: ("📄", "Отгул"),
    ABSENT: ("🚫", "Пропуск"),
}


def plural(n: int, one: str, few: str, many: str) -> str:
    return sch.plural(n, one, few, many)


def tenure(hired: date, today: date) -> tuple[int, int, int, int]:
    """(лет, месяцев, дней, всего дней) — календарный стаж.

    Считаем через якорь «дата устройства + N лет M месяцев», иначе на
    датах вроде 31 января против 1 марта получается отрицательный остаток.
    """
    total = (today - hired).days
    years = today.year - hired.year
    months = today.month - hired.month
    if today.day < hired.day:
        months -= 1
    if months < 0:
        years -= 1
        months += 12

    y = hired.year + years
    m = hired.month + months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    anchor = date(y, m, min(hired.day, calendar.monthrange(y, m)[1]))
    return years, months, (today - anchor).days, total


def tenure_text(hired: date, today: date) -> str:
    y, m, d, total = tenure(hired, today)
    parts = []
    if y:
        parts.append(f"{y} {plural(y, 'год', 'года', 'лет')}")
    if m:
        parts.append(f"{m} {plural(m, 'месяц', 'месяца', 'месяцев')}")
    if d or not parts:
        parts.append(f"{d} {plural(d, 'день', 'дня', 'дней')}")
    return " ".join(parts)


@dataclass
class Stats:
    hired: date
    today: date
    planned_shifts: int = 0
    planned_hours: float = 0.0
    worked_shifts: int = 0
    worked_hours: float = 0.0
    unconfirmed: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    missed: dict[str, tuple[int, float]] = field(default_factory=dict)

    @property
    def missed_shifts(self) -> int:
        return sum(n for n, _ in self.missed.values())

    @property
    def missed_hours(self) -> float:
        return sum(h for _, h in self.missed.values())

    @property
    def rate(self) -> float:
        if not self.planned_shifts:
            return 0.0
        return self.worked_shifts / self.planned_shifts


def shift_hours(cfg: sch.ShiftConfig, kind: str) -> float:
    return float(cfg.day_hours if kind == sch.DAY else cfg.night_hours)


async def build(session: AsyncSession, user: User, cfg: sch.ShiftConfig) -> Stats | None:
    if user.hired_at is None:
        return None

    today = cfg.now().date()
    if user.hired_at > today:
        return None

    rows = (
        await session.execute(
            select(Attendance).where(
                Attendance.user_id == user.tg_id, Attendance.shift_date >= user.hired_at
            )
        )
    ).scalars().all()
    marks = {r.shift_date: r.status for r in rows}

    st = Stats(hired=user.hired_at, today=today)
    day = user.hired_at
    while day < today:
        kind = cfg.kind(day)
        if kind in sch.WORK:
            hours = shift_hours(cfg, kind)
            st.planned_shifts += 1
            st.planned_hours += hours
            status = marks.get(day, WORKED)
            if status in MISSED:
                n, h = st.missed.get(status, (0, 0.0))
                st.missed[status] = (n + 1, h + hours)
            else:
                st.worked_shifts += 1
                st.worked_hours += hours
                st.by_kind[kind] = st.by_kind.get(kind, 0) + 1
                if day not in marks:
                    st.unconfirmed += 1
        day += timedelta(days=1)
    return st


def bar(value: float, width: int = 10) -> str:
    filled = round(max(0.0, min(1.0, value)) * width)
    return "▓" * filled + "░" * (width - filled)


def render(stats: Stats, name: str) -> str:
    y, m, d, total_days = tenure(stats.hired, stats.today)
    hours = int(stats.worked_hours)
    minutes = hours * 60
    full_days = stats.worked_hours / 24

    lines = [
        "<b>📊 СТАЖ И СТАТИСТИКА</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"👷 {name}",
        f"📅 В строю с {stats.hired:%d.%m.%Y}",
        f"    {tenure_text(stats.hired, stats.today)} · {total_days} "
        f"{plural(total_days, 'день', 'дня', 'дней')}",
        "",
        "<b>⏱ ОТРАБОТАНО</b>",
        f"<code>{bar(stats.rate)}</code> {stats.rate * 100:.0f}%",
        f"Смен: <b>{stats.worked_shifts}</b> из {stats.planned_shifts} по графику",
        f"Часов: <b>{hours:,}</b>".replace(",", " "),
        f"Минут: <b>{minutes:,}</b>".replace(",", " "),
        f"Это <b>{full_days:.1f}</b> {plural(int(full_days), 'сутки', 'суток', 'суток')} "
        f"непрерывной работы",
    ]

    if stats.by_kind:
        day_n = stats.by_kind.get(sch.DAY, 0)
        night_n = stats.by_kind.get(sch.NIGHT, 0)
        lines += ["", "<b>🌗 РАСКЛАД</b>",
                  f"☀️ Дневных: {day_n}",
                  f"🌙 Ночных: {night_n}"]

    if stats.missed:
        lines += ["", "<b>🚫 ПРОПУЩЕНО</b>"]
        for status, (n, h) in sorted(stats.missed.items(), key=lambda x: -x[1][0]):
            emoji, label = STATUS_LABEL[status]
            lines.append(f"{emoji} {label}: {n} {plural(n, 'смена', 'смены', 'смен')} · {int(h)} ч")
        lines.append(f"Всего: {stats.missed_shifts} "
                     f"{plural(stats.missed_shifts, 'смена', 'смены', 'смен')} "
                     f"({int(stats.missed_hours)} ч)")
    else:
        lines += ["", "<b>🚫 ПРОПУЩЕНО</b>", "Ни одной смены. Железный человек."]

    if stats.unconfirmed:
        lines += ["", f"<i>Без отметки: {stats.unconfirmed} — засчитаны как отработанные</i>"]

    lines += ["━━━━━━━━━━━━━━━━━━━━"]
    return "\n".join(lines)
