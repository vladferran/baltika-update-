from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, Time, UniqueConstraint, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .config import settings


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))

    pattern: Mapped[str] = mapped_column(String(31), default="ДДВННВВВ")
    anchor: Mapped[date] = mapped_column(Date)
    tz: Mapped[str] = mapped_column(String(48), default="Europe/Moscow")

    day_start: Mapped[time] = mapped_column(Time, default=time(8, 0))
    day_hours: Mapped[int] = mapped_column(Integer, default=12)
    night_start: Mapped[time] = mapped_column(Time, default=time(20, 0))
    night_hours: Mapped[int] = mapped_column(Integer, default=12)

    sarcasm: Mapped[int] = mapped_column(Integer, default=2)
    notify_d2: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_d1: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_soon_h: Mapped[int] = mapped_column(Integer, default=2)      # 0 = выключено
    notify_home_min: Mapped[int] = mapped_column(Integer, default=80)   # «скоро домой», 0 = выкл
    notify_freedom: Mapped[bool] = mapped_column(Boolean, default=True)
    weekend_min_days: Mapped[int] = mapped_column(Integer, default=2)

    shuttle_route: Mapped[str | None] = mapped_column(String(24))       # None = не выбрана
    notify_bus_min: Mapped[int] = mapped_column(Integer, default=30)    # 0 = выкл
    bus_buffer_min: Mapped[int] = mapped_column(Integer, default=20)
    show_weather: Mapped[bool] = mapped_column(Boolean, default=True)
    beer_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    hired_at: Mapped[date | None] = mapped_column(Date)
    notify_checkin: Mapped[bool] = mapped_column(Boolean, default=True)
    autoclean: Mapped[bool] = mapped_column(Boolean, default=True)
    clean_after_min: Mapped[int] = mapped_column(Integer, default=180)   # 0 = не чистить

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vacations: Mapped[list["Vacation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )


class Vacation(Base):
    __tablename__ = "vacations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.tg_id", ondelete="CASCADE"), index=True)
    start: Mapped[date] = mapped_column(Date)
    finish: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(128))

    user: Mapped[User] = relationship(back_populates="vacations")


class BeerEvent(Base):
    """Одно событие на смену: ключ — момент её окончания."""

    __tablename__ = "beer_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shift_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), unique=True)
    place: Mapped[str] = mapped_column(String(200))
    summary_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    votes: Mapped[list["BeerVote"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", lazy="selectin"
    )


class BeerVote(Base):
    __tablename__ = "beer_votes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("beer_events.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    yes: Mapped[bool] = mapped_column(Boolean)
    voted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    event: Mapped[BeerEvent] = relationship(back_populates="votes")

    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_beer_vote"),)


class Attendance(Base):
    """Отметка по смене. Пишем только исключения и явные подтверждения."""

    __tablename__ = "attendance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    shift_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(String(200))
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "shift_date", name="uq_attendance"),)


class PendingDelete(Base):
    """Очередь на удаление: сообщение живёт до delete_at, потом исчезает."""

    __tablename__ = "pending_deletes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int] = mapped_column(Integer)
    delete_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    __table_args__ = (UniqueConstraint("chat_id", "message_id", name="uq_pending_delete"),)


class Phrase(Base):
    __tablename__ = "phrases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(24), index=True)
    level: Mapped[int] = mapped_column(Integer, default=2)
    text: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("category", "level", "text", name="uq_phrase"),)


class Meta(Base):
    """Служебные метки: версия банка фраз и т.п."""

    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256))


class SentLog(Base):
    """Дедупликация: один и тот же пуш не уйдёт дважды после рестарта."""

    __tablename__ = "sent_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    key: Mapped[str] = mapped_column(String(128))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_sent"),)


engine = create_async_engine(settings.db_dsn, pool_size=10, max_overflow=5, echo=False)
Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    from .phrases import PHRASE_BANK_VERSION, seed_rows

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    version = str(PHRASE_BANK_VERSION)
    async with Session() as s:
        meta = await s.get(Meta, "phrase_bank")
        bank_changed = meta is None or meta.value != version
        if bank_changed:
            # новая версия банка: старые фразы выключаем, новые включаем
            await s.execute(update(Phrase).values(enabled=False))
        existing = {
            (p.category, p.level, p.text): p
            for p in (await s.execute(select(Phrase))).scalars().all()
        }
        for c, l, t in seed_rows():
            row = existing.get((c, l, t))
            if row is None:
                s.add(Phrase(category=c, level=l, text=t, enabled=True))
            elif bank_changed:
                row.enabled = True
        if meta is None:
            s.add(Meta(key="phrase_bank", value=version))
        else:
            meta.value = version
        await s.commit()
