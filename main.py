import os
import logging
import random
import json
import aiohttp
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CallbackContext, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from aiohttp import ClientTimeout

from sqlhelper import Base, User, Post, Settings

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARN)
print('[Уведомление] Инициализация базы данных...')

engine = create_engine('sqlite:///database.db')
Base.metadata.create_all(engine)
Session = scoped_session(sessionmaker(bind=engine))

print('[Загрузка...] Инициализация API Telegram...')
token = 'your_token'  # Замените на ваш токен
app = ApplicationBuilder().token(token).build()

print('[Загрузка...] Создание временной папки...')
if not os.path.exists('temp'):
    os.makedirs('temp')

print('[Загрузка...] Проверяем настройки...')
session = Session()
settings = session.query(Settings).first()

if not settings:
    settings = Settings(False, None, None)
    session.add(settings)

initialized = settings.initialized
target_channel = settings.target_channel

if initialized:
    if target_channel:
        print('[Предложка] Настройки...[OK], target_channel: {}'.format(target_channel))
    elif settings.initializer_id:
        print('[Predlozhka][WARN] Bot seems to be initialized, but no target selected. Annoying initializer...')
        app.bot.send_message(settings.initializer_id, 'Warning! No target channel specified.')
    else:
        print('[Predlozhka][WARN] Bot seems to be initialized, but neither target or initializer specified. '
              'DB maintenance required!')
else:
    print('[Predlozhka][CRITICAL] Bot is not initialized! Waiting for initializer...')
session.commit()
session.close()

print('[Завершено] Последние штрихи...')

async def start(update: Update, context: CallbackContext):
    print('[Предложка][/start] Кто-то прописал start...')
    db = Session()
    if not db.query(User).filter_by(user_id=update.effective_user.id).first():
        db.add(User(update.effective_user.id))
    await update.message.reply_text('Привет, чтобы предложить пост в канал отправь изображение или видео, бот отправит твое сообщение админу на проверку.')
    db.commit()

async def initialize(update: Update, context: CallbackContext):
    global initialized, target_channel
    if not initialized:
        db = Session()
        print('[Predlozhka][INFO] Initialize command triggered!')
        initialized = True
        initializer = update.effective_user.id
        parameters = update.message.text.replace('/init ', '').split(';')
        print('[Predlozhka][INFO] Initializing parameters: {}'.format(parameters))
        target_channel = parameters[0]
        settings = db.query(Settings).first()
        settings.initialized = True
        settings.initializer_id = initializer
        settings.target_channel = target_channel
        await update.message.reply_text('Bot initialized successfully:\n{}'.format(repr(settings)))
        print('[Predlozhka] User {} selected as admin'.format(parameters[1]))
        target_user = db.query(User).filter_by(user_id=int(parameters[1])).first()
        if target_user:
            target_user.is_admin = True
            await update.message.reply_text('User {} is now admin!'.format(parameters[1]))
        else:
            print('[Predlozhka][WARN] User {} does not exist, creating...'.format(parameters[1]))
            await update.message.reply_text("Warning! User {} does not exist. "
                                            "I'll create it anyway, but you need to know.".format(parameters[1]))
            db.add(User(user_id=int(parameters[1]), is_admin=True))
        db.commit()
        db.close()

async def media_handler(update: Update, context: CallbackContext):
    print('[Предложка][Медиа] Медиа принято.')
    db = Session()

    media_file = None
    if update.message.video:
        media_file = update.message.video
    elif update.message.photo:
        media_file = update.message.photo[-1]
    elif update.message.document:
        media_file = update.message.document
    else:
        await update.message.reply_text('Ошибка: вы должны отправить изображение, видео или файл.')
        return

    try:
        file_info = await media_file.get_file()
        file_id = file_info.file_id
        
        # Проверяем размер файла
        if update.message.video and file_info.file_size > 20 * 1024 * 1024:  # 20 MB для видео
            await update.message.reply_text('Ошибка: файл слишком большой. Максимальный размер для видео — 20 МБ.')
            return
        elif update.message.photo and file_info.file_size > 10 * 1024 * 1024:  # 10 MB для фото
            await update.message.reply_text('Ошибка: файл слишком большой. Максимальный размер для фото — 10 МБ.')
            return
        elif update.message.document and file_info.file_size > 20 * 1024 * 1024:  # 20 MB для документов
            await update.message.reply_text('Ошибка: файл слишком большой. Максимальный размер для файлов — 20 МБ.')
            return

        if update.message.video:
            path = f'temp/{random.randint(1, 100000000000)}_{file_id}.mp4'
        elif update.message.photo:
            path = f'temp/{random.randint(1, 100000000000)}_{file_id}.jpg'
        else:  # для других документов
            path = f'temp/{random.randint(1, 100000000000)}_{file_id}.{media_file.file_name.split(".")[-1]}'

        timeout = ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(file_info.file_path, ssl=False) as response:
                if response.status == 200:
                    with open(path, 'wb') as f:
                        f.write(await response.read())
                else:
                    await update.message.reply_text('Ошибка загрузки файла.')
                    return

        print('[Предложка][Медиа] Медиа скачено.')
        post = Post(update.effective_user.id, path, update.message.caption)
        db.add(post)
        db.commit()

        print('[Предложка][Загрузка...] Отправляется сообщение админу...')
        buttons = [
            [InlineKeyboardButton('✅', callback_data=json.dumps({'post': post.post_id, 'action': 'accept'})),
             InlineKeyboardButton('❌', callback_data=json.dumps({'post': post.post_id, 'action': 'decline'}))]
        ]
        if update.message.video:
            await context.bot.send_video(
                db.query(User).filter_by(is_admin=True).first().user_id,
                open(post.attachment_path, 'rb'),
                caption=post.text,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        elif update.message.photo:
            await context.bot.send_photo(
                db.query(User).filter_by(is_admin=True).first().user_id,
                open(post.attachment_path, 'rb'),
                caption=post.text,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:  # для других файлов
            await context.bot.send_document(
                db.query(User).filter_by(is_admin=True).first().user_id,
                open(post.attachment_path, 'rb'),
                caption=post.text,
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        db.close()

        print('[Предложка][media_handler] Sending confirmation to source...')
        await update.message.reply_text('Ваш пост отправлен администратору.\nЕсли он будет опубликован - вы получите сообщение.')

    except Exception as e:
        print(f'[Predlozhka][media_handler] Error: {e}')
        await update.message.reply_text('Произошла ошибка при обработке вашего медиа.')
        db.close()

async def callback_handler(update: Update, context: CallbackContext):
    print('[Predlozhka][callback_handler] Processing admin interaction')
    db = Session()
    if db.query(User).filter_by(user_id=update.effective_user.id).first().is_admin:
        print('[Predlozhka][callback_handler][auth_ring] Authentication successful')
        data = json.loads(update.callback_query.data)
        print('[Predlozhka][callback_handler] Data: {}'.format(data))
        post = db.query(Post).filter_by(post_id=data['post']).first()
        if post:
            print('[Predlozhka][callback_handler] Post found')
            if data['action'] == 'accept':
                print('[Predlozhka][callback_handler] Action: accept')
                await context.bot.send_video(target_channel, open(post.attachment_path, 'rb'), caption=post.text) if post.attachment_path.endswith('.mp4') else \
                    await context.bot.send_photo(target_channel, open(post.attachment_path, 'rb'), caption=post.text) if post.attachment_path.endswith('.jpg') else \
                    await context.bot.send_document(target_channel, open(post.attachment_path, 'rb'), caption=post.text)
                await update.callback_query.answer('✅ Пост успешно отправлен')
                await context.bot.send_message(post.owner_id, 'Предложеный вами пост был опубликован')
            elif data['action'] == 'decline':
                print('[Predlozhka][callback_handler] Action: decline')
                await update.callback_query.answer('Пост отклонен')
            print('[Predlozhka][callback_handler] Cleaning up...')
            try:
                os.remove(post.attachment_path)
            except:
                pass
            db.delete(post)
            await context.bot.delete_message(update.callback_query.message.chat_id, update.callback_query.message.message_id)
        else:
            await update.callback_query.answer('Ошибка: пост не найден')
    else:
        print('[Predlozhka][callback_handler][auth_ring] Authentication ERROR!')
        await update.callback_query.answer('Unauthorized access detected!')
    db.commit()
    db.close()

print('[Предложка] Все, что связано с инициализацией, выполнено успешно.')

app.add_handler(CommandHandler('start', start))
app.add_handler(CommandHandler('init', initialize))
app.add_handler(MessageHandler(filters.ALL & filters.ChatType.PRIVATE, media_handler))
app.add_handler(CallbackQueryHandler(callback_handler))

app.run_polling()