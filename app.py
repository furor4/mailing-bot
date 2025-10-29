import asyncio
import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from config import dp, bot, CHAT_ID
from db.models import DatabaseMiddleware, create_tables, async_session
from handlers import start, creating_mailings, editing_mailings
from misc.utils import start_mailing_scheduler

logging.getLogger('aiogram').setLevel(logging.INFO)

PINK = "\033[38;5;219m"
RESET = "\033[0m"


async def main():
    await create_tables()

    dp.update.middleware(DatabaseMiddleware())

    dp.include_routers(start.router, creating_mailings.router, editing_mailings.router)
    await bot.delete_webhook(drop_pending_updates=True)
    print(f'{PINK}Запущено!{RESET}')
    await dp.start_polling(bot)


async def on_startup(bot: Bot):
    async with async_session() as session:
        await start_mailing_scheduler(bot, session, CHAT_ID)


if __name__ == '__main__':
    try:
        dp.startup.register(on_startup)
        asyncio.run(main())
    except (KeyboardInterrupt, RuntimeError) as main_error:
        print('Бот выключен.')
