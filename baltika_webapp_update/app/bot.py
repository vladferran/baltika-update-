from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from . import notifier
from . import webapp
from .config import settings
from .db import init_db
from .admin import router as admin_router
from .handlers import router
from .menu import router as menu_router, main_kb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("baltika")

COMMANDS = [
    BotCommand(command="skolko", description="Сколько до выходных"),
    BotCommand(command="grafik", description="График на 14 дней"),
    BotCommand(command="razvozka", description="Расписание развозки"),
    BotCommand(command="pogoda", description="Погода на заводе"),
    BotCommand(command="pivo", description="Кто идёт после смены"),
    BotCommand(command="stazh", description="Стаж и статистика"),
    BotCommand(command="otmetka", description="Отметиться по смене"),
    BotCommand(command="clean", description="Вычистить чат"),
    BotCommand(command="nastroiki", description="Настройки уведомлений"),
    BotCommand(command="otpusk", description="Отпуск"),
    BotCommand(command="perenastroit", description="Задать график заново"),
    BotCommand(command="help", description="Помощь"),
]


async def main() -> None:
    await init_db()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=RedisStorage.from_url(settings.redis_dsn))
    dp.include_router(admin_router)
    dp.include_router(menu_router)   # кнопочное меню
    dp.include_router(router)

    await bot.set_my_commands(COMMANDS)
    if settings.web_url:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Приложение", web_app=WebAppInfo(url=settings.web_url))
        )
    worker = asyncio.create_task(notifier.run(bot))
    runner = await webapp.start()

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        worker.cancel()
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("остановлено")
