"""Фоновый воркер: раз в TICK_SECONDS проходит по активным юзерам и решает,
кому что отправить. Дедупликация — через sent_log (UNIQUE user_id+key),
поэтому рестарт сервиса не приводит к повторным пушам.

Окно срабатывания — GRACE: если бот лежал 10 минут, пуш всё равно уйдёт,
но с опозданием, а не потеряется.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from . import phrases as ph
from . import schedule as sch
from . import shuttle as sh
from . import weather as wx
from . import beer as be
from . import cleanup as cl
from . import stats as stt
from . import wellness as wl
from .appkb import ATTEND_TEXT, app_only_kb, with_app
from .config import settings
from .db import BeerEvent, Session, SentLog, User
from .service import cfg_from_user, dm, hhmm, render, user_route

log = logging.getLogger(__name__)

GRACE = timedelta(minutes=15)

# (ключ дедупликации, текст, клавиатура)
# (ключ дедупликации, текст, клавиатура, когда сообщение перестанет быть нужным)
Job = tuple[str, str, "InlineKeyboardMarkup | None", "datetime | None"]


def beer_kb(event_id: int) -> InlineKeyboardMarkup:
    return app_only_kb("🍺 Голос за пиво — в приложении")




async def already_sent(session: AsyncSession, user_id: int, key: str) -> bool:
    """Атомарная попытка занять ключ. True — уже отправляли раньше."""
    stmt = (
        insert(SentLog)
        .values(user_id=user_id, key=key)
        .on_conflict_do_nothing(index_elements=["user_id", "key"])
        .returning(SentLog.id)
    )
    res = await session.execute(stmt)
    await session.commit()
    return res.scalar_one_or_none() is None


def due(now: datetime, moment: datetime) -> bool:
    return moment <= now < moment + GRACE



async def weather_for(user: User, when: datetime) -> str:
    """Погодная строка к моменту `when`. При сбое сети — пусто."""
    if not user.show_weather:
        return ""
    w = await wx.fetch(tz=user.tz)
    if w is None:
        return ""
    p = w.at_hour(when)
    if p is None:
        return "\n\n" + wx.line_now(w)
    rain = f", осадки {p.precip_prob}%" if p.precip_prob >= 30 else ""
    return f"\n\n{p.emoji} К {when:%H:%M}: {p.temp:+.0f}° (ощущается {p.feels:+.0f}°), {p.text}{rain}\n{wx.advice(p)}"


async def build_jobs(session: AsyncSession, user: User) -> list[Job]:
    """Что нужно отправить этому человеку прямо сейчас."""
    cfg = cfg_from_user(user)
    st = sch.status(cfg)
    now = st.now
    lvl = user.sarcasm
    jobs: list[Job] = []

    # ── идёт смена: «скоро домой» ───────────────────────────────────────
    if st.working and user.notify_home_min:
        moment = st.shift_end - timedelta(minutes=user.notify_home_min)
        if due(now, moment):
            left = sch.human_delta(st.shift_end - now)
            text = await render(
                session, "almost_home", lvl,
                left=left, when=hhmm(st.shift_end),
                kind=ph.KIND_WORD.get(st.shift_kind, "смена"),
                weekend=sch.human_delta(st.weekend_start - now) if st.weekend_start else "—",
            )
            head = "🏠 <b>Скоро домой</b>\n\n"
            tail = await weather_for(user, st.shift_end)
            jobs.append((f"home:{st.shift_start.isoformat()}", head + text + tail, None,
                         st.shift_end + timedelta(minutes=30)))

    # ── начались выходные ───────────────────────────────────────────────
    if user.notify_freedom and st.in_weekend and st.weekend_start:
        if due(now, st.weekend_start):
            left = sch.human_delta(st.weekend_end - now) if st.weekend_end else "несколько дней"
            text = await render(session, "freedom", lvl, left=left,
                                kind="смена", when=hhmm(st.weekend_end) if st.weekend_end else "—",
                                weekend=left)
            head = "🎉 <b>Выходные начались</b>\n\n"
            jobs.append((f"freedom:{st.weekend_start.isoformat()}", head + text, None,
                         st.weekend_start + timedelta(hours=8)))

    # ── напоминания перед следующей сменой ──────────────────────────────
    if st.next_start:
        nxt = st.next_start
        kind = ph.KIND_WORD.get(st.next_kind, "смена")
        base = {
            "kind": kind,
            "when": hhmm(nxt),
            "weekend": sch.human_delta(st.weekend_start - now) if st.weekend_start else "—",
        }
        rules = []
        if user.notify_d2:
            rules.append(("d2", nxt - timedelta(days=2), "🗓 "))
        if user.notify_d1:
            rules.append(("d1", nxt - timedelta(days=1), "⏳ "))
        if user.notify_soon_h:
            rules.append(("soon", nxt - timedelta(hours=user.notify_soon_h), "⏰ "))

        for cat, moment, icon in rules:
            # во время смены человек и так в курсе, что он на работе:
            # долгие напоминания шлём только когда он свободен
            if cat in ("d2", "d1") and st.working:
                continue
            if due(now, moment):
                text = await render(session, cat, lvl, left=sch.human_delta(nxt - now), **base)
                tail = await weather_for(user, nxt) if cat == "soon" else ""
                jobs.append((f"{cat}:{nxt.isoformat()}", icon + text + tail, None, nxt))

    # ── развозка ────────────────────────────────────────────────────────
    route = user_route(user)
    if route and user.notify_bus_min:
        lead = timedelta(minutes=user.notify_bus_min)

        # с завода после смены
        if st.working and st.shift_end:
            buses = sh.from_work_buses(route, st.shift_end, limit=1)
            if buses and due(now, buses[0] - lead):
                text = await render(
                    session, "bus_from", lvl,
                    left=sch.human_delta(buses[0] - now),
                    when=hhmm(buses[0]), station=route.station,
                    kind=ph.KIND_WORD.get(st.shift_kind, "смена"), weekend="—",
                )
                jobs.append((f"busfrom:{buses[0].isoformat()}", "🚌 " + text, None,
                             buses[0] + timedelta(minutes=20)))

        # от метро на смену
        if st.next_start:
            buses = sh.to_work_buses(route, st.next_start, user.bus_buffer_min, limit=1)
            if buses and due(now, buses[0] - lead):
                text = await render(
                    session, "bus_to", lvl,
                    left=sch.human_delta(buses[0] - now),
                    when=hhmm(buses[0]), station=route.station,
                    kind=ph.KIND_WORD.get(st.next_kind, "смена"), weekend="—",
                )
                jobs.append((f"busto:{buses[0].isoformat()}", "🚌 " + text, None,
                             buses[0] + timedelta(minutes=20)))

    # ── опрос «по пиву» перед концом дневной смены ──────────────────────
    if (
        st.working
        and st.shift_kind == sch.DAY
        and user.beer_enabled
        and st.shift_end
    ):
        moment = st.shift_end - timedelta(minutes=settings.beer_lead_min)
        if due(now, moment):
            event = await be.get_or_create(session, st.shift_end)
            text = await render(
                session, "beer_ask", lvl,
                left=sch.human_delta(st.shift_end - now),
                when=hhmm(st.shift_end), place=event.place,
                kind=ph.KIND_WORD.get(st.shift_kind, "смена"), weekend="—",
            )
            jobs.append((f"beer:{event.id}", "🍺 " + text, beer_kb(event.id),
                         st.shift_end + timedelta(hours=2)))

    # ── просьба отметиться через 30 минут после начала смены ────────────
    if st.working and user.notify_checkin and user.hired_at and st.shift_start:
        moment = st.shift_start + timedelta(minutes=30)
        if due(now, moment):
            day = st.shift_start.date()
            kb_app = app_only_kb(ATTEND_TEXT)
            jobs.append((
                f"checkin:{day.isoformat()}",
                f"<b>📋 Отметка за {day:%d.%m}</b>\n{sch.SHIFT_LABEL[st.shift_kind]} смена\n\n"
                "Отметка только в приложении. Без неё смена засчитается как отработанная.",
                kb_app,
                st.shift_end + timedelta(hours=1),
            ))

    # ── мужской выходной: зал, бассейн, сауна открыты ───────────────────
    # Включается тем же переключателем, что и «Поздравлять с выходными».
    today = now.date()
    if user.notify_freedom and wl.access(cfg, today)["open"]:
        morning = datetime.combine(today, time(9, 0), tzinfo=cfg.zone)
        evening = datetime.combine(today, time(21, 0), tzinfo=cfg.zone)
        if morning <= now < evening:
            jobs.append((f"wellness:{today.isoformat()}", wl.notify_text(today), None, evening))

    return jobs


async def send_one(bot: Bot, user_id: int, text: str,
                   markup: InlineKeyboardMarkup | None = None):
    """Возвращает отправленное сообщение либо None."""
    try:
        return await bot.send_message(user_id, text, reply_markup=markup)
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after + 1)
        try:
            return await bot.send_message(user_id, text, reply_markup=markup)
        except Exception as exc:
            log.warning("retry failed for %s: %s", user_id, exc)
            return None
    except TelegramForbiddenError:
        async with Session() as s:
            u = await s.get(User, user_id)
            if u:
                u.is_active = False
                await s.commit()
        log.info("user %s заблокировал бота — деактивирован", user_id)
        return None
    except Exception as exc:
        log.warning("send failed for %s: %s", user_id, exc)
        return None



async def beer_summaries(bot: Bot, session: AsyncSession) -> None:
    """После конца смены рассылает участникам итоговый состав и место."""
    now = datetime.now().astimezone()
    events = (
        await session.execute(
            select(BeerEvent).where(
                BeerEvent.summary_sent.is_(False), BeerEvent.shift_end <= now
            )
        )
    ).scalars().all()

    for event in events:
        voters = [v.user_id for v in event.votes if v.yes]
        if voters:
            text = await be.event_summary(session, event)
            die = event.shift_end + timedelta(hours=8)
            for uid in voters:
                sent = await send_one(bot, uid, text, with_app())
                if sent:
                    await cl.schedule(session, sent.chat.id, sent.message_id, die)
        event.summary_sent = True
    if events:
        await session.commit()


async def tick(bot: Bot) -> None:
    async with Session() as session:
        users = (
            await session.execute(select(User).where(User.is_active.is_(True)))
        ).scalars().all()

        sem = asyncio.Semaphore(settings.send_concurrency)
        tasks = []

        async def handle(u: User) -> None:
            try:
                jobs = await build_jobs(session, u)
            except Exception as exc:
                log.exception("build_jobs failed for %s: %s", u.tg_id, exc)
                return
            for key, text, markup, expire_at in jobs:
                if await already_sent(session, u.tg_id, key):
                    continue
                async with sem:
                    sent = await send_one(bot, u.tg_id, text, with_app(markup))
                if sent and u.autoclean:
                    die = expire_at or (
                        datetime.now().astimezone() + timedelta(minutes=u.clean_after_min or 180)
                    )
                    await cl.schedule(session, sent.chat.id, sent.message_id, die)

        for u in users:
            tasks.append(handle(u))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        try:
            await beer_summaries(bot, session)
        except Exception as exc:
            log.exception("beer_summaries failed: %s", exc)

        try:
            await cl.sweep(bot, session)
        except Exception as exc:
            log.exception("cleanup sweep failed: %s", exc)


async def cleanup(session: AsyncSession) -> None:
    """Чистим лог отправок старше 60 дней."""
    cutoff = datetime.now().astimezone() - timedelta(days=60)
    await session.execute(delete(SentLog).where(SentLog.sent_at < cutoff))
    await session.commit()


async def run(bot: Bot) -> None:
    log.info("notifier started, tick=%ss", settings.tick_seconds)
    counter = 0
    while True:
        try:
            await tick(bot)
            counter += 1
            if counter % 1440 == 0:
                async with Session() as s:
                    await cleanup(s)
        except Exception as exc:
            log.exception("tick failed: %s", exc)
        await asyncio.sleep(settings.tick_seconds)
