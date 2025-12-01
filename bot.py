#================================
# PANCHAN CARDS
# by. SharoPetr
# 01.12.2025
#================================

import asyncio
import aiosqlite
import random
from aiogram import Bot, Dispatcher, executor, types
import logging

#КОНФИГ
TOKEN = "8306114663:AAFvcz3mhU__2vLu6eASshzXJx70fIpiZQY"
DB_PATH = "database.db"
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

#ЛЮБЫЕ ЛОГИ ЧЕРЕЗ logging.info("ТЕКСТ ЛОГА")

#ИНИТ БД
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            visual_id TEXT UNIQUE, 
            username TEXT,
            first_name TEXT
        )
        """)
        await db.commit()

        # ТАБЛИЦА ЧАТОВ
        await db.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY,
            title TEXT,
            type TEXT
        )
        """)
        await db.commit()

#ВИЗУАЛЬНЫЙ АЙДИШНИК ПОЛЬЗОВАТЕЛЯ
def generate_visual_id() -> str:
    return str(random.randint(100000, 999999))

#ДОБАВЛЕНИЕ ЮЗЕРА В БД
async def add_user(user_id: int, username: str, first_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        #ПРОВЕРКА НА НАЛИЧИЕ ЮЗЕРА
        async with db.execute("SELECT visual_id FROM users WHERE id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()

        if row:  #УЖЕ ЕСТЬ В БД
            return row[0]

        visual_id = generate_visual_id()

        #ДОБАВЛЕНИЕ В БД
        await db.execute(
            "INSERT INTO users (id, username, first_name, visual_id) VALUES (?, ?, ?, ?)",
            (user_id, username, first_name, visual_id)
        )
        await db.commit()

        logging.info(f'🟢НОВЫЙ ПОЛЬЗОВАТЕЛЬ: {username} с ID {user_id}')

        return visual_id


# ДОБАВЛЕНИЕ ЧАТА В БД
async def add_chat(chat_id: int, title: str | None, chat_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        #ПРОВЕРКА НА НАЛИЧИЕ ЧАТА
        async with db.execute("SELECT id FROM chats WHERE id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()

        if row:
            return row[0]

        await db.execute(
            "INSERT INTO chats (id, title, type) VALUES (?, ?, ?)",
            (chat_id, title or '', chat_type)
        )
        await db.commit()

        logging.info(f"🟢НОВЫЙ ЧАТ: {chat_id} - {title} ({chat_type})")

        return chat_id
    
#ПРОВЕРКА ЕСТЬ ЛИ ЧАТ В БД
async def is_chat_in_db(chat_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM chats WHERE id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            return row is not None

#ПОЛУЧЕНИЯ ВИЗУАЛЬНОГО ID ЮЗЕРА
async def get_user_visual_id(user_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT visual_id FROM users WHERE id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
            return None





#СТАРТОВАЯ КОМАНДА
#КНОПКА ДЛЯ ДОБАВЛЕНИЯ БОТА В ГРУППУ
button = types.InlineKeyboardButton(
    text="➕ Добавить бота в группу",
    url="https://t.me/PanchanCardsBot?startgroup=new"
)

keyboard = types.InlineKeyboardMarkup().add(button)

#ОБРАБОТЧИК /start
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    chat_type = message.chat.type

    # ЛС - СТАРТ КОГДА УГОДНО ПРОПИСЫВАТЬ
    if chat_type == 'private':
        # ДОБАВЛЕНИЕ/ОБНОВЛЕНИЕ ЮЗЕРА В БД
        await add_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name
        )

        # СООБЩЕНИЕ ПРИ СТАРТЕ В ЛС
        await message.answer(
            f"👋 Привет! Тут ты можешь собирать уникальные карточки и соревноваться с другими игроками"
            f"\nКак получить карточки?"
            f"\n<blockquote>Отправь команду «панчан»</blockquote>"
            f"\n\nУзнать все функции можно по команде /help",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return

    #ГРУППА - РЕАГИРУЕМ ТОЛЬКО ПРИ ПЕРВОМ /start
    if chat_type in ['group', 'supergroup']:
        chat_exists = await is_chat_in_db(message.chat.id)
        if not chat_exists:
            # ДОБАВЛЕНИЕ ЧАТА В БД
            await add_chat(
                chat_id=message.chat.id,
                title=message.chat.title,
                chat_type=chat_type
            )

            #ОТВЕТ В ГРУППЕ ТОЛЬКО ПРИ ПЕРВОМ /start
            await message.answer(
                f"👋 Привет! Тут ты можешь собирать уникальные карточки и соревноваться с другими игроками"
                f"\nКак получить карточки?"
                f"\n<blockquote>Отправь команду «панчан»</blockquote>"
                f"\n\nУзнать все функции можно по команде /help",
                reply_markup=keyboard,
                parse_mode="HTML"
            )

        #ИГНОРИРУЕМ ПОСЛЕДУЮЩИЕ /start В ГРУППЕ
        return

    #ДЛЯ ДРУГИХ СЛУЧАЕВ ПРОСТО ИГНОРИРУЕМ
    return


#КОМНАНДА /help
@dp.message_handler(commands=['help'])
async def help_command(message: types.Message):

    await message.answer(
        "📚 <b>Что это за бот?</b> 📚"
        "\n<blockquote>/Тут ты можешь собирать карточки <b>Панчан</b> и сорвеноваться с другими игроками</blockquote>"
        "\n\n🃏 <b>Команды</b> 🃏"
        "\n<blockquote>/profile — ваш профиль</blockquote>"
        "\n\n<b>Чтобы получить случайную карточку, отправьте любую из команд</b>"
        "\n<blockquote>панчан\nкачан\nкарту\nполучить карту\n</blockquote>",
        parse_mode="HTML"
    )
    return

#КОМАНДА /profile
@dp.message_handler(commands=['profile'])
async def profile_command(message: types.Message):
    user = message.from_user
    user_visual_id = await get_user_visual_id(user.id) # ПОЛУЧЕНИЕ ВИЗУАЛЬНОГО ID ЮЗЕРА
    photos = await bot.get_user_profile_photos(user.id) # ПОЛУЧЕНИЕ ФОТО ПРОФИЛЯ ЧЕЛОВЕКА

    #ПОДПИСЬ К ПРОФИЛЮ
    caption = (
        f"👤 Профиль : <b>{user.first_name}</b>\n\n"
        f"🔎 ID: {user_visual_id}\n"
    )

    #ЕСЛИ НЕТ ФОТО, ТО ПРОСТО ОТПРАВЛЯЕМ ПОДПИСЬ
    if photos.total_count == 0:
        await message.answer(caption, parse_mode="HTML")
        return
    
    #ЕСЛИ ЕСТЬ ФОТО, ТО ПОЛУЧАЕМ FILE_ID САМОГО ПЕРВОГО ФОТО
    file_id = photos.photos[0][-1].file_id

    #СКИДЫВАЕМ ФОТО ПРОФИЛЯ С ПОДПИСЬЮ
    await message.answer_photo(
        photo=file_id,
        caption=caption,
        parse_mode="HTML"
    )

#ИНИТ
async def on_startup(_):
    await init_db()
    logging.info("✅УСПЕШНАЯ ИНИЦИАЛИЗАЦИЯ✅")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
