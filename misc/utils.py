import asyncio
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import MSK
from db.models import Mailings


async def get_mailings_with_buttons(session: AsyncSession):
    result = (await session.execute(
        select(Mailings)
        .options(selectinload(Mailings.buttons))
    )).scalars().all()

    builder = InlineKeyboardBuilder()

    if result:
        for mailing in result:
            text = (mailing.text[:20] + "...") if mailing.text else "Рассылка без текста"
            builder.add(InlineKeyboardButton(
                text=text,
                callback_data=f"mailing_{mailing.id}"
            ))
        builder.adjust(1)

    builder.row(InlineKeyboardButton(
        text="➕ Создать рассылку",
        callback_data="create_mailing"
    ))

    return builder


async def mailing_scheduler(bot: Bot, session: AsyncSession, chat_id: int):
    while True:
        try:
            mailings = (await session.execute(select(Mailings)
                                            .where(Mailings.status == True)
                                            .options(selectinload(Mailings.buttons)))).scalars().all()

            for mailing in mailings:
                if not await check_global_period(mailing.globalper, mailing.created_at):
                    mailing.status = False
                    await session.commit()
                    continue

                if not await check_periodicity(mailing.per, mailing.last_sent):
                    continue

                if mailing.last_message_id:
                    try:
                        await bot.delete_message(chat_id=chat_id, message_id=mailing.last_message_id)
                    except Exception as e:
                        print(f'Не удалось удалить предыдущее сообщение: {e}')

                message_id = await send_mailing(bot, chat_id, mailing)

                mailing.last_sent = datetime.now(MSK)
                mailing.last_message_id = message_id
                await session.commit()

        except Exception as e:
            print(f'Ошибка в рассылке: {e}')

        await asyncio.sleep(60)

async def parse_time(time_str: str) -> dict:
    time_dict = {'d': 0, 'h': 0, 'm': 0, 'w': 0, 'M': 0}

    parts = time_str.split()
    for part in parts:
        if part[-1] in time_dict:
            try:
                time_dict[part[-1]] = int(part[:-1])
            except ValueError:
                continue

    return time_dict

async def check_global_period(globalper: str, created_at: datetime) -> bool | None:
    if not globalper:
        return True

    time_dict = await parse_time(globalper)

    total_days = (time_dict['d'] + time_dict['w'] * 7 + time_dict['M'] * 30)

    delta = timedelta(days=total_days,
                      hours=time_dict['h'],
                      minutes=time_dict['m'])

    return datetime.now(MSK) < created_at + delta

async def check_periodicity(per: str, last_sent: datetime) -> bool:
    if not per:
        return False

    if not last_sent:
        return True

    time_dict = await parse_time(per)

    delta = timedelta(days=time_dict['d'],
                      hours=time_dict['h'],
                      minutes=time_dict['m'])

    return datetime.now(MSK) >= last_sent + delta

async def send_mailing(bot: Bot, chat_id: int, mailing: Mailings) -> int | None:
    reply_markup = None
    if mailing.buttons:
        kb = InlineKeyboardBuilder()
        for btn in mailing.buttons:
            kb.add(InlineKeyboardButton(text=btn.text, url=btn.url))
        kb.adjust(1)
        reply_markup = kb.as_markup()

    try:
        if mailing.media:
            if mailing.media.startswith('AgAC'):
                msg = await bot.send_photo(
                    chat_id=chat_id,
                    photo=mailing.media,
                    caption=mailing.text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
            elif mailing.media.startswith('BAAC'):
                msg = await bot.send_video(
                    chat_id=chat_id,
                    video=mailing.media,
                    caption=mailing.text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
            elif mailing.media.startswith('CgAC'):
                msg = await bot.send_animation(
                    chat_id=chat_id,
                    animation=mailing.media,
                    caption=mailing.text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
            else:
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=mailing.text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
        else:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=mailing.text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )

        return msg.message_id

    except Exception as e:
        print(f'Ошибка при отправке рассылки {mailing.id}: {e}')
        return None

async def start_mailing_scheduler(bot: Bot, session: AsyncSession, chat_id: int):
    asyncio.create_task(mailing_scheduler(bot, session, chat_id))