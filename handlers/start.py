from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import ADMIN_IDS
from misc.utils import get_mailings_with_buttons

router = Router()


@router.message(Command('admin'))
async def admin(message: Message, session: AsyncSession):
    if str(message.from_user.id) not in ADMIN_IDS:
        return
    if message.chat.type != 'private':
        return

    builder = await get_mailings_with_buttons(session)

    await message.answer(
        "📦 <b>Меню рассылок:</b>", parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )