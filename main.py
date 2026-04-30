import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery


BOT_TOKEN = "bot_token"
CHANNEL_ID = -1001234567890
ADMIN_ID = 123456789

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()


@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("Отправь предложку: текст, фото, видео или файл до 50 МБ")


def file_size(m: Message) -> int:
    for item in (
        m.document,
        m.video,
        m.animation,
        m.audio,
        m.voice,
        m.video_note,
    ):
        if item:
            return item.file_size or 0

    if m.photo:
        return m.photo[-1].file_size or 0

    return 0


@dp.message(F.chat.type == "private")
async def suggest(m: Message):
    if m.text and m.text.startswith("/"):
        return

    size = file_size(m)

    if size > 50 * 1024 * 1024:
        await m.answer("Файл больше 50 МБ")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Одобрить", callback_data="ok"),
                InlineKeyboardButton(text="Отклонить", callback_data="no"),
            ]
        ]
    )

    try:
        await m.send_copy(
            chat_id=ADMIN_ID,
            reply_markup=kb
        )
        await m.answer("Отправлено на рассмотрение админа")
    except Exception:
        logging.exception("Failed to send suggestion to admin")
        await m.answer("Не удалось отправить предложку")


@dp.callback_query(F.data == "ok")
async def approve(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("Нет доступа", show_alert=True)
        return

    try:
        await bot.copy_message(
            chat_id=CHANNEL_ID,
            from_chat_id=ADMIN_ID,
            message_id=cb.message.message_id,
            reply_markup=None
        )
        await cb.message.edit_reply_markup(reply_markup=None)
        await cb.answer("Одобрено и опубликовано")
    except Exception:
        logging.exception("Failed to publish suggestion")
        await cb.answer("Не удалось опубликовать", show_alert=True)


@dp.callback_query(F.data == "no")
async def reject(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("Нет доступа", show_alert=True)
        return

    try:
        await cb.message.edit_reply_markup(reply_markup=None)
        await cb.answer("Отклонено")
    except Exception:
        logging.exception("Failed to reject suggestion")
        await cb.answer("Не удалось отклонить", show_alert=True)


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
