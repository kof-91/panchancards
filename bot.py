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
import io
import textwrap
import datetime
from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher.filters import Regexp
import re
from datetime import timedelta
from zoneinfo import ZoneInfo   
from PIL import Image, ImageDraw, ImageFont

#КОНФИГ
TOKEN = ""
DB_PATH = "database.db"
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
BOT_USERNAME = None

#ЧАСОВОЙ ПОЯС
MSK = ZoneInfo("Europe/Moscow")

logging.basicConfig(level=logging.INFO)
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
#ЛЮБЫЕ ЛОГИ ЧЕРЕЗ logging.info("ТЕКСТ ЛОГА")

PANCHAN_PATH = "panchans"

#ЗАГРУЗКА СТИКЕРОВ
with open("stickers.json", "r", encoding="utf-8") as f:
    STICKERS = json.load(f)

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
            last_panchan_at TEXT,
            have_bonus INTEGER DEFAULT 0,
            last_bonus_at TEXT
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
            "INSERT INTO users (id, username, first_name, visual_id, visual_username, have_bonus) VALUES (?, ?, ?, ?, ?, 0)",
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

#ОТОБРАЖЕНИЕ РЕДКОСТИ
def rarity_display(rarity: str) -> str:
    mapping = {
        "common": "🍃 Обычная",
        "rare": "✨ Редкая",
        "superrare": "🌟 Суперредкая",
        "legendary": "🔥 Легендарная",
        "mythical": "🌀 Мифическая",
        "chronicle": "📜 Летописная"
    }
    if not rarity:
        return "Хуй его знает"
    return mapping.get(rarity, str(rarity).capitalize())

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


#ГЕНЕРАЦИЯ КАРТИНКИ (НЕ ЛЕЗЬТЕ ТУДА ПОЖАЛУЙСТА)
IMAGE_SIZE = (1024, 512)
BACKGROUND_COLOR = (17, 17, 17)
TEXT_COLOR = (255, 255, 255)
FONT_SIZE = 96
SHIFT = 230 
PICTURE_MAX_CHARS = 300
PREFERRED_FONTS = ["DejaVuSans.ttf", "arial.ttf"]



def _round_corners(im: Image.Image, radius: int) -> Image.Image:
    mask = Image.new('L', im.size, 0)
    dd = ImageDraw.Draw(mask)
    try:
        dd.rounded_rectangle([(0, 0), im.size], radius=radius, fill=255)
    except Exception:
        dd.rectangle([(0, 0), im.size], fill=255)
    out = Image.new('RGBA', im.size)
    out.paste(im, (0, 0), mask)
    return out


def create_picture(text: str, author_name: str = "", author_username: str = "", bot_username: str = "", author_image: Image.Image = None) -> io.BytesIO:
    img = Image.new("RGB", IMAGE_SIZE, BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)

    margin = 20

    profile_size = 300
    profile_x = int(IMAGE_SIZE[0] * 0.14 - profile_size // 2)
    profile_y = (IMAGE_SIZE[1] - profile_size) // 2
    left_reserved = profile_x + profile_size + 24

    max_w = IMAGE_SIZE[0] - left_reserved - margin
    max_h = IMAGE_SIZE[1] - 2 * margin

    truetype_available = False
    MAIN_FONT_NAME = None
    for _f in PREFERRED_FONTS:
        try:
            font = ImageFont.truetype(_f, FONT_SIZE)
            truetype_available = True
            MAIN_FONT_NAME = _f
            break
        except Exception:
            continue
    if not truetype_available:
        font = ImageFont.load_default()
        MAIN_FONT_NAME = None

    def wrap_text_to_width(text: str, font_obj) -> str:
        words = text.split()
        if not words:
            return text
        lines = []
        line = words[0]
        for w in words[1:]:
            test = f"{line} {w}"
            try:
                width = draw.textlength(test, font=font_obj)
            except Exception:
                try:
                    width = font_obj.getsize(test)[0]
                except Exception:
                    width = len(test) * (FONT_SIZE // 2)
            if width <= max_w:
                line = test
            else:
                lines.append(line)
                line = w
        lines.append(line)
        return "\n".join(lines)

    font_size = FONT_SIZE
    min_font_size = 14
    wrapped = text

    if truetype_available:
        while font_size >= min_font_size:
            try:
                if MAIN_FONT_NAME:
                    font = ImageFont.truetype(MAIN_FONT_NAME, font_size)
                else:
                    font = ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()
                break

            wrapped = wrap_text_to_width(text, font)

            try:
                bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
            except Exception:
                try:
                    text_w, text_h = font.getsize_multiline(wrapped)
                except Exception:
                    lines = wrapped.splitlines() or [wrapped]
                    text_w = 0
                    text_h = 0
                    try:
                        sample_h = draw.textsize("A", font=font)[1]
                        line_spacing = max(4, int(sample_h * 0.2))
                    except Exception:
                        line_spacing = 4
                    for i, ln in enumerate(lines):
                        try:
                            w, h = draw.textsize(ln, font=font)
                        except Exception:
                            w = len(ln) * (font_size // 2)
                            h = font_size
                        text_w = max(text_w, w)
                        text_h += h
                        if i < len(lines) - 1:
                            text_h += line_spacing

            if text_w <= max_w and text_h <= max_h:
                break

            font_size -= 2

        if font_size < min_font_size:
            if truetype_available and MAIN_FONT_NAME:
                try:
                    font = ImageFont.truetype(MAIN_FONT_NAME, min_font_size)
                except Exception:
                    font = ImageFont.load_default()
            else:
                font = ImageFont.load_default()
            wrapped = wrap_text_to_width(text, font)
            lines = wrapped.splitlines()
            try:
                _, line_h = font.getsize("A")
            except Exception:
                line_h = min_font_size
            max_lines = max(1, max_h // line_h)
            if len(lines) > max_lines:
                lines = lines[:max_lines]
                if lines:
                    lines[-1] = lines[-1].rstrip()
                    if len(lines[-1]) > 3:
                        lines[-1] = lines[-1][:-3] + '...'
                    else:
                        lines[-1] = lines[-1] + '...'
                wrapped = "\n".join(lines)

    else:
        wrapped = textwrap.fill(text, width=30)

    try:
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    except Exception:
        try:
            text_width, text_height = font.getsize_multiline(wrapped)
        except Exception:
            lines = wrapped.splitlines() or [wrapped]
            text_width = 0
            text_height = 0
            try:
                sample_h = draw.textsize("A", font=font)[1]
                line_spacing = max(4, int(sample_h * 0.2))
            except Exception:
                line_spacing = 4
            for i, line in enumerate(lines):
                try:
                    w, h = draw.textsize(line, font=font)
                except Exception:
                    w = len(line) * (FONT_SIZE // 2)
                    h = FONT_SIZE
                text_width = max(text_width, w)
                text_height += h
                if i < len(lines) - 1:
                    text_height += line_spacing

    available_width = IMAGE_SIZE[0] - left_reserved - margin
    x = left_reserved + max(0, (available_width - text_width) // 2) + SHIFT
    x = max(left_reserved + 8, min(x, IMAGE_SIZE[0] - margin - text_width))
    y = (IMAGE_SIZE[1] - text_height) // 2
    y = max(margin, min(y, IMAGE_SIZE[1] - margin - text_height))

    draw.multiline_text((x, y), wrapped, fill=TEXT_COLOR, font=font, align="left")

    profile_size = 300
    profile_x = int(IMAGE_SIZE[0] * 0.18 - profile_size // 2)
    profile_y = (IMAGE_SIZE[1] - profile_size) // 2

    try:
        if author_image is not None:
            prof = author_image.convert("RGBA")
            prof = prof.resize((profile_size, profile_size), Image.LANCZOS)
            prof = _round_corners(prof, radius=28)
        else:
            initials = ''
            if author_name:
                initials = ''.join([p[0].upper() for p in author_name.split()[:2] if p])
            if not initials and author_username:
                initials = ''.join([c for c in author_username.replace('@','')[:2]]).upper()
            prof = Image.new('RGBA', (profile_size, profile_size), (38, 117, 255))
            pd = ImageDraw.Draw(prof)
            try:
                pd.rounded_rectangle([(0, 0), (profile_size, profile_size)], radius=28, fill=(38, 117, 255))
            except Exception:
                pd.rectangle([(0, 0), (profile_size, profile_size)], fill=(38, 117, 255))
            try:
                if MAIN_FONT_NAME:
                    init_font = ImageFont.truetype(MAIN_FONT_NAME, profile_size // 2)
                else:
                    init_font = ImageFont.load_default()
            except Exception:
                init_font = ImageFont.load_default()
            w, h = pd.textsize(initials, font=init_font)
            pd.text(((profile_size - w) / 2, (profile_size - h) / 2), initials, fill=(255, 255, 255), font=init_font)

        img.paste(prof, (profile_x, profile_y), prof)
    except Exception:
        pass

    BADGE_BG = (29, 155, 240)
    BADGE_TEXT = (255, 255, 255)
    badge_padding_x = 16
    badge_padding_y = 8
    badge_gap = 10
    badge_font_size = 26
    try:
        if MAIN_FONT_NAME:
            badge_font = ImageFont.truetype(MAIN_FONT_NAME, badge_font_size)
        else:
            badge_font = ImageFont.truetype("arial.ttf", badge_font_size)
    except Exception:
        badge_font = ImageFont.load_default()

    bot_text = bot_username or ''
    user_text = author_username or ''

    def text_size(s: str, fnt):
        try:
            w = draw.textlength(s, font=fnt)
            h = fnt.getsize(s)[1]
            return int(w), int(h)
        except Exception:
            try:
                return fnt.getsize(s)
            except Exception:
                return (len(s) * badge_font_size // 2, badge_font_size)

    bot_w, bot_h = text_size(bot_text, badge_font) if bot_text else (0, 0)
    user_w, user_h = text_size(user_text, badge_font) if user_text else (0, 0)

    bot_box_w = bot_w + 2 * badge_padding_x
    user_box_w = user_w + 2 * badge_padding_x
    badge_h = max(bot_h, user_h) + 2 * badge_padding_y

    total_w = (bot_box_w if bot_text else 0) + (badge_gap if bot_text and user_text else 0) + (user_box_w if user_text else 0)

    available_right_width = IMAGE_SIZE[0] - left_reserved - margin

    if total_w <= available_right_width:
        badges_x = IMAGE_SIZE[0] - margin - total_w
        badges_y = IMAGE_SIZE[1] - margin - badge_h

        cur_x = badges_x
        if bot_text:
            try:
                draw.rounded_rectangle([cur_x, badges_y, cur_x + bot_box_w, badges_y + badge_h], radius=badge_h // 2, fill=BADGE_BG)
            except Exception:
                draw.rectangle([cur_x, badges_y, cur_x + bot_box_w, badges_y + badge_h], fill=BADGE_BG)
            tx = cur_x + badge_padding_x
            ty = badges_y + (badge_h - bot_h) // 2
            draw.text((tx, ty), bot_text, font=badge_font, fill=BADGE_TEXT)
            cur_x += bot_box_w + (badge_gap if user_text else 0)

        if user_text:
            try:
                draw.rounded_rectangle([cur_x, badges_y, cur_x + user_box_w, badges_y + badge_h], radius=badge_h // 2, fill=BADGE_BG)
            except Exception:
                draw.rectangle([cur_x, badges_y, cur_x + user_box_w, badges_y + badge_h], fill=BADGE_BG)
            tx = cur_x + badge_padding_x
            ty = badges_y + (badge_h - user_h) // 2
            draw.text((tx, ty), user_text, font=badge_font, fill=BADGE_TEXT)
    else:
        max_box_w = max(bot_box_w if bot_text else 0, user_box_w if user_text else 0)
        badges_x = IMAGE_SIZE[0] - margin - max_box_w
        bottom_y = IMAGE_SIZE[1] - margin - badge_h
        if bot_text and user_text:
            bot_y = bottom_y - (badge_h + badge_gap)
            user_y = bottom_y
            try:
                draw.rounded_rectangle([badges_x, bot_y, badges_x + bot_box_w, bot_y + badge_h], radius=badge_h // 2, fill=BADGE_BG)
            except Exception:
                draw.rectangle([badges_x, bot_y, badges_x + bot_box_w, bot_y + badge_h], fill=BADGE_BG)
            draw.text((badges_x + badge_padding_x, bot_y + (badge_h - bot_h) // 2), bot_text, font=badge_font, fill=BADGE_TEXT)

            try:
                draw.rounded_rectangle([badges_x, user_y, badges_x + user_box_w, user_y + badge_h], radius=badge_h // 2, fill=BADGE_BG)
            except Exception:
                draw.rectangle([badges_x, user_y, badges_x + user_box_w, user_y + badge_h], fill=BADGE_BG)
            draw.text((badges_x + badge_padding_x, user_y + (badge_h - user_h) // 2), user_text, font=badge_font, fill=BADGE_TEXT)
        elif bot_text:
            try:
                draw.rounded_rectangle([badges_x, bottom_y, badges_x + bot_box_w, bottom_y + badge_h], radius=badge_h // 2, fill=BADGE_BG)
            except Exception:
                draw.rectangle([badges_x, bottom_y, badges_x + bot_box_w, bottom_y + badge_h], fill=BADGE_BG)
            draw.text((badges_x + badge_padding_x, bottom_y + (badge_h - bot_h) // 2), bot_text, font=badge_font, fill=BADGE_TEXT)
        elif user_text:
            try:
                draw.rounded_rectangle([badges_x, bottom_y, badges_x + user_box_w, bottom_y + badge_h], radius=badge_h // 2, fill=BADGE_BG)
            except Exception:
                draw.rectangle([badges_x, bottom_y, badges_x + user_box_w, bottom_y + badge_h], fill=BADGE_BG)
            draw.text((badges_x + badge_padding_x, bottom_y + (badge_h - user_h) // 2), user_text, font=badge_font, fill=BADGE_TEXT)

    if author_name:
        name_font_size = 36
        try:
            if MAIN_FONT_NAME:
                name_font = ImageFont.truetype(MAIN_FONT_NAME, name_font_size)
            else:
                name_font = ImageFont.truetype("arial.ttf", name_font_size)
        except Exception:
            name_font = ImageFont.load_default()
        name_text = f"-{author_name}"

        try:
            bbox = draw.textbbox((0, 0), name_text, font=name_font)
            name_w = bbox[2] - bbox[0]
            name_h = bbox[3] - bbox[1]
        except Exception:
            try:
                name_w = draw.textlength(name_text, font=name_font)
            except Exception:
                try:
                    name_w = name_font.getmask(name_text).size[0]
                except Exception:
                    name_w = len(name_text) * (name_font.size // 2 if hasattr(name_font, 'size') else 8)
            try:
                ascent, descent = name_font.getmetrics()
                name_h = ascent + descent
            except Exception:
                name_h = name_font.size if hasattr(name_font, 'size') else 14

        name_x = x + text_width - name_w
        name_y = y + text_height + 28
        if name_y + name_h > IMAGE_SIZE[1] - margin - badge_h - 28:
            name_y = IMAGE_SIZE[1] - margin - badge_h - name_h - 28
        name_x = max(margin, min(name_x, IMAGE_SIZE[0] - margin - name_w))
        draw.text((name_x, name_y), name_text, font=name_font, fill=TEXT_COLOR)

    output = io.BytesIO()
    output.name = "picture.png"
    img.save(output, format="PNG")
    output.seek(0)
    return output

    






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

#ПОЛУЧЕНИЕ ВРЕМЕНИ ПОСЛЕДНЕГО БОНУСА
async def get_last_bonus_time(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT last_bonus_at FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()

        if row is None or row[0] is None:
            return None

        try:
            return datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        except:
            return None
        
#ОБНОВЛЕНИЕ ВРЕМЕНИ ПОСЛЕДНЕГО БОНУСА
async def update_last_bonus_time(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute("UPDATE users SET last_bonus_at = ? WHERE id = ?", (now, user_id))
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
        await message.answer_animation(
            animation="https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExZ2JxMXc1NmJxaWdibWdnczR3N3duM3piaHo5Y3JtMndheGliYTh5diZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/FoSN2e0NW3wH1jhuOv/giphy.gif",
            caption =f"👋 Привет! Тут ты можешь собирать уникальные карточки и соревноваться с другими игроками"
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

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT visual_username FROM users WHERE id = ?", (user.id,)) as cursor:
            row = await cursor.fetchone()
            visual_username = row[0] if row else user.first_name

    #ПОДПИСЬ К ПРОФИЛЮ
    caption = (
        f"👤 Профиль : <b>{visual_username}</b>\n\n"
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

@dp.callback_query_handler(lambda c: c.data == 'my_cards')
async def my_cards_callback(query: types.CallbackQuery):
    user_id = query.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM user_cards WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            cards_count = row[0] if row else 0

    try:
        await bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
    except Exception:
        pass

    if cards_count == 0:
        await bot.send_message(
            chat_id=query.message.chat.id,
            text=(
                f"🃏 <b>Ваши карточки</b>\n\n"
                f"<blockquote>У вас всего <b>{cards_count}</b> карточек</blockquote>\n\n"
            ),
            reply_markup=keyboard_back_inventory,
            parse_mode="HTML"
        )
        await query.answer()
        return

    #получаем редкости польователя
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT DISTINCT rarity FROM user_cards WHERE user_id = ?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
            rarities = [r[0] for r in rows if r[0]]

    #клавиши редкостей
    kb = types.InlineKeyboardMarkup()
    for r in rarities:
        kb.add(types.InlineKeyboardButton(rarity_display(r), callback_data=f"cards_rarity:{r}"))

    kb.add(types.InlineKeyboardButton("‹ Назад", callback_data="back_inventory"))

    await bot.send_message(
        chat_id=query.message.chat.id,
        text=(
            f"🃏 <b>Ваши карточки</b>\n\n"
            f"<blockquote>У вас всего <b>{cards_count}</b> карточек</blockquote>"
        ),
        reply_markup=kb,
        parse_mode="HTML"
    )
    await query.answer()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('cards_rarity:'))
async def cards_rarity_callback(query: types.CallbackQuery):
    user_id = query.from_user.id
    rarity = query.data.split(":", 1)[1]

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, filename, created_at FROM user_cards WHERE user_id = ? AND rarity = ? ORDER BY created_at",
            (user_id, rarity)
        ) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await query.answer("У вас нет карточек этой редкости", show_alert=True)
        return

    kb = types.InlineKeyboardMarkup()
    for idx, (card_id, filename, created_at) in enumerate(rows, start=1):
        title = filename
        jpg_path = os.path.join(PANCHAN_PATH, rarity, filename)
        json_path = os.path.splitext(jpg_path)[0] + '.json'
        try:
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    title = metadata.get('title', filename)
        except Exception:
            pass

        label = f"{idx}. {title}"
        # callback по id карточки
        kb.add(types.InlineKeyboardButton(label, callback_data=f"card_info:{card_id}"))

    kb.add(types.InlineKeyboardButton("‹ Назад", callback_data="back_inventory"))

    try:
        await bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
    except Exception:
        pass

    await bot.send_message(
        chat_id=query.message.chat.id,
        text=f"🃏 <b>{rarity_display(rarity)} — Ваши карточки</b>\n\nВыберите карточку:",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await query.answer()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('card_info:'))
async def card_info_callback(query: types.CallbackQuery):
    user_id = query.from_user.id
    try:
        card_id = int(query.data.split(':', 1)[1])
    except Exception:
        await query.answer("Неверный идентификатор карточки", show_alert=True)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT filename, rarity, points, coins, created_at FROM user_cards WHERE id = ? AND user_id = ?", (card_id, user_id)) as cursor:
            row = await cursor.fetchone()

    if not row:
        await query.answer("Карточка не найдена", show_alert=True)
        return

    filename, rarity, pts, cns, created_at = row
    jpg_path = os.path.join(PANCHAN_PATH, rarity, filename)
    json_path = os.path.splitext(jpg_path)[0] + '.json'

    metadata = {}
    try:
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
    except Exception:
        metadata = {}

    title = metadata.get('title', 'Без названия')
    description = metadata.get('description', '')

    created_str = str(created_at)
    try:
        dt = datetime.datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=datetime.timezone.utc).astimezone(MSK)
        created_str = dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        pass

    caption = (
        f"<b>{title}</b>\n{description}\n\n"
        f"⭐ Редкость: <b>{rarity_display(rarity)}</b>\n"
        f"🏷 Цена: Очки <b>{pts}</b>, Монеты <b>{cns}</b>\n"
        f"📥 Получено: <b>{created_str}</b>"
    )

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("‹ Назад", callback_data=f"back_to_cards:{rarity}"))
    kb.add(types.InlineKeyboardButton("‹ Редкости", callback_data="my_cards"))

    try:
        await bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
    except Exception:
        pass

    if os.path.exists(jpg_path):
        try:
            with open(jpg_path, 'rb') as photo:
                await bot.send_photo(chat_id=query.message.chat.id, photo=photo, caption=caption, parse_mode='HTML', reply_markup=kb)
        except Exception:
            await bot.send_message(chat_id=query.message.chat.id, text=caption, parse_mode='HTML', reply_markup=kb)
    else:
        await bot.send_message(chat_id=query.message.chat.id, text=caption, parse_mode='HTML', reply_markup=kb)

    await query.answer()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('back_to_cards:'))
async def back_to_cards_callback(query: types.CallbackQuery):
    user_id = query.from_user.id
    rarity = query.data.split(':', 1)[1]

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, filename, created_at FROM user_cards WHERE user_id = ? AND rarity = ? ORDER BY created_at", (user_id, rarity)) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await query.answer("У вас нет карточек этой редкости", show_alert=True)
        return

    kb = types.InlineKeyboardMarkup()
    for idx, (card_id, filename, created_at) in enumerate(rows, start=1):
        title = filename
        jpg_path = os.path.join(PANCHAN_PATH, rarity, filename)
        json_path = os.path.splitext(jpg_path)[0] + '.json'
        try:
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    title = metadata.get('title', filename)
        except Exception:
            pass
        kb.add(types.InlineKeyboardButton(f"{idx}. {title}", callback_data=f"card_info:{card_id}"))

    kb.add(types.InlineKeyboardButton("‹ Назад", callback_data="back_inventory"))

    try:
        await bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
    except Exception:
        pass

    await bot.send_message(chat_id=query.message.chat.id, text=f"🃏 <b>{rarity_display(rarity)} — Ваши карточки</b>\n\nВыберите карточку:", reply_markup=kb, parse_mode='HTML')
    await query.answer()

@dp.callback_query_handler(lambda c: c.data == 'back_inventory')
async def back_inventory_callback(query: types.CallbackQuery):
    user = query.from_user
    user_id = user.id

    try:
        await bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
    except Exception:
        pass

    await add_user(user_id=user.id, username=user.username, first_name=user.first_name)

    user_visual_id = await get_user_visual_id(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT visual_username FROM users WHERE id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            visual_username = row[0] if row else user.first_name

    points, coins = await get_user_balance(user_id)

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM user_cards WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            cards_count = row[0] if row else 0

    caption = (
        f"👤 Профиль : <b>{visual_username}</b>\n\n"
        f"🔎 ID: {user_visual_id}\n"
        f"💰 Монеты: <b>{coins}</b>\n"
        f"⭐ Очки: <b>{points}</b>\n"
        f"🃏 Коллекция: <b>{cards_count}</b> карточек\n"
    )

    try:
        photos = await bot.get_user_profile_photos(user_id)
        if photos.total_count == 0:
            await bot.send_message(chat_id=query.message.chat.id, text=caption, reply_markup=keyboard_profile, parse_mode='HTML')
        else:
            file_id = photos.photos[0][-1].file_id
            await bot.send_photo(chat_id=query.message.chat.id, photo=file_id, caption=caption, reply_markup=keyboard_profile, parse_mode='HTML')
    except Exception:
        await bot.send_message(chat_id=query.message.chat.id, text=caption, reply_markup=keyboard_profile, parse_mode='HTML')

    await query.answer()

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

    # читаем метку редкости для вывода
    rarity_label = rarity_display(metadata.get("rarity"))

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
        f"⭐ Редкость: <b>{rarity_label}</b>\n"
        f"🏆 Очки: +<b>{pts_add} [{new_points}]</b>\n"
        f"💰 Монеты: +<b>{cns_add} [{new_coins}]</b>"
    )

    if already_owned:
        caption = (
            f"🌟 Карточка — <b>{metadata.get('title')}</b> уже была у вас\n\n"
            f"⭐ Редкость: <b>{rarity_label}</b>\n"
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

@dp.message_handler(commands=['name'])
async def change_name_command(message: types.Message):
    user = message.from_user
    args = message.get_args()

    if not args:
        return await message.answer("<b>Использование</b>\n<blockquote>Отправьте /name [имя]\nПример: /name SharoPidr_Gandon</blockquote>", parse_mode="HTML")
    
    if len(args.strip()) > 30:
        return await message.answer("❌<b>Ошибка</b>\n<blockquote>Имя не должно превышать 30 символов</blockquote>", parse_mode="HTML")

    new_name = args.strip()

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM users WHERE visual_username = ? AND id != ?", (new_name, user.id)) as cursor:
            row = await cursor.fetchone()
        
        if row:
            return await message.answer(f"❌<b>Ошибка</b>\n<blockquote>Ник <b>Имя «{new_name}»</b> уже кем то занято</blockquote>", parse_mode="HTML")
        
        await db.execute("UPDATE users SET visual_username = ? WHERE id = ?", (new_name, user.id))
        await db.commit()

    await message.answer(f"✅<b>Успешно</b> \n<blockquote>Ваше имя было изменено на <b>«{new_name}»</b></blockquote>", parse_mode="HTML")


@dp.message_handler(commands=['bonus'])
async def bonus_command(message: types.Message):
    user_id = message.from_user.id
    chat_type = message.chat.type

    last_time = await get_last_bonus_time(user_id)
    now = datetime.datetime.utcnow()

    if last_time is not None:
        diff = now - last_time
        cooldown = 60 * 60 * 12 #12 ЧАСОВ
        if diff.total_seconds() < cooldown:
            wait = int(cooldown - diff.total_seconds())
            wait_hours = wait // 3600
            wait_minutes = (wait % 3600) // 60
            wait_seconds = wait % 60
            return await message.reply(
                f"<b>Вы не можете сейчас получить бонус</b>\n\n"
                f"🕛 Попробуйте через <b>{wait_hours}ч. {wait_minutes}мин. {wait_seconds}сек.</b>",
                parse_mode="HTML"
            )

    if chat_type != 'private':
        await message.answer("🎁<b>Использование</b>\n<blockquote>Команда доступна только в ЛС с ботом</blockquote>", parse_mode="HTML")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT have_bonus FROM users WHERE id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            have_bonus = row[0] if row and row[0] is not None else 0

    if have_bonus == 1:
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

        # читаем метку редкости для вывода
        rarity_label = rarity_display(metadata.get("rarity"))

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
            f"🎁 <b>Бонусная карточка</b> — <b>{metadata.get('title', 'Без названия')}</b>\n\n"
            f"{metadata.get('description', '')}\n\n"
            f"⭐ Редкость: <b>{rarity_label}</b>\n"
            f"🏆 Очки: +<b>{pts_add} [{new_points}]</b>\n"
            f"💰 Монеты: +<b>{cns_add} [{new_coins}]</b>"
        )

        if already_owned:
            caption = (
                f"🌟 Бонусная карточка — <b>{metadata.get('title')}</b> уже была у вас\n\n"
                f"⭐ Редкость: <b>{rarity_label}</b>\n"
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

            #обновляем last_bonus_at
            await update_last_bonus_time(user_id)

        except Exception:
            logging.exception("Ошибка при отправке бонусной карточки")
            return await message.answer("❌ Ошибка при выдаче бонусной карточки. Попробуйте позже.")
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📺Подписаться", url="https://t.me/gandonioffical"))
    kb.add(types.InlineKeyboardButton("📺Подписаться", url="https://t.me/pidorasiofficial"))
    kb.add(types.InlineKeyboardButton("🔗Перейти", url="https://t.me/EBU_MANGU_BOT?start=ref"))
    kb.add(types.InlineKeyboardButton("✅Проверить", callback_data="verify"))

    await bot.send_message(
        text=("<b>📒Задания</b>\n"
              "<blockquote>Выполните все задания чтобы получить бонус</blockquote>\n"),
        parse_mode="HTML",
        chat_id=message.chat.id,
        reply_markup=kb
    )

@dp.callback_query_handler(lambda c: c.data == 'verify')
async def process_verify_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    channels = {
        "МЕСТО ДЛЯ РЕКЛАМЫ 1": "gandonioffical", #ЗАМЕНИТЕ НА СВОИ КАНАЛЫ (БОТ ДОЛЖЕН БЫТЬ АДМИНИСТРАТОРОМ В КАНАЛАХ)
        "МЕСТО ДЛЯ РЕКЛАМЫ 2": "pidorasiofficial" #ЗАМЕНИТЕ НА СВОИ КАНАЛЫ (БОТ ДОЛЖЕН БЫТЬ АДМИНИСТРАТОРОМ В КАНАЛАХ)
    }

    not_subscribed = []
    access_errors = []

    for name, channel in channels.items():
        chat_id = channel if channel.startswith('@') else f"@{channel}"
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_subscribed.append(name)
        except Exception as e:
            logging.exception(f"Ошибка при проверке канала {channel}: {e}")
            access_errors.append(name)

    if not_subscribed or access_errors:
        parts = ["❌ <b>Ошибка проверки заданий</b>"]
        if not_subscribed:
            parts.append(f"Вы не подписаны на каналы: {', '.join(not_subscribed)}")
        if access_errors:
            parts.append(f"Не удалось проверить: {', '.join(access_errors)}")

        text = "\n".join(parts)

        await bot.answer_callback_query(
            callback_query.id,
            text=text,
            show_alert=True
        )
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT have_bonus FROM users WHERE id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            have_bonus = row[0] if row else 0

        if have_bonus == 1:
            await bot.answer_callback_query(
                callback_query.id,
                text="ℹ️ У вас уже есть бонусная карточка.",
                show_alert=True
            )
            return

        await db.execute("UPDATE users SET have_bonus = 1 WHERE id = ?", (user_id,))
        await db.commit()

    await bot.send_message(
        callback_query.message.chat.id,
        text="🎁<b>Бонус получен</b>\n<blockquote>Вы можете снова получить свою бонусную карточку</blockquote>",
        parse_mode="HTML"
    )















#СТИКЕРЫ ДЛЯ РАССЫЛКИ
async def scheduler():
    while True:
        now = datetime.now(MSK)
        target_minute = random.randint(0, 23 * 60 + 59)
        target_time = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=target_minute)

        if target_time <= now:
            target_time += timedelta(days=1)

        wait_seconds = (target_time - now).total_seconds()
        print(f"СТИКЕРЫ ОТПРАВЯТСЯ В {target_time}")

        await asyncio.sleep(wait_seconds)
        await send_daily_sticker()


async def send_daily_sticker():
    sticker = random.choice(STICKERS)

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id FROM users")
        rows = await cursor.fetchall()
    for (user_id,) in rows:
        try:
            await bot.send_sticker(user_id, sticker)
        except:
            pass

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT chat_id FROM chats")
        rows = await cursor.fetchall()
    for (chat_id,) in rows:
        try:
            await bot.send_sticker(chat_id, sticker)
        except:
            pass

#ТЕСТ
@dp.message_handler(commands=['rndsticker'])
async def test_command(message: types.Message):
    sticker = random.choice(STICKERS)
    await message.answer_sticker(sticker)

#ТЕСТ2
@dp.message_handler(Regexp(r'^панчан цитата(?:\s+.+)?$'))
async def picture_command(message: types.Message):
    m = re.match(r'^(?:панчан цитата)(?:\s+(.*))?$', message.text or '', re.IGNORECASE | re.DOTALL)
    args = (m.group(1) or '').strip() if m else ''
    if not args:
        await message.reply("💬<b>Как использовать цитаты?</b>\n\n"
                            "<b>Варианты</b>\n\n"
                            "<blockquote>Отправьте <i>панчан цитата</i> в ответ на чьё то сообщение</blockquote>\n"
                            "<blockquote>Или отправьте <i>панчан цитата [ваш текст]</i></blockquote>\n\n",
                            parse_mode="HTML"
                            )
        return

    if len(args) > PICTURE_MAX_CHARS:
        args = args[:PICTURE_MAX_CHARS - 3].rstrip() + '...'


    user = message.from_user
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    author_username = f"@{user.username}" if user.username else ''

    author_image = None
    try:
        photos = await bot.get_user_profile_photos(user.id)
        if photos and photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            f = await bot.get_file(file_id)
            bio = io.BytesIO()
            await bot.download_file(f.file_path, bio)
            bio.seek(0)
            author_image = Image.open(bio)
    except Exception:
        pass

    try:
        image = create_picture(args, author_name=full_name, author_username=author_username, bot_username=BOT_USERNAME or '', author_image=author_image)
        image.seek(0)
        await message.answer_photo(photo=types.InputFile(image, filename="picture.png"))
    except Exception:
        logging.exception("Ошибка при выполнении /quote")



#ИНИТ
async def on_startup(_):
    await init_db()
    # get bot username for badges
    try:
        me = await bot.get_me()
        global BOT_USERNAME
        BOT_USERNAME = f"@{me.username}" if me and me.username else (me.first_name if me else "")
    except Exception:
        BOT_USERNAME = None

    asyncio.create_task(scheduler())
    logging.info("✅УСПЕШНАЯ ИНИЦИАЛИЗАЦИЯ✅")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
