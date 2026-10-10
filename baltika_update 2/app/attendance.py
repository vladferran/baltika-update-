"""Отметки посещаемости."""

from __future__ import annotations

from datetime import date

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .db import Attendance


async def mark(session: AsyncSession, user_id: int, shift_date: date,
               status: str, note: str | None = None) -> None:
    """Ставит или перезаписывает отметку по смене."""
    stmt = (
        insert(Attendance)
        .values(user_id=user_id, shift_date=shift_date, status=status, note=note)
        .on_conflict_do_update(
            index_elements=["user_id", "shift_date"],
            set_={"status": status, "note": note},
        )
    )
    await session.execute(stmt)
    await session.commit()


async def mark_range(session: AsyncSession, user_id: int, start: date, finish: date,
                     status: str, cfg) -> int:
    """Отмечает все рабочие смены в диапазоне. Возвращает их число."""
    from . import schedule as sch
    from datetime import timedelta

    n = 0
    d = start
    while d <= finish:
        if cfg.kind(d) in sch.WORK:
            await mark(session, user_id, d, status)
            n += 1
        d += timedelta(days=1)
    return n
