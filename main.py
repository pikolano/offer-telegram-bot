import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery


BOT_TOKEN   = "bot_token"
CHANNEL_ID  = -148814886742
ADMIN_ID    = 123456789


bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("Отправь предложку (текст/медиа до 50 МБ)")


def file_size(m: Message) -> int:
    for item in (m.document, m.video, m.animation, m.audio, m.voice, m.video_note):
        if item:
            return item.file_size or 0
    return m.photo[-1].file_size if m.photo else 0


@dp.message(F.chat.type.in_({"private", "group", "supergroup"}))
async def suggest(m: Message):
    if m.text and m.text.startswith("/"):
        return

    size = file_size(m)
    if size > 50 * 1024 * 1024:
        await m.answer("Файл больше 50 МБ")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Одобрить", callback_data=f"ok:{m.message_id}"),
            InlineKeyboardButton(text="Отклонить", callback_data=f"no:{m.message_id}")
        ]
    ])

    await m.send_copy(ADMIN_ID, reply_markup=kb)
    await m.answer("Отправлено на рассмотрение админа")


@dp.callback_query(F.data.startswith("ok:"))
async def approve(cb: CallbackQuery):
    msg_id = int(cb.data.split(":")[1])
    await bot.copy_message(CHANNEL_ID, cb.from_user.id, msg_id)
    await cb.message.edit_text("✔ Одобрено и опубликованo")


@dp.callback_query(F.data.startswith("no:"))
async def reject(cb: CallbackQuery):
    await cb.message.edit_text("✖ Отклонено")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
