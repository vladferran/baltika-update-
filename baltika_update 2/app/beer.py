"""Событие «по пиву после смены».

Одно событие на момент окончания смены — все, у кого дневная заканчивается
в это время, попадают в общий список. Смысл именно в общем списке: иначе
кнопка была бы просто кнопкой.

Голос перезаписывается — передумать можно до самого конца смены.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import BeerEvent, BeerVote, User


async def get_or_create(session: AsyncSession, shift_end: datetime,
                        place: str | None = None) -> BeerEvent:
    stmt = (
        insert(BeerEvent)
        .values(shift_end=shift_end, place=place or settings.beer_place)
        .on_conflict_do_nothing(index_elements=["shift_end"])
    )
    await session.execute(stmt)
    await session.commit()
    event = (
        await session.execute(select(BeerEvent).where(BeerEvent.shift_end == shift_end))
    ).scalar_one()
    return event


async def vote(session: AsyncSession, event_id: int, user_id: int, yes: bool) -> None:
    """Голос перезаписывается при повторном нажатии."""
    stmt = (
        insert(BeerVote)
        .values(event_id=event_id, user_id=user_id, yes=yes)
        .on_conflict_do_update(
            index_elements=["event_id", "user_id"],
            set_={"yes": yes},
        )
    )
    await session.execute(stmt)
    await session.commit()


def display_name(user: User | None, fallback_id: int) -> str:
    if user is None:
        return f"id{fallback_id}"
    if user.first_name:
        return user.first_name
    if user.username:
        return f"@{user.username}"
    return f"id{user.tg_id}"


async def participants(session: AsyncSession, event_id: int) -> list[str]:
    rows = (
        await session.execute(
            select(BeerVote.user_id).where(BeerVote.event_id == event_id, BeerVote.yes.is_(True))
        )
    ).scalars().all()
    if not rows:
        return []
    users = (
        await session.execute(select(User).where(User.tg_id.in_(rows)))
    ).scalars().all()
    by_id = {u.tg_id: u for u in users}
    return [display_name(by_id.get(uid), uid) for uid in rows]


async def event_summary(session: AsyncSession, event: BeerEvent) -> str:
    names = await participants(session, event.id)
    if not names:
        return (
            f"<b>🍺 После смены в {event.shift_end:%H:%M}</b>\n\n"
            "Пока никто не согласился. Тихий вечер тоже вариант."
        )
    listed = ", ".join(names)
    return (
        f"<b>🍺 После смены в {event.shift_end:%H:%M}</b>\n\n"
        f"Идут ({len(names)}): {listed}\n"
        f"📍 Место: {event.place}"
    )


async def nearest_event(session: AsyncSession, now: datetime) -> BeerEvent | None:
    """Ближайшее событие: текущее или сегодняшнее прошедшее."""
    rows = (
        await session.execute(
            select(BeerEvent).order_by(BeerEvent.shift_end.desc()).limit(10)
        )
    ).scalars().all()
    for e in rows:
        if e.shift_end.date() == now.date():
            return e
    return rows[0] if rows else None
