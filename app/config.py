from __future__ import annotations

import os
from dataclasses import dataclass


def _env(key: str, default: str | None = None) -> str:
    val = os.getenv(key, default)
    if val is None:
        raise RuntimeError(f"Не задана переменная окружения {key}")
    return val


@dataclass(frozen=True)
class Settings:
    bot_token: str = _env("BOT_TOKEN", "")
    db_dsn: str = _env("DB_DSN", "postgresql+asyncpg://baltika:baltika@localhost:5432/baltika_bot")
    redis_dsn: str = _env("REDIS_DSN", "redis://localhost:6379/3")
    admin_ids: tuple[int, ...] = tuple(
        int(x) for x in _env("ADMIN_IDS", "").replace(" ", "").split(",") if x
    )
    default_tz: str = _env("DEFAULT_TZ", "Europe/Moscow")
    beer_place: str = _env("BEER_PLACE", "магазинчик у проходной")
    beer_lead_min: int = int(_env("BEER_LEAD_MIN", "35"))
    tick_seconds: int = int(_env("TICK_SECONDS", "60"))
    send_concurrency: int = int(_env("SEND_CONCURRENCY", "20"))
    web_port: int = int(_env("WEB_PORT", "8080"))
    web_url: str = _env("WEB_URL", "")        # публичный https-адрес Mini App


settings = Settings()
