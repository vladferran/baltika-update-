"""Движок сменных циклов.

Паттерн — строка символов:
    Д — дневная смена
    Н — ночная смена (переходит через полночь)
    В — нерабочий день

Цикл крутится бесконечно от якорной даты: anchor соответствует pattern[0].
Ключевая тонкость: одиночный В внутри блока — это межсменная передышка,
а «выходные» — блок из min_days подряд. Ночная смена «съедает» утро
первого выходного, поэтому свобода наступает в момент её окончания.

Модуль без внешних зависимостей — тестируется отдельно.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DAY = "Д"
NIGHT = "Н"
OFF = "В"
WORK = (DAY, NIGHT)

PRESETS: dict[str, tuple[str, str]] = {
    "baltika": ("ДДВННВВВ", "2 дневные / выходной / 2 ночные / 3 выходных"),
    "2d2n4o": ("ДДННВВВВ", "2 дня / 2 ночи / 4 выходных"),
    "2x2": ("ДДВВ", "2/2 только дневные"),
    "2x2dn": ("ДНВВ", "день / ночь / отсыпной / выходной"),
    "3x3": ("ДДДВВВ", "3/3 по 12 часов"),
    "5x2": ("ДДДДДВВ", "5/2 пятидневка"),
    "sutki": ("ДВВВ", "сутки через трое"),
}

SHIFT_LABEL = {DAY: "☀️ Дневная", NIGHT: "🌙 Ночная", OFF: "🏠 Выходной"}


def normalize_pattern(raw: str) -> str:
    """'ддвннввв', 'DDVNNVVV', 'Д Д В Н Н В В В' -> 'ДДВННВВВ'."""
    table = {
        "D": DAY, "Д": DAY, "1": DAY,
        "N": NIGHT, "Н": NIGHT, "2": NIGHT,
        "V": OFF, "В": OFF, "O": OFF, "О": OFF, "0": OFF, "X": OFF, "Х": OFF,
    }
    out = []
    for ch in raw.upper():
        if ch.isspace() or ch in ",/|.-_":
            continue
        if ch not in table:
            raise ValueError(f"непонятный символ {ch!r}")
        out.append(table[ch])
    if not out:
        raise ValueError("пустой паттерн")
    if len(out) > 31:
        raise ValueError("цикл длиннее 31 дня")
    if not any(c in WORK for c in out):
        raise ValueError("в цикле нет рабочих смен")
    return "".join(out)


@dataclass(frozen=True)
class ShiftConfig:
    pattern: str
    anchor: date                       # дата, в которую цикл стоит на pattern[0]
    tz: str = "Europe/Moscow"
    day_start: time = time(8, 0)
    day_hours: int = 12
    night_start: time = time(20, 0)
    night_hours: int = 12
    weekend_min_days: int = 2          # сколько В подряд считать «выходными»
    vacations: tuple[tuple[date, date], ...] = field(default_factory=tuple)

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    def now(self) -> datetime:
        return datetime.now(self.zone)

    def on_vacation(self, d: date) -> bool:
        return any(a <= d <= b for a, b in self.vacations)

    def kind(self, d: date) -> str:
        if self.on_vacation(d):
            return OFF
        return self.pattern[(d - self.anchor).days % len(self.pattern)]

    def bounds(self, d: date) -> tuple[datetime, datetime] | None:
        """Начало и конец смены, стартующей в дату d. None — выходной."""
        k = self.kind(d)
        if k == OFF:
            return None
        if k == DAY:
            start = datetime.combine(d, self.day_start, tzinfo=self.zone)
            return start, start + timedelta(hours=self.day_hours)
        start = datetime.combine(d, self.night_start, tzinfo=self.zone)
        return start, start + timedelta(hours=self.night_hours)


def current_shift(cfg: ShiftConfig, now: datetime) -> tuple[datetime, datetime] | None:
    """Смена, идущая прямо сейчас (в т.ч. ночная, начавшаяся вчера)."""
    for delta in (0, -1):
        b = cfg.bounds(now.date() + timedelta(days=delta))
        if b and b[0] <= now < b[1]:
            return b
    return None


def next_shift(cfg: ShiftConfig, now: datetime, horizon: int = 120) -> tuple[datetime, datetime] | None:
    for i in range(horizon):
        b = cfg.bounds(now.date() + timedelta(days=i))
        if b and b[0] > now:
            return b
    return None


def next_weekend(cfg: ShiftConfig, now: datetime, horizon: int = 90):
    """Ближайший блок выходных длиной >= weekend_min_days.

    Возвращает (free_at, back_at):
      free_at — момент реальной свободы (конец последней смены перед блоком),
      back_at — начало первой смены после блока.
    """
    d0 = now.date()
    i = 0
    while i < horizon:
        cur = d0 + timedelta(days=i)
        if cfg.kind(cur) != OFF:
            i += 1
            continue
        start_day = cur
        while cfg.kind(start_day - timedelta(days=1)) == OFF:
            start_day -= timedelta(days=1)
        end_day = cur
        while cfg.kind(end_day + timedelta(days=1)) == OFF:
            end_day += timedelta(days=1)

        if (end_day - start_day).days + 1 >= cfg.weekend_min_days:
            prev = cfg.bounds(start_day - timedelta(days=1))
            free_at = prev[1] if prev else datetime.combine(start_day, time(0, 0), tzinfo=cfg.zone)
            nxt = cfg.bounds(end_day + timedelta(days=1))
            back_at = nxt[0] if nxt else None
            if back_at is None or back_at > now:
                return free_at, back_at
        i = (end_day - d0).days + 1
    return None


@dataclass
class Status:
    now: datetime
    working: bool
    shift_kind: str | None
    shift_start: datetime | None
    shift_end: datetime | None
    next_start: datetime | None
    next_kind: str | None
    weekend_start: datetime | None
    weekend_end: datetime | None
    in_weekend: bool           # прямо сейчас идут настоящие выходные
    short_break: bool          # не работаем, но это лишь передышка внутри блока


def status(cfg: ShiftConfig, now: datetime | None = None) -> Status:
    now = now or cfg.now()
    cur = current_shift(cfg, now)
    nxt = next_shift(cfg, now)
    wknd = next_weekend(cfg, now)

    free_at, back_at = wknd if wknd else (None, None)
    in_weekend = (
        cur is None
        and free_at is not None
        and free_at <= now
        and (back_at is None or now < back_at)
    )

    return Status(
        now=now,
        working=cur is not None,
        shift_kind=cfg.kind(cur[0].date()) if cur else None,
        shift_start=cur[0] if cur else None,
        shift_end=cur[1] if cur else None,
        next_start=nxt[0] if nxt else None,
        next_kind=cfg.kind(nxt[0].date()) if nxt else None,
        weekend_start=free_at,
        weekend_end=back_at,
        in_weekend=in_weekend,
        short_break=cur is None and not in_weekend,
    )


def calendar(cfg: ShiftConfig, start: date, days: int = 14) -> list[tuple[date, str]]:
    return [(start + timedelta(days=i), cfg.kind(start + timedelta(days=i))) for i in range(days)]


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def human_delta(delta: timedelta) -> str:
    total = max(int(delta.total_seconds()), 0)
    d, rem = divmod(total, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    parts = []
    if d:
        parts.append(f"{d} {plural(d, 'день', 'дня', 'дней')}")
    if h:
        parts.append(f"{h} {plural(h, 'час', 'часа', 'часов')}")
    if m and not d:
        parts.append(f"{m} {plural(m, 'минута', 'минуты', 'минут')}")
    return " ".join(parts) or "меньше минуты"
