import re
from datetime import datetime

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import bot, CHAT_ID, MSK
from db.models import Mailings, Buttons
from misc.utils import send_mailing

router = Router()


PERIODICITY_REGEX = re.compile(r'^(\d+[dhm]\s*)+$')
GLOBAL_PERIODICITY_REGEX = re.compile(r'^(\d+[Mwd]\s*)+$')

class MailingCreation(StatesGroup):
    waiting_for_text = State()
    waiting_for_media = State()
    waiting_for_per = State()
    waiting_for_globalper = State()
    waiting_for_buttons = State()
    confirmation = State()


@router.callback_query(F.data == 'create_mailing')
async def create_mailing(cq: CallbackQuery, state: FSMContext):
    await state.set_state(MailingCreation.waiting_for_text)
    await cq.message.edit_text(
        "<b>💬 Введите текст рассылки:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")]
        ]), parse_mode=ParseMode.HTML
    )
    await cq.answer()


@router.message(MailingCreation.waiting_for_text)
async def process_mailing_text(message: Message, state: FSMContext):
    await state.update_data(text=message.html_text)
    await state.set_state(MailingCreation.waiting_for_media)

    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="▶️ Пропустить", callback_data="skip_media"))
    builder.add(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation"))
    builder.adjust(1)

    await message.answer(
        "✅ <i>Текст принят!</i>"
        "\n\n💾 <b>Отправьте фото, видео или GIF для рассылки (одно медиа):</b>",
        reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
    )


@router.callback_query(F.data == "skip_media", MailingCreation.waiting_for_media)
async def skip_media(cq: CallbackQuery, state: FSMContext):
    await state.update_data(media=None)
    await state.set_state(MailingCreation.waiting_for_per)
    await cq.message.edit_text(
        "▶️ <i>Медиа пропущено!</i>"
        "\n\n🕒 <b>Введите периодичность отправки:</b>\n"
        "<blockquote>Примеры: <code>30m, 1h, 2d</code></blockquote>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")]
        ]), parse_mode=ParseMode.HTML
    )
    await cq.answer()


@router.message(MailingCreation.waiting_for_media, F.photo | F.video | F.animation)
async def process_mailing_media(message: Message, state: FSMContext):
    if message.photo:
        media_id = message.photo[-1].file_id
    elif message.video:
        media_id = message.video.file_id
    elif message.animation:
        media_id = message.animation.file_id
    else:
        return await message.answer('❌ <i>Неверный формат.</i>'
                                    '\n\n💾 <b>Отправьте фото, видео или GIF для рассылки (одно медиа):</b>',
                                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")]
                                    ]), parse_mode=ParseMode.HTML
                                    )

    await state.update_data(media=media_id)
    await state.set_state(MailingCreation.waiting_for_per)

    await message.answer(
        "✅ <i>Медиа принято!</i>"
        "\n\n🕒 <b>Введите периодичность отправки:</b>\n"
        "<blockquote>Примеры: <code>30m, 1h, 2d</code></blockquote>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")]
        ]), parse_mode=ParseMode.HTML
    )


@router.message(MailingCreation.waiting_for_per)
async def process_periodicity(message: Message, state: FSMContext):
    if not message.text or not PERIODICITY_REGEX.match(message.text.strip()):
        return await message.answer("❌ <i>Неверный формат.</i>"
                                    "\n\n🕒 <b>Введите периодичность отправки:</b>\n"
                                    "<blockquote>Примеры: <code>30m, 1h, 2d</code></blockquote>",
                                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")]
                                    ]), parse_mode=ParseMode.HTML)

    await state.update_data(per=message.text)
    await state.set_state(MailingCreation.waiting_for_globalper)

    await message.answer(
        "✅ <i>Периодичность принята!</i>"
        "\n\n<b>🗓️ Введите глобальную периодичность (когда рассылка прекратится):</b>\n"
        "<blockquote>Примеры: <code>1M, 2w, 3d</code></blockquote>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")]
        ]), parse_mode=ParseMode.HTML
    )


@router.message(MailingCreation.waiting_for_globalper)
async def process_global_periodicity(message: Message, state: FSMContext):
    if not message.text or not GLOBAL_PERIODICITY_REGEX.match(message.text.strip()):
        return await message.answer("❌ <i>Неверный формат.</i>"
                                    "\n\n<b>🗓️ Введите глобальную периодичность (когда рассылка прекратится):</b>\n"
                                    "<blockquote>Примеры: <code>1M, 2w, 3d</code></blockquote>",
                                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")]
                                    ]), parse_mode=ParseMode.HTML)

    await state.update_data(globalper=message.text)
    await state.set_state(MailingCreation.waiting_for_buttons)

    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="▶️ Пропустить", callback_data="no_buttons"))
    builder.add(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation"))
    builder.adjust(1)

    await message.answer(
        "✅ <i>Глобальная периодичность принята!</i>"
        "\n\n🎛️ <b>Добавьте кнопки в формате:</b>\n"
        "<blockquote><code>Текст - https://ссылка1.com</code>\n"
        "<code>Текст2 - https://ссылка2.com</code></blockquote>\n\n"
        "💡 <i>Каждая кнопка с новой строки!</i>",
        reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
    )


@router.callback_query(F.data == "no_buttons", MailingCreation.waiting_for_buttons)
async def no_buttons(cq: CallbackQuery, state: FSMContext):
    await state.update_data(buttons=[])
    await show_confirmation(cq.message, state)
    await cq.answer()


@router.message(MailingCreation.waiting_for_buttons)
async def process_buttons(message: Message, state: FSMContext):
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
                                            "\n\n🎛️ <b>Добавьте кнопки в формате:</b>\n"
                                            "<blockquote><code>Текст - https://ссылка1.com</code>\n"
                                            "<code>Текст2 - https://ссылка2.com</code></blockquote>\n\n"
                                            "💡 <i>Каждая кнопка с новой строки!</i>",
                                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                                [InlineKeyboardButton(text="▶️ Пропустить", callback_data="no_buttons")],
                                                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")]
                                            ]), parse_mode=ParseMode.HTML)

    await state.update_data(buttons=buttons_data)
    await show_confirmation(message, state)


async def show_confirmation(message: Message, state: FSMContext):
    data = await state.get_data()

    text = data.get('text', 'Нет текста')
    media = data.get('media')
    buttons = data.get('buttons', [])

    reply_markup = None
    if buttons:
        kb = InlineKeyboardBuilder()
        for btn in buttons:
            kb.add(InlineKeyboardButton(text=btn['text'], url=btn['url']))
        kb.adjust(1)
        reply_markup = kb.as_markup()

    try:
        if media:
            if isinstance(media, str):
                if media.startswith('AgAC'):
                    await message.answer_photo(
                        media,
                        caption=text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup
                    )
                elif media.startswith('BAAC'):
                    await message.answer_video(
                        media,
                        caption=text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup
                    )
                elif media.startswith('CgAC'):
                    await message.answer_animation(
                        media,
                        caption=text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup
                    )
                else:
                    await message.answer(
                        text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup
                    )
            else:
                await message.answer(
                    text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
        else:
            await message.answer(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Ошибка при отправке сообщения: {e}")
        await message.answer(
            "❌ <b>Произошла ошибка при создании предпросмотра. Проверьте данные и попробуйте еще раз.</b>"
        , parse_mode=ParseMode.HTML)
        return await state.clear()

    confirm_kb = InlineKeyboardBuilder()
    confirm_kb.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_mailing"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data="cancel_creation")
    )
    confirm_kb.adjust(1)

    await message.answer(
        "📢 <b>Вы подтверждаете создание рассылки?</b>",
        reply_markup=confirm_kb.as_markup(), parse_mode=ParseMode.HTML
    )

    await state.set_state(MailingCreation.confirmation)


@router.callback_query(F.data == "confirm_mailing", MailingCreation.confirmation)
async def confirm_mailing(cq: CallbackQuery, session: AsyncSession, state: FSMContext):
    data = await state.get_data()

    mailing = Mailings(
        text=data['text'],
        media=data.get('media'),
        per=data['per'],
        globalper=data['globalper'],
        status=True
    )

    session.add(mailing)
    await session.commit()
    await session.refresh(mailing)

    if 'buttons' in data and data['buttons']:
        for btn_data in data['buttons']:
            button = Buttons(
                mailing_id=mailing.id,
                text=btn_data['text'],
                url=btn_data['url']
            )
            session.add(button)
        await session.commit()

    await state.clear()
    await cq.message.edit_text("✅ <b>Рассылка успешно создана!</b>", parse_mode=ParseMode.HTML)

    try:
        from db.models import async_session as new_async_session
        async with new_async_session() as new_session:
            fresh_mailing = await new_session.get(
                Mailings,
                mailing.id,
                options=[selectinload(Mailings.buttons)]
            )

            message_id = await send_mailing(cq.bot, CHAT_ID, fresh_mailing)

            if message_id:
                fresh_mailing.last_sent = datetime.now(MSK)
                fresh_mailing.last_message_id = message_id
                await new_session.commit()

    except Exception as e:
        print(f"Ошибка при первой отправке рассылки: {e}")

    await cq.answer()


@router.callback_query(F.data == "cancel_creation")
async def cancel_creation(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await cq.message.edit_text("❌ <b>Создание рассылки отменено.</b>", parse_mode=ParseMode.HTML)
    await cq.answer()
