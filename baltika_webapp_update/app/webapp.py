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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web
from sqlalchemy import select

from . import attendance as att
from . import beer as br
from . import schedule as sch
from . import shuttle as sh
from . import stats as stt
from . import weather as wx
from .config import settings
from .db import BeerEvent, BeerVote, Session, User
from .service import cfg_from_user, user_route

log = logging.getLogger("baltika.web")

INDEX = Path(__file__).resolve().parent.parent / "webapp" / "index.html"
STATIC = Path(__file__).resolve().parent.parent / "webapp" / "static"
MAX_AGE = 24 * 3600                       # initData старше суток не принимаем
MARK_STATUSES = {"worked", "sick", "vacation", "dayoff", "absent"}


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
        out.append({
            "date": d.isoformat(),
            "kind": k,
            "weekend": sh.is_weekend(d),
            "start": _iso(b[0]) if b else None,
            "end": _iso(b[1]) if b else None,
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


async def _weather_json(user: User) -> dict | None:
    if not user.show_weather:
        return None
    w = await wx.fetch(tz=user.tz)
    if w is None:
        return None
    return {"line": wx.line_now(w), "advice": wx.advice(w.now)}


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
            "sarcasm": user.sarcasm,
            "today": today.isoformat(),
            "status": _status_json(st),
            "calendar": _calendar_json(cfg, today, days),
            "shuttle": _shuttle_json(user, st),
            "beer": await _beer_json(session, user, st.now),
            "stats": await _stats_json(session, user, cfg),
            "weather": await _weather_json(user),
            "settings": {
                "notify_checkin": user.notify_checkin,
                "beer_enabled": user.beer_enabled,
                "show_weather": user.show_weather,
                "autoclean": user.autoclean,
            },
        }
    return web.json_response(payload)


async def mark_handler(request: web.Request) -> web.Response:
    tg_id = _tg_id(request)
    if tg_id is None:
        return web.json_response({"error": "auth"}, status=401)
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        return web.json_response({"error": "bad_json"}, status=400)
    status = body.get("status")
    if status not in MARK_STATUSES:
        return web.json_response({"error": "bad_status"}, status=400)

    async with Session() as session:
        user = await session.get(User, tg_id)
        if user is None:
            return web.json_response({"error": "not_registered"}, status=404)
        cfg = cfg_from_user(user)
        st = sch.status(cfg)
        ref = st.shift_start or st.next_start
        if ref is None:
            return web.json_response({"error": "no_shift"}, status=409)
        await att.mark(session, tg_id, ref.date(), status)
    return web.json_response({"ok": True, "shift_date": ref.date().isoformat()})


SETTING_FIELDS = ("notify_checkin", "beer_enabled", "show_weather", "autoclean")


def parse_settings(body) -> dict | None:
    """Берём только известные переключатели и только bool. Битый вход — None."""
    if not isinstance(body, dict):
        return None
    out: dict[str, bool] = {}
    for k in SETTING_FIELDS:
        if k in body:
            if not isinstance(body[k], bool):
                return None
            out[k] = body[k]
    return out or None


async def settings_handler(request: web.Request) -> web.Response:
    tg_id = _tg_id(request)
    if tg_id is None:
        return web.json_response({"error": "auth"}, status=401)
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        return web.json_response({"error": "bad_json"}, status=400)
    changes = parse_settings(body)
    if changes is None:
        return web.json_response({"error": "bad_settings"}, status=400)

    async with Session() as session:
        user = await session.get(User, tg_id)
        if user is None:
            return web.json_response({"error": "not_registered"}, status=404)
        for k, v in changes.items():
            setattr(user, k, v)
        saved = {k: getattr(user, k) for k in SETTING_FIELDS}   # читаем до commit
        await session.commit()
    return web.json_response({"ok": True, "settings": saved})


async def beer_vote(request: web.Request) -> web.Response:
    tg_id = _tg_id(request)
    if tg_id is None:
        return web.json_response({"error": "auth"}, status=401)
    try:
        body = await request.json()
        event_id = int(body["event_id"])
        yes = bool(body["yes"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return web.json_response({"error": "bad_body"}, status=400)

    async with Session() as session:
        if await session.get(BeerEvent, event_id) is None:
            return web.json_response({"error": "no_event"}, status=404)
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
