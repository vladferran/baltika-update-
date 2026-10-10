"""Автоочистка чата.

Каждое сообщение бота регистрируется в очереди с моментом смерти. Смысл
не в «удалить через час», а в «удалить, когда перестало быть нужным»:
напоминание о смене живёт до начала смены, про автобус — до его отправления,
опрос про пиво — до конца смены.

Telegram позволяет боту удалять в личке и свои сообщения, и входящие,
но только моложе 48 часов. Просроченные записи просто выбрасываем.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from aiogram import Bot
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .db import PendingDelete

log = logging.getLogger(__name__)

TG_LIMIT = timedelta(hours=47, minutes=30)   # запас до лимита в 48 часов


async def schedule(session: AsyncSession, chat_id: int, message_id: int,
                   delete_at: datetime) -> None:
    """Ставит сообщение в очередь. Повторный вызов сдвигает срок."""
    stmt = (
        insert(PendingDelete)
        .values(chat_id=chat_id, message_id=message_id, delete_at=delete_at)
        .on_conflict_do_update(
            index_elements=["chat_id", "message_id"],
            set_={"delete_at": delete_at},
        )
    )
    await session.execute(stmt)
    await session.commit()


async def sweep(bot: Bot, session: AsyncSession, limit: int = 200) -> int:
    """Удаляет всё, чей срок пришёл. Возвращает число удалённых."""
    now = datetime.now().astimezone()
    rows = (
        await session.execute(
            select(PendingDelete).where(PendingDelete.delete_at <= now).limit(limit)
        )
    ).scalars().all()

    done = 0
    for row in rows:
        if now - row.delete_at < TG_LIMIT:
            try:
                await bot.delete_message(row.chat_id, row.message_id)
                done += 1
            except Exception:
                # уже удалено вручную, слишком старое или чат недоступен
                pass
        await session.delete(row)
    if rows:
        await session.commit()
    return done


async def purge_chat(bot: Bot, session: AsyncSession, chat_id: int) -> int:
    """Немедленно вычищает всё, что стоит в очереди для этого чата."""
    rows = (
        await session.execute(select(PendingDelete).where(PendingDelete.chat_id == chat_id))
    ).scalars().all()
    done = 0
    for row in rows:
        try:
            await bot.delete_message(row.chat_id, row.message_id)
            done += 1
        except Exception:
            pass
        await session.delete(row)
    if rows:
        await session.commit()
    return done


async def forget(session: AsyncSession, chat_id: int, message_id: int) -> None:
    """Снимает сообщение с удаления — например, итоговый список участников."""
    await session.execute(
        delete(PendingDelete).where(
            PendingDelete.chat_id == chat_id, PendingDelete.message_id == message_id
        )
    )
    await session.commit()
