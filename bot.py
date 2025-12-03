#================================
# PANCHAN CARDS
# by. SharoPetr
# 01.12.2025
#================================

import asyncio
import aiosqlite
import random
import logging
import os
import json
import datetime
from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher.filters import Regexp

#КОНФИГ
TOKEN = "8484717385:AAENK80yEByo5tDCQDgK-uksC7q16268RaE"
DB_PATH = "database.db"
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

logging.basicConfig(level=logging.INFO)
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

#ЛЮБЫЕ ЛОГИ ЧЕРЕЗ logging.info("ТЕКСТ ЛОГА")

PANCHAN_PATH = "panchans"

#РЕДКОСТИ ШАНС В %
RARITY_POOL = {
    "common": 0.70,
    "rare": 0.25
}

#ИНИТ БД
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            visual_id TEXT UNIQUE, 
            visual_username TEXT,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            last_panchan_at TEXT
        )
        """)
        await db.commit()

        # ТАБЛИЦА ДЛЯ ХРАНЕНИЯ БАЛАНСОВ (очки / монеты)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_balances (
            user_id INTEGER PRIMARY KEY,
            points INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0
        )
        """)
        await db.commit()

        # ТАБЛИЦА ДЛЯ ХРАНЕНИЯ ПОЛУЧЕННЫХ КАРТОЧЕК
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            filename TEXT,
            panchan_id INTEGER,
            rarity TEXT,
            points INTEGER,
            coins INTEGER,
            created_at TEXT
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
        visual_username = f"{first_name}"

        #ДОБАВЛЕНИЕ В БД
        await db.execute(
            "INSERT INTO users (id, username, first_name, visual_id, visual_username) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, first_name, visual_id, visual_username)
        )
        await db.commit()

        logging.info(f'🟢НОВЫЙ ПОЛЬЗОВАТЕЛЬ: {username} с ID {user_id}')
        async with aiosqlite.connect(DB_PATH) as db2:
            await db2.execute("INSERT OR IGNORE INTO user_balances (user_id, points, coins) VALUES (?, 0, 0)", (user_id,))
            await db2.commit()

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


#ПОЛУЧЕНИЕ БАЛАНСА ЮЗЕРА
async def get_user_balance(user_id: int) -> tuple[int, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT points, coins FROM user_balances WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0], row[1]

        await db.execute("INSERT OR IGNORE INTO user_balances (user_id, points, coins) VALUES (?, 0, 0)", (user_id,))
        await db.commit()
        return 0, 0


#СОХРАНЕНИЕ ПОЛУЧЕННОЙ КАРТОЧКИ ЮЗЕРОМ
async def add_user_card(user_id: int, filename: str, metadata: dict, rarity: str):
    async with aiosqlite.connect(DB_PATH) as db:
        # Проверяем, есть ли уже такая карточка у пользователя
        async with db.execute("SELECT 1 FROM user_cards WHERE user_id = ? AND filename = ? LIMIT 1", (user_id, filename)) as cursor:
            row = await cursor.fetchone()
        if row:
            return False

        await db.execute(
            "INSERT INTO user_cards (user_id, filename, panchan_id, rarity, points, coins, created_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            (user_id, filename, metadata.get('id'), rarity, metadata.get('points', 0), metadata.get('coins', 0))
        )
        await db.commit()
        return True


#НАЧИСЛЕНИЕ БАЛАНСА ЮЗЕРУ
async def increment_user_balance(user_id: int, points: int = 0, coins: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO user_balances (user_id, points, coins) VALUES (?, 0, 0)", (user_id,))
        await db.execute("UPDATE user_balances SET points = points + ?, coins = coins + ? WHERE user_id = ?", (points, coins, user_id))
        await db.commit()

#ПОЛУЧЕНИЯ ВИЗУАЛЬНОГО ID ЮЗЕРА
async def get_user_visual_id(user_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT visual_id FROM users WHERE id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
            return None
        
#ПОЛУЧЕНИЯ ВИЗУАЛЬНОГО USERNAME ЮЗЕРА
async def get_user_visual_username(user_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT visual_username FROM users WHERE id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
            return None

#СДЕЛАТЬ 

#ВЫБОР РЕДКОСТИ ПО ВЕСАМ
def choose_rarity():
    rarities = list(RARITY_POOL.keys())
    weights = list(RARITY_POOL.values())
    return random.choices(rarities, weights=weights, k=1)[0]

#ПОЛУЧЕНИЕ СЛУЧАЙНОЙ ПАРЫ JPG + JSON
def get_random_image_pair():
    rarity = choose_rarity()
    rarity_path = os.path.join(PANCHAN_PATH, rarity)

    # ФИЛЬТРУЕМ ВСЕ JPG ФАЙЛЫ В ПАПКЕ
    jpg_files = [f for f in os.listdir(rarity_path) if f.endswith(".jpg")]
    if not jpg_files:
        logging.info(f"Нет изображений в папке: {rarity_path}")
        return None

    #СЛУЧАЙНЫЙ JPG
    jpg = random.choice(jpg_files)

    base_name = os.path.splitext(jpg)[0]
    json_file = base_name + ".json"

    jpg_path = os.path.join(rarity_path, jpg)
    json_path = os.path.join(rarity_path, json_file)

    if not os.path.exists(json_path):
        logging.info(f"Нет JSON для {jpg}")
        return None

    return jpg_path, json_path


#ПРОВЕРКА ЕСТЬ ЛИ ФАЙЛ У ЮЗЕРА
async def user_has_file(user_id: int, filename: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM user_cards WHERE user_id = ? AND filename = ? LIMIT 1", (user_id, filename)) as cursor:
            row = await cursor.fetchone()
            return row is not None


#ПОЛУЧЕНИЕ СПИСКА НЕПРИОБРЕТЕННЫХ ФАЙЛОВ ПО РЕДКОСТИ
async def get_unowned_files_by_rarity(user_id: int, rarity: str) -> list:
    rarity_path = os.path.join(PANCHAN_PATH, rarity)
    if not os.path.isdir(rarity_path):
        return []

    jpg_files = [f for f in os.listdir(rarity_path) if f.endswith('.jpg')]

    unowned = []
    for jpg in jpg_files:
        if not await user_has_file(user_id, jpg):
            unowned.append(jpg)

    return unowned



#ПОЛУЧЕНИЕ ВРЕМЕНИ ПОСЛЕДНЕГО ПАНЧАНА
async def get_last_panchan_time(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT last_panchan_at FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()

        if row is None or row[0] is None:
            return None

        try:
            return datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        except:
            return None
        

#ОБНОВЛЕНИЕ ВРЕМЕНИ ПОСЛЕДНЕГО ПАНЧАНА
async def update_last_panchan_time(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute("UPDATE users SET last_panchan_at = ? WHERE id = ?", (now, user_id))
        await db.commit()


async def choose_card_for_user(user_id: int):
    # ОБЩИЙ СПИСОК ВСЕХ РЕДКОСТЕЙ
    rarities = list(RARITY_POOL.keys())

    #выбор редкости
    chosen_rarity = choose_rarity()
    rarity_path = os.path.join(PANCHAN_PATH, chosen_rarity)

    #получаем все карточки в этой редкости
    jpg_candidates = []
    if os.path.isdir(rarity_path):
        jpg_candidates = [f for f in os.listdir(rarity_path) if f.endswith('.jpg')]

    #если в выбранной редкости нет карточек, ищем в других редкостях
    if not jpg_candidates:
        other = rarities[:]
        random.shuffle(other)
        for r in other:
            rp = os.path.join(PANCHAN_PATH, r)
            if os.path.isdir(rp):
                jpg_candidates = [f for f in os.listdir(rp) if f.endswith('.jpg')]
                if jpg_candidates:
                    chosen_rarity = r
                    rarity_path = rp
                    break

    if not jpg_candidates:
        return None

    #случайный выбор карточки
    jpg = random.choice(jpg_candidates)
    jpg_path = os.path.join(rarity_path, jpg)
    json_path = os.path.splitext(jpg_path)[0] + '.json'

    #прверка
    already_owned = await user_has_file(user_id, jpg)

    return jpg_path, json_path, chosen_rarity, already_owned, jpg




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
    user = message.from_user
    await add_user(user.id, user.username, user.first_name)

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
        "\n<blockquote>панчан\nкачан\nкарту\nполучить карту\nпачан</blockquote>",
        parse_mode="HTML"
    )
    return




#ВОЗВРАТЫ
keyboard_back_inventory = types.InlineKeyboardMarkup()
button_back_inventory = types.InlineKeyboardButton("‹ Назад", callback_data="back_inventory")
keyboard_back_inventory.add(button_back_inventory)  

#КЛАВИАТУРА ПРОФИЛЯ
keyboard_profile = types.InlineKeyboardMarkup()
button_inventory = types.InlineKeyboardButton("🎒Инвентарь", callback_data="inventory")
button_cards = types.InlineKeyboardButton("🃏Мои карточки", callback_data="my_cards")
keyboard_profile.add(button_inventory)
keyboard_profile.add(button_cards)


#КОМАНДА /profile
@dp.message_handler(commands=['profile'])
async def profile_command(message: types.Message):
    user = message.from_user
    await add_user(user.id, user.username, user.first_name)
    user_visual_id = await get_user_visual_id(user.id) # ПОЛУЧЕНИЕ ВИЗУАЛЬНОГО ID ЮЗЕРА
    photos = await bot.get_user_profile_photos(user.id) # ПОЛУЧЕНИЕ ФОТО ПРОФИЛЯ ЧЕЛОВЕКА

    points, coins = await get_user_balance(user.id)

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM user_cards WHERE user_id = ?", (user.id,)) as cursor:
            row = await cursor.fetchone()
            cards_count = row[0] if row else 0

    #ПОДПИСЬ К ПРОФИЛЮ
    caption = (
        f"👤 Профиль : <b>{user.first_name}</b>\n\n"
        f"🔎 ID: {user_visual_id}\n"
        f"💰 Монеты: <b>{coins}</b>\n"
        f"⭐ Очки: <b>{points}</b>\n"
        f"🃏 Коллекция: <b>{cards_count}</b> карточек\n"
    )  

    #ЕСЛИ НЕТ ФОТО, ТО ПРОСТО ОТПРАВЛЯЕМ ПОДПИСЬ
    if photos.total_count == 0:
        await message.answer(caption, reply_markup=keyboard_profile, parse_mode="HTML")
        return
    
    #ЕСЛИ ЕСТЬ ФОТО, ТО ПОЛУЧАЕМ FILE_ID САМОГО ПЕРВОГО ФОТО
    file_id = photos.photos[0][-1].file_id

    #СКИДЫВАЕМ ФОТО ПРОФИЛЯ С ПОДПИСЬЮ
    await message.answer_photo(
        photo=file_id,
        caption=caption,
        reply_markup=keyboard_profile,
        parse_mode="HTML"
    )

#ИНВЕНТАРЬ
@dp.callback_query_handler(lambda c: c.data == 'inventory')
async def inventory_callback(callback_query: types.CallbackQuery):
    #ТУТ НИЧЕГО НЕТУ ПОКА ЧТО
    await callback_query.message.delete()

    await bot.send_message(
        chat_id=callback_query.from_user.id,
        text="🎒Инвентарь\n<blockquote>Ваш инвентарь пуст</blockquote>",
        reply_markup=keyboard_back_inventory,
        parse_mode="HTML"
    )
    await callback_query.answer()

#ВОЗВРАТ ИЗ ИНВЕНТАРЯ
@dp.callback_query_handler(lambda c: c.data == 'back_inventory')
async def back_inventory_callback(callback_query: types.CallbackQuery):
    user = callback_query.from_user
    user_visual_id = await get_user_visual_id(user.id) # ПОЛУЧЕНИЕ ВИЗУАЛЬНОГО ID ЮЗЕРА
    photos = await bot.get_user_profile_photos(user.id) # ПОЛУЧЕНИЕ ФОТО ПРОФИЛЯ ЧЕЛОВЕКА

    points, coins = await get_user_balance(user.id)

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM user_cards WHERE user_id = ?", (user.id,)) as cursor:
            row = await cursor.fetchone()
            cards_count = row[0] if row else 0

    #ПОДПИСЬ К ПРОФИЛЮ
    caption = (
        f"👤 Профиль : <b>{user.first_name}</b>\n\n"
        f"🔎 ID: {user_visual_id}\n"
        f"💰 Монеты: <b>{coins}</b>\n"
        f"⭐ Очки: <b>{points}</b>\n"
        f"🃏 Коллекция: <b>{cards_count}</b> карточек\n"
    )  

    #ЕСЛИ НЕТ ФОТО, ТО ПРОСТО ОТПРАВЛЯЕМ ПОДПИСЬ
    if photos.total_count == 0:
        await callback_query.message.edit_text(caption, reply_markup=keyboard_profile, parse_mode="HTML")
        await callback_query.answer()
        return
    
    #ЕСЛИ ЕСТЬ ФОТО, ТО ПОЛУЧАЕМ FILE_ID САМОГО ПЕРВОГО ФОТО
    file_id = photos.photos[0][-1].file_id

    #СКИДЫВАЕМ ФОТО ПРОФИЛЯ С ПОДПИСЬЮ
    await callback_query.message.delete()
    await bot.send_photo(
        chat_id=callback_query.from_user.id,
        photo=file_id,
        caption=caption,
        reply_markup=keyboard_profile,
        parse_mode="HTML"
    )
    await callback_query.answer()







#ОБРАБОТЧИК КОМАНД ДЛЯ ПОЛУЧЕНИЯ КАРТОЧКИ
@dp.message_handler(Regexp(r'^(панчан|качан|карту|получить карту|пачан)$'))
async def send_panchan(message: types.Message):
    user_id = message.from_user.id

    # таймер
    last_time = await get_last_panchan_time(user_id)
    now = datetime.datetime.utcnow()

    if last_time is not None:
        diff = now - last_time
        cooldown = 60 * 60 * 4 #4 часа
        if diff.total_seconds() < cooldown:
            wait = int(cooldown - diff.total_seconds())
            wait_hours = wait // 3600
            wait_minutes = (wait % 3600) // 60
            wait_seconds = wait % 60
            return await message.reply(
                f"Вы осмотрелись, но не увидели рядом <b>Панчан</b> 👀\n\n"
                f"🕛 Попробуйте через <b>{wait_hours}ч. {wait_minutes}мин. {wait_seconds}сек.</b>",
                parse_mode="HTML"
            )

    #регистрация пользователя
    await add_user(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )

    points, coins = await get_user_balance(user_id)

    #выбор карточки
    choice = await choose_card_for_user(user_id)
    if choice is None:
        return await message.answer("❌ ОШИБКА: Не удалось найти карточку.")

    jpg_path, json_path, chosen_rarity, already_owned, filename = choice

    #джисон метадата
    with open(json_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    if not metadata.get("rarity"):
        metadata["rarity"] = chosen_rarity or os.path.basename(os.path.dirname(jpg_path))

    #очко
    try:
        pts_add = int(metadata.get("points", 0))
    except:
        pts_add = 0
    try:
        cns_add = int(metadata.get("coins", 0))
    except:
        cns_add = 0

    new_points = points + pts_add
    new_coins = coins + cns_add

    #подпись
    base_caption = (
        f"🎴 Новая карточка — <b>{metadata.get('title', 'Без названия')}</b>\n\n"
        f"{metadata.get('description', '')}\n\n"
        f"⭐ Редкость: <b>{metadata.get('rarity')}</b>\n"
        f"🏆 Очки: +<b>{pts_add} [{new_points}]</b>\n"
        f"💰 Монеты: +<b>{cns_add} [{new_coins}]</b>"
    )

    if already_owned:
        caption = (
            f"🌟 Карточка — <b>{metadata.get('title')}</b> уже была у вас\n\n"
            f"⭐ Редкость: <b>{metadata.get('rarity')}</b>\n"
            f"🏆 Очки: +<b>{pts_add} [{new_points}]</b>\n"
            f"💰 Монеты: +<b>{cns_add} [{new_coins}]</b>\n\n"
            f"<blockquote>Будут начислены только очки</blockquote>"
        )
    else:
        caption = base_caption

    #отправка карты
    try:
        with open(jpg_path, "rb") as photo:
            await message.answer_photo(photo, caption=caption, parse_mode="HTML")

        if not already_owned:
            await add_user_card(user_id, filename, metadata, metadata.get("rarity"))

        await increment_user_balance(
            user_id,
            points=int(metadata.get("points", 0)),
            coins=int(metadata.get("coins", 0))
        )

        #обновляем last_panchan_at
        await update_last_panchan_time(user_id)

    except Exception:
        logging.exception("Ошибка при отправке карточки")
        return await message.answer("❌ Ошибка при выдаче карточки. Попробуйте позже.")









#ИНИТ
async def on_startup(_):
    await init_db()
    logging.info("✅УСПЕШНАЯ ИНИЦИАЛИЗАЦИЯ✅")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
