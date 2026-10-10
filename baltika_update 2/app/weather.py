"""Погода через Open-Meteo — без ключа и регистрации.

Кэш на 15 минут: бот дёргает API не чаще, чем раз в четверть часа на точку,
сколько бы человек ни жало /pogoda. При недоступности сети отдаём None,
и вызывающий код просто не показывает погодную строку — уведомление
о смене должно уйти в любом случае.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import aiohttp

log = logging.getLogger(__name__)

# Завод «Балтика», 6-й Верхний переулок, 3 — Санкт-Петербург
PLANT_LAT = 60.0459
PLANT_LON = 30.3339

API = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL = timedelta(minutes=15)
TIMEOUT = aiohttp.ClientTimeout(total=8)

# Коды WMO: https://open-meteo.com/en/docs
WMO: dict[int, tuple[str, str]] = {
    0: ("☀️", "ясно"),
    1: ("🌤", "малооблачно"),
    2: ("⛅️", "переменная облачность"),
    3: ("☁️", "пасмурно"),
    45: ("🌫", "туман"),
    48: ("🌫", "изморозь"),
    51: ("🌦", "морось"),
    53: ("🌦", "морось"),
    55: ("🌦", "сильная морось"),
    56: ("🌧", "ледяная морось"),
    57: ("🌧", "ледяная морось"),
    61: ("🌧", "небольшой дождь"),
    63: ("🌧", "дождь"),
    65: ("🌧", "сильный дождь"),
    66: ("🌧", "ледяной дождь"),
    67: ("🌧", "ледяной дождь"),
    71: ("🌨", "небольшой снег"),
    73: ("🌨", "снег"),
    75: ("❄️", "сильный снег"),
    77: ("🌨", "снежная крупа"),
    80: ("🌦", "ливень"),
    81: ("🌧", "ливень"),
    82: ("⛈", "сильный ливень"),
    85: ("🌨", "снегопад"),
    86: ("❄️", "сильный снегопад"),
    95: ("⛈", "гроза"),
    96: ("⛈", "гроза с градом"),
    99: ("⛈", "сильная гроза с градом"),
}


def describe(code: int) -> tuple[str, str]:
    return WMO.get(code, ("🌡", "непонятно что"))


@dataclass(frozen=True)
class Point:
    """Погода на конкретный час."""
    at: datetime
    temp: float
    feels: float
    code: int
    precip_prob: int
    wind: float

    @property
    def emoji(self) -> str:
        return describe(self.code)[0]

    @property
    def text(self) -> str:
        return describe(self.code)[1]


@dataclass(frozen=True)
class Weather:
    now: Point
    hourly: tuple[Point, ...]

    def at_hour(self, when: datetime) -> Point | None:
        """Ближайший почасовой прогноз к указанному моменту."""
        if not self.hourly:
            return None
        target = when.replace(minute=0, second=0, microsecond=0)
        best = min(self.hourly, key=lambda p: abs((p.at - target).total_seconds()))
        return best if abs((best.at - target).total_seconds()) <= 5400 else None


_cache: dict[tuple[float, float], tuple[datetime, Weather]] = {}
_lock = asyncio.Lock()


def _parse(payload: dict, tz: str) -> Weather:
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(tz)
    cur = payload["current"]
    now = Point(
        at=datetime.fromisoformat(cur["time"]).replace(tzinfo=zone),
        temp=float(cur["temperature_2m"]),
        feels=float(cur["apparent_temperature"]),
        code=int(cur["weather_code"]),
        precip_prob=0,
        wind=float(cur["wind_speed_10m"]),
    )

    h = payload.get("hourly", {})
    points = []
    for i, raw_time in enumerate(h.get("time", [])):
        try:
            points.append(
                Point(
                    at=datetime.fromisoformat(raw_time).replace(tzinfo=zone),
                    temp=float(h["temperature_2m"][i]),
                    feels=float(h["apparent_temperature"][i]),
                    code=int(h["weather_code"][i]),
                    precip_prob=int(h.get("precipitation_probability", [0] * (i + 1))[i] or 0),
                    wind=float(h.get("wind_speed_10m", [0] * (i + 1))[i] or 0),
                )
            )
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return Weather(now=now, hourly=tuple(points))


async def fetch(lat: float = PLANT_LAT, lon: float = PLANT_LON,
                tz: str = "Europe/Moscow") -> Weather | None:
    key = (round(lat, 3), round(lon, 3))
    async with _lock:
        hit = _cache.get(key)
        if hit and datetime.now() - hit[0] < CACHE_TTL:
            return hit[1]

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "hourly": "temperature_2m,apparent_temperature,weather_code,precipitation_probability,wind_speed_10m",
        "timezone": tz,
        "forecast_days": 3,
        "wind_speed_unit": "ms",
    }
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.get(API, params=params) as resp:
                resp.raise_for_status()
                payload = await resp.json()
        weather = _parse(payload, tz)
    except Exception as exc:
        log.warning("погода недоступна: %s", exc)
        return None

    async with _lock:
        _cache[key] = (datetime.now(), weather)
    return weather


# ─────────────────────────── тексты ─────────────────────────────────────


def advice(p: Point) -> str:
    """Короткий совет по экипировке — от ощущаемой температуры и осадков."""
    if p.feels <= -20:
        return "Одевайся как капуста, слоями. Это не шутка."
    if p.feels <= -10:
        return "Шапка и нормальные перчатки обязательны."
    if p.feels <= 0:
        return "Ниже нуля по ощущениям — куртку потеплее."
    if p.code in (61, 63, 65, 80, 81, 82, 51, 53, 55):
        return "Зонт или капюшон. Мокнуть всю смену — так себе план."
    if p.code in (71, 73, 75, 85, 86, 77):
        return "Снег. Обувь с нормальной подошвой."
    if p.code in (95, 96, 99):
        return "Гроза. Под деревьями на остановке не стой."
    if p.feels >= 25:
        return "Жара. Воду с собой возьми."
    return "Погода нормальная, без сюрпризов."


def line_now(w: Weather) -> str:
    p = w.now
    return (
        f"{p.emoji} {p.temp:+.0f}°, ощущается {p.feels:+.0f}°, "
        f"{p.text}, ветер {p.wind:.0f} м/с"
    )


def line_at(w: Weather, when: datetime, label: str) -> str:
    p = w.at_hour(when)
    if p is None:
        return ""
    rain = f", осадки {p.precip_prob}%" if p.precip_prob >= 30 else ""
    return f"{p.emoji} {label}: {p.temp:+.0f}° (ощущается {p.feels:+.0f}°), {p.text}{rain}"


def full_text(w: Weather, shift_start: datetime | None = None,
              shift_end: datetime | None = None) -> str:
    parts = [f"<b>Погода на заводе</b>\n{line_now(w)}", advice(w.now)]
    extra = []
    if shift_start:
        extra.append(line_at(w, shift_start, f"К началу смены ({shift_start:%d.%m %H:%M})"))
    if shift_end:
        extra.append(line_at(w, shift_end, f"К концу смены ({shift_end:%d.%m %H:%M})"))
    extra = [x for x in extra if x]
    if extra:
        parts.append("\n".join(extra))
    return "\n\n".join(parts)
