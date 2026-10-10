"""Развозка «Балтики»: расписание корпоративных автобусов от метро и обратно.

Расписание статичное, живёт в коде — меняется редко, зато не требует БД.
Различаются будни и выходные (сб/вс). Праздники не учитываются: в них
на заводе обычно действует расписание выходного дня, но проверять надо
по факту.

Логика подбора:
  на работу  — последние рейсы, отправляющиеся не позже чем за buffer минут
               до начала смены;
  с работы   — первые рейсы, отправляющиеся не раньше конца смены.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta


def _t(raw: str) -> time:
    h, m = raw.split(":")
    return time(int(h), int(m))


def _times(*raw: str) -> tuple[time, ...]:
    return tuple(_t(x) for x in raw)


@dataclass(frozen=True)
class Route:
    key: str
    station: str                       # короткое имя для кнопок
    title: str                         # полное имя станции метро
    to_work_weekday: tuple[time, ...]
    to_work_weekend: tuple[time, ...]
    from_work_weekday: tuple[time, ...]
    from_work_weekend: tuple[time, ...]

    def to_work(self, d: date) -> tuple[time, ...]:
        return self.to_work_weekend if is_weekend(d) else self.to_work_weekday

    def from_work(self, d: date) -> tuple[time, ...]:
        return self.from_work_weekend if is_weekend(d) else self.from_work_weekday


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


ROUTES: dict[str, Route] = {
    "parnas": Route(
        key="parnas",
        station="Парнас",
        title="метро «Парнас»",
        to_work_weekday=_times(
            "6:50", "7:05", "7:20", "7:35", "7:50", "8:05", "8:25", "8:40", "8:55",
            "9:30", "10:00", "16:30", "16:55", "17:05", "17:30", "17:50", "18:15",
            "18:35", "19:10", "19:40", "20:10",
        ),
        to_work_weekend=_times("7:15", "7:45", "8:15", "8:45", "9:15", "18:45", "19:15", "19:45", "20:15"),
        from_work_weekday=_times(
            "7:05", "7:35", "7:50", "8:10", "8:25", "8:40", "9:15", "9:45", "16:15",
            "16:40", "16:50", "17:15", "17:30", "17:55", "18:00", "18:20", "18:55",
            "19:25", "19:55", "20:10", "20:30",
        ),
        from_work_weekend=_times("7:30", "8:00", "8:30", "9:00", "19:00", "19:30", "20:00", "20:30"),
    ),
    "prosvet": Route(
        key="prosvet",
        station="Пр. Просвещения",
        title="метро «Проспект Просвещения»",
        to_work_weekday=_times("7:10", "8:40", "19:10"),
        to_work_weekend=_times("7:10", "19:10"),
        from_work_weekday=_times("8:20", "16:45", "17:45", "20:30"),
        from_work_weekend=_times("8:20", "20:30"),
    ),
    "grazhdanka": Route(
        key="grazhdanka",
        station="Гражданский пр.",
        title="метро «Гражданский проспект»",
        to_work_weekday=_times("7:00", "7:05", "8:25", "9:00", "17:20", "19:00"),
        to_work_weekend=_times("7:05", "8:45", "19:10"),
        from_work_weekday=_times("7:55", "8:25", "16:45", "17:45", "18:25", "20:30"),
        from_work_weekend=_times("8:20", "18:40", "20:30"),
    ),
    "devyatkino": Route(
        key="devyatkino",
        station="Девяткино",
        title="метро «Девяткино»",
        to_work_weekday=_times("7:05", "8:05", "19:10"),
        to_work_weekend=_times("7:20", "19:10"),
        from_work_weekday=_times("8:35", "16:45", "17:30", "20:20"),
        from_work_weekend=_times("8:35", "20:30"),
    ),
}

DEFAULT_BUFFER_MIN = 20


def _combine(d: date, t: time, tz) -> datetime:
    return datetime.combine(d, t, tzinfo=tz)


def to_work_buses(route: Route, shift_start: datetime, buffer_min: int = DEFAULT_BUFFER_MIN,
                  limit: int = 2) -> list[datetime]:
    """Последние рейсы от метро, успевающие к началу смены.

    Возвращает от старшего к младшему: [самый поздний удобный, запасной пораньше].
    """
    tz = shift_start.tzinfo
    deadline = shift_start - timedelta(minutes=buffer_min)
    day = shift_start.date()
    fits = [
        _combine(day, t, tz)
        for t in route.to_work(day)
        if _combine(day, t, tz) <= deadline
    ]
    return sorted(fits, reverse=True)[:limit]


def from_work_buses(route: Route, shift_end: datetime, limit: int = 2) -> list[datetime]:
    """Первые рейсы с завода после окончания смены (в т.ч. на следующий день)."""
    tz = shift_end.tzinfo
    out: list[datetime] = []
    for offset in (0, 1):
        day = shift_end.date() + timedelta(days=offset)
        for t in route.from_work(day):
            dt = _combine(day, t, tz)
            if dt >= shift_end:
                out.append(dt)
        if out:
            break
    return sorted(out)[:limit]


def timetable_text(route: Route, d: date) -> str:
    """Полное расписание маршрута на конкретный тип дня."""
    kind = "выходные" if is_weekend(d) else "будни"

    def row(items: tuple[time, ...]) -> str:
        return "  ".join(t.strftime("%H:%M") for t in items) or "—"

    return (
        f"<b>🚌 {route.title}</b>\n"
        f"<i>расписание на {kind}</i>\n\n"
        f"<b>Метро → Завод</b>\n<code>{row(route.to_work(d))}</code>\n\n"
        f"<b>Завод → Метро</b>\n<code>{row(route.from_work(d))}</code>"
    )
