from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Mailings, Buttons
from handlers.creating_mailings import PERIODICITY_REGEX, GLOBAL_PERIODICITY_REGEX
from handlers.start import get_mailings_with_buttons

router = Router()


class MailingEditing(StatesGroup):
    waiting_for_text = State()
    waiting_for_media = State()
    waiting_for_per = State()
    waiting_for_globalper = State()
    waiting_for_buttons = State()
    waiting_for_delete_confirmation = State()


def kb_edits(mailing):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ Изменить текст", callback_data=f"edit_text_{mailing.id}"),
        InlineKeyboardButton(text="💾 Изменить медиа", callback_data=f"edit_media_{mailing.id}")
    )
    builder.row(
        InlineKeyboardButton(text="🕒 Изменить периодичность", callback_data=f"edit_per_{mailing.id}"),
        InlineKeyboardButton(text="🗓️ Изменить глоб. периодичность", callback_data=f"edit_globalper_{mailing.id}")
    )
    builder.row(
        InlineKeyboardButton(text="🎛️ Изменить кнопки", callback_data=f"edit_buttons_{mailing.id}")
    )
    builder.row(
        InlineKeyboardButton(text='🟢 Рассылка включена!' if mailing.status else '🔴 Рассылка выключена.',
                             callback_data=f"toggle_status_{mailing.id}")
    )
    builder.row(
        InlineKeyboardButton(text="❌ УДАЛИТЬ РАССЫЛКУ", callback_data=f"delete_mailing_{mailing.id}")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_mailings")
    )

    return builder


async def kb_back(mailing_id: int):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_{mailing_id}"))

    return builder


@router.callback_query(F.data.startswith('mailing_'))
async def mailing_editing_handler(cq: CallbackQuery, session: AsyncSession, state: FSMContext):
    mailing_id = int(cq.data.split("_")[1])

    mailing = await session.get(Mailings, mailing_id, options=[selectinload(Mailings.buttons)])

    if not mailing:
        return

    await cq.message.delete()

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
                await cq.message.answer_photo(
                    str(mailing.media),
                    caption=str(mailing.text),
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
            elif mailing.media.startswith('BAAC'):
                await cq.message.answer_video(
                    str(mailing.media),
                    caption=str(mailing.text),
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
            elif mailing.media.startswith('CgAC'):
                await cq.message.answer_animation(
                    str(mailing.media),
                    caption=str(mailing.text),
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
            else:
                await cq.message.answer(
                    str(mailing.text),
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
        else:
            await cq.message.answer(
                str(mailing.text),
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Ошибка при отправке рассылки: {e}")
        await cq.message.answer(
            "❌ Ошибка при отображении рассылки",
            parse_mode=ParseMode.HTML
        )

    builder = kb_edits(mailing)

    await cq.message.answer(
        "📝 <b>Что хотите изменить?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

    await state.update_data(
        mailing_id=mailing.id,
    )
    await cq.answer()


@router.callback_query(F.data.startswith("edit_text_"))
async def edit_text_handler(cq: CallbackQuery, state: FSMContext):
    mailing_id = int(cq.data.split("_")[2])
    await state.set_state(MailingEditing.waiting_for_text)
    await state.update_data(mailing_id=mailing_id)

    builder = await kb_back(mailing_id)

    await cq.message.edit_text(
        text="📝 <b>Введите новый текст рассылки:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

    await cq.answer()


@router.message(MailingEditing.waiting_for_text)
async def process_new_text(message: Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    mailing_id = data.get('mailing_id')

    mailing = await session.get(Mailings, mailing_id)
    mailing.text = message.html_text
    await session.commit()

    await message.answer(
        text="✅ <b>Текст рассылки успешно обновлен!</b>",
        parse_mode=ParseMode.HTML
    )

    await state.clear()


@router.callback_query(F.data.startswith("edit_media_"))
async def edit_media_handler(cq: CallbackQuery, state: FSMContext):
    mailing_id = int(cq.data.split("_")[2])
    await state.set_state(MailingEditing.waiting_for_media)
    await state.update_data(mailing_id=mailing_id)

    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="❌ Убрать медиа", callback_data=f"remove_media_{mailing_id}"))
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_{mailing_id}"))
    builder.adjust(1)

    await cq.message.edit_text(
        text="💾 <b>Отправьте новое фото, видео или GIF:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

    await cq.answer()


@router.callback_query(F.data.startswith("remove_media_"))
async def remove_media_handler(cq: CallbackQuery, session: AsyncSession, state: FSMContext):
    mailing_id = int(cq.data.split("_")[2])

    mailing = await session.get(Mailings, mailing_id)
    mailing.media = None
    await session.commit()

    await cq.message.edit_text(
        "✅ <b>Медиа удалено из рассылки!</b>",
        parse_mode=ParseMode.HTML
    )

    await state.clear()
    await cq.answer()


@router.message(MailingEditing.waiting_for_media, F.photo | F.video | F.animation)
async def process_new_media(message: Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    mailing_id = data.get('mailing_id')

    if message.photo:
        media_id = message.photo[-1].file_id
    elif message.video:
        media_id = message.video.file_id
    elif message.animation:
        media_id = message.animation.file_id
    else:
        return await message.answer("❌ Неверный формат.\n\n💾 <b>Отправьте новое фото, видео или GIF:</b>",
                                    parse_mode=ParseMode.HTML)

    mailing = await session.get(Mailings, mailing_id)
    mailing.media = media_id
    await session.commit()

    await message.answer(
        text="✅ <b>Медиа рассылки успешно обновлено!</b>",
        parse_mode=ParseMode.HTML
    )

    await state.clear()


@router.callback_query(F.data.startswith("edit_per_"))
async def edit_per_handler(cq: CallbackQuery, state: FSMContext):
    mailing_id = int(cq.data.split("_")[2])
    await state.set_state(MailingEditing.waiting_for_per)
    await state.update_data(mailing_id=mailing_id)

    builder = await kb_back(mailing_id)

    await cq.message.edit_text(
        text="🕒 <b>Введите новую периодичность отправки:</b>"
             "\n<blockquote>Примеры: <code>30m, 1h, 2d</code></blockquote>",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

    await cq.answer()


@router.message(MailingEditing.waiting_for_per)
async def process_new_per(message: Message, session: AsyncSession, state: FSMContext):
    if not message.text or not PERIODICITY_REGEX.match(message.text.strip()):
        return await message.answer("❌ <i>Неверный формат.</i>"
                                    "\n\n🕒 <b>Введите новую периодичность отправки:</b>\n"
                                    "<blockquote>Примеры: <code>30m, 1h, 2d</code></blockquote>",
                                    parse_mode=ParseMode.HTML)

    data = await state.get_data()
    mailing_id = data.get('mailing_id')

    mailing = await session.get(Mailings, mailing_id)
    mailing.per = message.text
    await session.commit()

    await message.answer(
        text="✅ <b>Периодичность рассылки успешно обновлена!</b>",
        parse_mode=ParseMode.HTML
    )

    await state.clear()


@router.callback_query(F.data.startswith("edit_globalper_"))
async def edit_globalper_handler(cq: CallbackQuery, state: FSMContext):
    mailing_id = int(cq.data.split("_")[2])
    await state.set_state(MailingEditing.waiting_for_globalper)
    await state.update_data(mailing_id=mailing_id)

    builder = await kb_back(mailing_id)

    await cq.message.edit_text(
        text="🗓️ <b>Введите новую глобальную периодичность:</b>"
             "\n<blockquote>Примеры: <code>1M, 2w, 3d</code></blockquote>",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

    await cq.answer()


@router.message(MailingEditing.waiting_for_globalper)
async def process_new_globalper(message: Message, session: AsyncSession, state: FSMContext):
    if not message.text or not GLOBAL_PERIODICITY_REGEX.match(message.text.strip()):
        return await message.answer("❌ <i>Неверный формат.</i>"
                                    "\n\n🗓️ <b>Введите новую глобальную периодичность:</b>\n"
                                    "<blockquote>Примеры: <code>1M, 2w, 3d</code></blockquote>",
                                    parse_mode=ParseMode.HTML)

    data = await state.get_data()
    mailing_id = data.get('mailing_id')

    mailing = await session.get(Mailings, mailing_id)
    mailing.globalper = message.text
    await session.commit()

    await message.answer(
        text="✅ <b>Глобальная периодичность рассылки успешно обновлена!</b>",
        parse_mode=ParseMode.HTML
    )

    await state.clear()


@router.callback_query(F.data.startswith("edit_buttons_"))
async def edit_buttons_handler(cq: CallbackQuery, state: FSMContext):
    mailing_id = int(cq.data.split("_")[2])
    await state.set_state(MailingEditing.waiting_for_buttons)
    await state.update_data(mailing_id=mailing_id)

    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="❌ Убрать кнопки", callback_data=f"remove_buttons_{mailing_id}"))
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_{mailing_id}"))
    builder.adjust(1)

    await cq.message.edit_text(
        text="\n\n🎛️ <b>Добавьте новые кнопки в формате:</b>\n"
             "<blockquote><code>Текст - https://ссылка1.com</code>\n"
             "<code>Текст2 - https://ссылка2.com</code></blockquote>\n\n"
             "💡 <i>Каждая кнопка с новой строки!\n"
             "При добавлении новых кнопок старые сотрутся!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

    await cq.answer()


@router.callback_query(F.data.startswith("remove_buttons_"))
async def remove_buttons_handler(cq: CallbackQuery, session: AsyncSession, state: FSMContext):
    mailing_id = int(cq.data.split("_")[2])

    await session.execute(delete(Buttons).where(Buttons.mailing_id == mailing_id))
    await session.commit()

    await cq.message.edit_text(
        "✅ <b>Кнопки удалены из рассылки!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_{mailing_id}")]
        ])
    )

    await state.clear()
    await cq.answer()


@router.message(MailingEditing.waiting_for_buttons)
async def process_new_buttons(message: Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    mailing_id = data.get('mailing_id')

    await session.execute(delete(Buttons).where(Buttons.mailing_id == mailing_id))

    buttons_data = []
    lines = message.text.split('\n')

    for line in lines:
        if '-' in line:
            text_part, url_part = line.split('-', 1)
            text = text_part.strip()
            url = url_part.strip()

            try:
                buttons_data.append({'text': text, 'url': url})
            except TelegramBadRequest:
                return await message.answer("❌ <i>Неверный формат кнопок.</i>"
                                            "\n\n🎛️ <b>Добавьте новые кнопки в формате:</b>\n"
                                            "<blockquote><code>Текст - https://ссылка1.com</code>\n"
                                            "<code>Текст2 - https://ссылка2.com</code></blockquote>\n\n"
                                            "💡 <i>Каждая кнопка с новой строки!\n"
                                            "При добавлении новых кнопок старые сотрутся!</i>",
                                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                                [InlineKeyboardButton(text="❌ Убрать кнопки",
                                                                      callback_data=f"remove_buttons_{mailing_id}")],
                                                [InlineKeyboardButton(text="🔙 Назад",
                                                                      callback_data=f"back_to_{mailing_id}")]
                                            ]), parse_mode=ParseMode.HTML)

    for btn_data in buttons_data:
        button = Buttons(
            mailing_id=mailing_id,
            text=btn_data['text'],
            url=btn_data['url']
        )
        session.add(button)

    await session.commit()

    await message.answer(
        text="✅ <b>Кнопки рассылки успешно обновлены!</b>",
        parse_mode=ParseMode.HTML
    )

    await state.clear()


@router.callback_query(F.data.startswith("delete_mailing_"))
async def delete_mailing_handler(cq: CallbackQuery, state: FSMContext):
    mailing_id = int(cq.data.split("_")[2])
    await state.set_state(MailingEditing.waiting_for_delete_confirmation)
    await state.update_data(mailing_id=mailing_id)

    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_delete_{mailing_id}"),
        InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_{mailing_id}")
    )
    builder.adjust(1)

    await cq.message.edit_text(
        "❌ <b>Вы уверены, что хотите удалить эту рассылку?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

    await cq.answer()


@router.callback_query(F.data.startswith("confirm_delete_"))
async def confirm_delete_handler(cq: CallbackQuery, session: AsyncSession, state: FSMContext):
    mailing_id = int(cq.data.split("_")[2])

    await session.delete(await session.get(Mailings, mailing_id))
    await session.commit()

    await cq.message.edit_text(
        "✅ <b>Рассылка успешно удалена!</b>",
        parse_mode=ParseMode.HTML
    )

    await state.clear()
    await cq.answer()


@router.callback_query(F.data.startswith("toggle_status_"))
async def toggle_mailing_status(cq: CallbackQuery, session: AsyncSession):
    mailing_id = int(cq.data.split("_")[2])
    mailing = await session.get(Mailings, mailing_id)

    mailing.status = not mailing.status
    await session.commit()

    builder = kb_edits(mailing)

    await cq.message.edit_reply_markup(
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data == "back_to_mailings")
async def back_to_mailings_handler(cq: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()

    builder = await get_mailings_with_buttons(session)

    await cq.message.edit_text(
        "📦 <b>Меню рассылок:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

    await cq.answer()


@router.callback_query(F.data.startswith("back_to_"))
async def back_to_mailing(cq: CallbackQuery, session: AsyncSession, state: FSMContext):
    mailing_id = int(cq.data.split("_")[2])
    mailing = await session.get(Mailings, mailing_id, options=[selectinload(Mailings.buttons)])

    builder = kb_edits(mailing)

    await cq.message.edit_text(
        "📝 <b>Что хотите изменить?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

    await state.update_data(
        mailing_id=mailing.id,
    )
    await cq.answer()
