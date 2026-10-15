"""HTTP-сервер для Telegram Mini App.

Работает рядом с aiogram в том же процессе. Все запросы авторизуются через
initData от Telegram (подпись HMAC по токену бота), поэтому открыть API
чужим людям без токена бота невозможно.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web
from sqlalchemy import delete, select

from . import attendance as att
from . import beer as br
from . import schedule as sch
from . import shuttle as sh
from . import stats as stt
from . import weather as wx
from . import wellness as wl
from .config import settings
from .db import BeerEvent, BeerVote, Session, User, Vacation
from .service import cfg_from_user, user_route

log = logging.getLogger("baltika.web")

# Сборка Vite: webapp/dist/index.html + webapp/dist/assets/* (готовая, на сервере Node не нужен).
DIST = Path(__file__).resolve().parent.parent / "webapp" / "dist"
INDEX = DIST / "index.html"
ASSETS = DIST / "assets"
STATIC = Path(__file__).resolve().parent.parent / "webapp" / "static"   # логотип и прочая статика
MAX_AGE = 24 * 3600                       # initData старше суток не принимаем
MARK_STATUSES = {"worked", "sick", "vacation", "dayoff", "absent"}
MAX_RANGE_DAYS = 92                       # отпуск или больничный длиннее — почти наверняка ошибка ввода


# ---------- авторизация ----------

def verify_init_data(init_data: str, bot_token: str,
                     now: datetime | None = None, max_age: int = MAX_AGE) -> int | None:
    """Проверяет подпись initData и возвращает tg id пользователя или None.

    Схема Telegram: secret = HMAC_SHA256(key="WebAppData", msg=token),
    hash = HMAC_SHA256(key=secret, msg=data_check_string).
    """
    if not init_data or not bot_token:
        return None

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", None)
    if not received:
        return None

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return None

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        return None
    now_ts = int((now or datetime.now(timezone.utc)).timestamp())
    if now_ts - auth_date > max_age:
        return None

    try:
        return int(json.loads(pairs.get("user", ""))["id"])
    except (ValueError, KeyError, TypeError):
        return None


def _tg_id(request: web.Request) -> int | None:
    return verify_init_data(request.headers.get("X-Init-Data", ""), settings.bot_token)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _hm(times) -> list[str]:
    return [t.strftime("%H:%M") for t in times]


def _err(code: str, status: int) -> web.Response:
    return web.json_response({"error": code}, status=status)


# ---------- сборка ответа ----------

def _status_json(st: sch.Status) -> dict:
    return {
        "working": st.working,
        "shift_kind": st.shift_kind,
        "shift_start": _iso(st.shift_start),
        "shift_end": _iso(st.shift_end),
        "next_start": _iso(st.next_start),
        "next_kind": st.next_kind,
        "in_weekend": st.in_weekend,
        "short_break": st.short_break,
        "weekend_start": _iso(st.weekend_start),
        "weekend_end": _iso(st.weekend_end),
    }


def _route_block(route: sh.Route, today) -> dict:
    return {
        "key": route.key,
        "station": route.station,
        "title": route.title,
        "to_work_today": _hm(route.to_work(today)),
        "from_work_today": _hm(route.from_work(today)),
        "is_weekend": sh.is_weekend(today),
    }


def _shuttle_json(user: User, st: sch.Status) -> dict | None:
    """Свой маршрут — с ближайшими рейсами. Все маршруты — для блоков на вкладке."""
    today = st.now.date()
    route = user_route(user)
    routes = [
        {**_route_block(r, today), "is_mine": route is not None and r.key == route.key}
        for r in sh.ROUTES.values()
    ]
    if route is None:
        return {"mine": None, "routes": routes}

    to_work, from_work = [], []
    if st.working and st.shift_end:
        from_work = [_iso(b) for b in sh.from_work_buses(route, st.shift_end, limit=3)]
    elif st.next_start:
        to_work = [_iso(b) for b in sh.to_work_buses(route, st.next_start, user.bus_buffer_min)]
    return {
        "mine": {
            **_route_block(route, today),
            "next_to_work": to_work,
            "next_from_work": from_work,
        },
        "routes": routes,
    }


def _calendar_json(cfg: sch.ShiftConfig, start, days: int) -> list[dict]:
    """Каждый день с временем смены: для Д/Н — начало и конец, для В — None."""
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        k = cfg.kind(d)
        b = cfg.bounds(d)
        w = wl.access(cfg, d)
        out.append({
            "date": d.isoformat(),
            "kind": k,
            "weekend": sh.is_weekend(d),
            "start": _iso(b[0]) if b else None,
            "end": _iso(b[1]) if b else None,
            "wellness": w["state"],          # open / other / shift
            "gender": w["gender"],
        })
    return out


async def _beer_json(session, user: User, now: datetime) -> dict | None:
    if not user.beer_enabled:
        return None
    ev: BeerEvent | None = await br.nearest_event(session, now)
    if ev is None:
        return None
    names = await br.participants(session, ev.id)
    mine = (
        await session.execute(
            select(BeerVote.yes).where(BeerVote.event_id == ev.id, BeerVote.user_id == user.tg_id)
        )
    ).scalar_one_or_none()
    return {
        "event_id": ev.id,
        "place": ev.place,
        "yes_names": names,
        "yes_count": len(names),
        "my_vote": mine,            # True / False / None
    }


async def _stats_json(session, user: User, cfg: sch.ShiftConfig) -> dict | None:
    if user.hired_at is None:
        return None
    today = cfg.now().date()
    years, months, days, total = stt.tenure(user.hired_at, today)
    out = {
        "hired": user.hired_at.isoformat(),
        "years": years,
        "months": months,
        "days": days,
        "total_days": total,
    }
    s = await stt.build(session, user, cfg)
    if s is not None:
        out.update({
            "planned_shifts": s.planned_shifts,
            "worked_shifts": s.worked_shifts,
            "worked_hours": round(s.worked_hours, 1),
            "missed_shifts": s.missed_shifts,
            "missed_hours": round(s.missed_hours, 1),
            "unconfirmed": s.unconfirmed,
            "rate": round(s.rate, 3),
        })
    return out


def _vacations_json(user: User, today: date) -> list[dict]:
    """Отпуска: текущие, будущие и прошедшие за последний месяц."""
    cutoff = today - timedelta(days=30)
    rows = sorted(user.vacations, key=lambda v: v.start)
    return [
        {"id": v.id, "start": v.start.isoformat(), "finish": v.finish.isoformat(), "note": v.note}
        for v in rows if v.finish >= cutoff
    ][:20]


async def _weather_json(user: User) -> dict | None:
    if not user.show_weather:
        return None
    w = await wx.fetch(tz=user.tz)
    if w is None:
        return None
    return {"line": wx.line_now(w), "advice": wx.advice(w.now)}


# ---------- настройки ----------

BOOL_SETTINGS = (
    "notify_d2", "notify_d1", "notify_freedom", "notify_checkin",
    "beer_enabled", "show_weather", "autoclean",
)
# Значения ровно те, что циклически переключаются в боте (set:soon, set:home, ...).
CHOICE_SETTINGS = {
    "notify_soon_h": (0, 1, 2, 3),
    "notify_home_min": (0, 30, 60, 80, 120),
    "notify_bus_min": (0, 15, 30, 45, 60),
    "clean_after_min": (0, 60, 180, 360, 720),
    "sarcasm": (1, 2, 3),
}
SETTING_FIELDS = BOOL_SETTINGS + tuple(CHOICE_SETTINGS) + ("shuttle_route",)


def _settings_json(user: User) -> dict:
    out = {k: getattr(user, k) for k in SETTING_FIELDS if k != "shuttle_route"}
    out["shuttle_route"] = user.shuttle_route or "none"   # "none" = не пользуюсь развозкой
    return out


def parse_settings(body) -> dict | None:
    """Принимает только известные поля и только допустимые значения. Битый вход — None."""
    if not isinstance(body, dict):
        return None
    out: dict = {}
    for k in BOOL_SETTINGS:
        if k in body:
            if not isinstance(body[k], bool):
                return None
            out[k] = body[k]
    for k, allowed in CHOICE_SETTINGS.items():
        if k in body:
            v = body[k]
            if isinstance(v, bool) or v not in allowed:
                return None
            out[k] = v
    if "shuttle_route" in body:
        v = body["shuttle_route"]
        if v == "none" or v is None:
            out["shuttle_route"] = None
        elif isinstance(v, str) and v in sh.ROUTES:
            out["shuttle_route"] = v
        else:
            return None
    if "clean_after_min" in out:              # как в боте: 0 минут = автоочистка выключена
        out["autoclean"] = out["clean_after_min"] > 0
    return out or None


def parse_range(body) -> tuple[date, date] | None:
    """Период из запроса: start и finish (finish по умолчанию = start)."""
    if not isinstance(body, dict):
        return None
    start = _parse_day(body.get("start"))
    if start is None:
        return None
    finish = _parse_day(body.get("finish")) or start
    if finish < start:
        start, finish = finish, start
    if (finish - start).days > MAX_RANGE_DAYS:
        return None
    return start, finish


def _parse_day(value) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        d = date.fromisoformat(value)
    except ValueError:
        return None
    return d if d.year >= 1960 else None


async def _read(request: web.Request):
    """Общий вход для POST-запросов: (tg_id, тело, ошибка). Ошибка — готовый ответ."""
    tg_id = _tg_id(request)
    if tg_id is None:
        return None, None, _err("auth", 401)
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        return tg_id, None, _err("bad_json", 400)
    return tg_id, body, None


SETUP_ANCHOR_SPAN = 366                   # дата цикла не дальше года от сегодня — иначе опечатка


def parse_setup(body) -> dict | None:
    """График из приложения: цикл и дата, на которую цикл стоит на первой позиции."""
    if not isinstance(body, dict):
        return None
    try:
        pattern = sch.normalize_pattern(str(body.get("pattern", "")))
    except ValueError:
        return None
    anchor = _parse_day(body.get("anchor"))
    if anchor is None or abs((anchor - date.today()).days) > SETUP_ANCHOR_SPAN:
        return None
    return {"pattern": pattern, "anchor": anchor}


async def setup_handler(request: web.Request) -> web.Response:
    tg_id, body, err = await _read(request)
    if err:
        return err
    data = parse_setup(body)
    if data is None:
        return _err("bad_setup", 400)

    async with Session() as session:
        user = await session.get(User, tg_id)
        if user is None:
            # часы смен берём из значений по умолчанию модели; меняются в боте (/perenastroit)
            user = User(tg_id=tg_id)
            session.add(user)
        user.pattern = data["pattern"]
        user.anchor = data["anchor"]
        user.is_active = True
        await session.commit()
    return web.json_response({"ok": True})


# ---------- обработчики ----------

async def index(request: web.Request) -> web.StreamResponse:
    if not INDEX.exists():
        raise web.HTTPNotFound()
    return web.FileResponse(INDEX, headers={"Cache-Control": "no-cache"})


async def state(request: web.Request) -> web.Response:
    tg_id = _tg_id(request)
    if tg_id is None:
        return web.json_response({"error": "auth"}, status=401)
    try:
        days = min(max(int(request.query.get("days", "42")), 7), 120)
    except ValueError:
        days = 42

    async with Session() as session:
        user = await session.get(User, tg_id)
        if user is None:
            return web.json_response({"error": "not_registered"}, status=404)

        cfg = cfg_from_user(user)
        st = sch.status(cfg)
        today = cfg.now().date()
        payload = {
            "name": user.first_name or "",
            "today": today.isoformat(),
            "status": _status_json(st),
            "calendar": _calendar_json(cfg, today, days),
            "shuttle": _shuttle_json(user, st),
            "beer": await _beer_json(session, user, st.now),
            "stats": await _stats_json(session, user, cfg),
            "vacations": _vacations_json(user, today),
            "wellness": wl.access(cfg, today),
            "weather": await _weather_json(user),
            "settings": _settings_json(user),
            "schedule": {"pattern": user.pattern, "anchor": user.anchor.isoformat()},
        }
    return web.json_response(payload)


async def mark_handler(request: web.Request) -> web.Response:
    tg_id, body, err = await _read(request)
    if err:
        return err
    status = body.get("status") if isinstance(body, dict) else None
    if status not in MARK_STATUSES:
        return _err("bad_status", 400)

    async with Session() as session:
        user = await session.get(User, tg_id)
        if user is None:
            return _err("not_registered", 404)
        cfg = cfg_from_user(user)
        st = sch.status(cfg)
        ref = st.shift_start or st.next_start
        if ref is None:
            return _err("no_shift", 409)
        await att.mark(session, tg_id, ref.date(), status)
    return web.json_response({"ok": True, "shift_date": ref.date().isoformat()})


async def settings_handler(request: web.Request) -> web.Response:
    tg_id, body, err = await _read(request)
    if err:
        return err
    changes = parse_settings(body)
    if changes is None:
        return _err("bad_settings", 400)

    async with Session() as session:
        user = await session.get(User, tg_id)
        if user is None:
            return _err("not_registered", 404)
        for k, v in changes.items():
            setattr(user, k, v)
        await session.commit()
        saved = _settings_json(user)
    return web.json_response({"ok": True, "settings": saved})


async def vacation_add(request: web.Request) -> web.Response:
    tg_id, body, err = await _read(request)
    if err:
        return err
    rng = parse_range(body)
    if rng is None:
        return _err("bad_range", 400)

    async with Session() as session:
        if await session.get(User, tg_id) is None:
            return _err("not_registered", 404)
        session.add(Vacation(user_id=tg_id, start=rng[0], finish=rng[1]))
        await session.commit()
    return web.json_response({"ok": True})


async def vacation_delete(request: web.Request) -> web.Response:
    """Тело: {"id": N} — одну запись, или {"clear": true} — все отпуска."""
    tg_id, body, err = await _read(request)
    if err:
        return err
    if not isinstance(body, dict):
        return _err("bad_body", 400)

    async with Session() as session:
        if body.get("clear") is True:
            await session.execute(delete(Vacation).where(Vacation.user_id == tg_id))
        else:
            try:
                vid = int(body["id"])
            except (KeyError, TypeError, ValueError):
                return _err("bad_id", 400)
            await session.execute(
                delete(Vacation).where(Vacation.user_id == tg_id, Vacation.id == vid)
            )
        await session.commit()
    return web.json_response({"ok": True})


async def sick_handler(request: web.Request) -> web.Response:
    """Больничный на период: отмечает все рабочие смены, как /bolnichny в боте."""
    tg_id, body, err = await _read(request)
    if err:
        return err
    rng = parse_range(body)
    if rng is None:
        return _err("bad_range", 400)

    async with Session() as session:
        user = await session.get(User, tg_id)
        if user is None:
            return _err("not_registered", 404)
        n = await att.mark_range(session, tg_id, rng[0], rng[1], stt.SICK, cfg_from_user(user))
    return web.json_response({"ok": True, "count": n})


async def hired_handler(request: web.Request) -> web.Response:
    """Дата устройства — от неё считаются стаж и звание (как /ustroilsya)."""
    tg_id, body, err = await _read(request)
    if err:
        return err
    hired = _parse_day(body.get("date")) if isinstance(body, dict) else None
    if hired is None:
        return _err("bad_date", 400)

    async with Session() as session:
        user = await session.get(User, tg_id)
        if user is None:
            return _err("not_registered", 404)
        if hired > cfg_from_user(user).now().date():
            return _err("future", 400)
        user.hired_at = hired
        await session.commit()
    return web.json_response({"ok": True})


async def beer_vote(request: web.Request) -> web.Response:
    tg_id, body, err = await _read(request)
    if err:
        return err
    try:
        event_id = int(body["event_id"])
        yes = bool(body["yes"])
    except (ValueError, KeyError, TypeError):
        return _err("bad_body", 400)

    async with Session() as session:
        if await session.get(BeerEvent, event_id) is None:
            return _err("no_event", 404)
        await br.vote(session, event_id, tg_id, yes)
    return web.json_response({"ok": True})


# ---------- запуск ----------

def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/api/state", state)
    app.router.add_post("/api/mark", mark_handler)
    app.router.add_post("/api/beer/vote", beer_vote)
    app.router.add_post("/api/settings", settings_handler)
    app.router.add_post("/api/vacation", vacation_add)
    app.router.add_post("/api/vacation/delete", vacation_delete)
    app.router.add_post("/api/sick", sick_handler)
    app.router.add_post("/api/hired", hired_handler)
    app.router.add_post("/api/setup", setup_handler)
    if ASSETS.is_dir():                       # JS и CSS сборки (имена с хешем)
        app.router.add_static("/assets/", ASSETS, show_index=False)
    if STATIC.is_dir():                       # логотип и прочая статика: webapp/static/
        app.router.add_static("/static/", STATIC, show_index=False)
    return app


async def start() -> web.AppRunner:
    """Поднимает HTTP на 127.0.0.1 — наружу его отдаёт Caddy/nginx с HTTPS."""
    runner = web.AppRunner(make_app())
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", settings.web_port)
    await site.start()
    log.info("webapp слушает 127.0.0.1:%s", settings.web_port)
    return runner
