# -*- coding: utf-8 -*-
"""
🎁 Gift To
Админ-розыгрыши + ежедневный 777-спин + ВСЁ СТАРОЕ
"""
import asyncio
import logging
import sqlite3
import aiosqlite
import random
import time
import re
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, CallbackQuery, BotCommand, BotCommandScopeDefault
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode, ChatType
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from aiogram.utils.markdown import hbold, hcode, hlink, hitalic
from collections import defaultdict
from typing import Dict, List, Optional, Any, Tuple
# ========= К О Н Ф И Г =========
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [
    int(os.getenv("ADMIN_ID_1")),
    int(os.getenv("ADMIN_ID_2"))
]
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
GROUP_ID = int(os.getenv("GROUP_ID"))
# =================================
COOLDOWN = 1 # Изменено на 15 секунд
MINI_GAME_COOLDOWN = 15 # 30 секунд КД для мини-игр
DAILY_SPINS = 0
DAILY_POINTS = 150
CACHE_TTL = 60
REFS_FOR_SPIN = 2 # Нужно 2 реферала для одного двухдневного спина
TWO_DAY_SPIN_INTERVAL = timedelta(days=1)
TWO_DAY_SPIN_POINTS = 10 # Только 10 очков за выигрыш
USER_LEVELS = {
    0: {"name": "🌱 Нов", "bonus": 0},
    100: {"name": "🎲 Игрок", "bonus": 1},
    500: {"name": "♦️ Про", "bonus": 3},
    1500: {"name": "👑 Мастер", "bonus": 5},
    5000: {"name": "🔥 Легенда", "bonus": 10},
}
WIN_COMBOS = {
    "🛩️ 🛩️ 🛩️": {"name": "ТРИ САМОЛЁТА", "prize": "💎 Самолёт", "points": 1000, "rarity": "🔴 LEGENDARY"},
    "BAR BAR BAR": {"name": "ТРИ BAR", "prize": "❤️ Сердце", "points": 500, "rarity": "🟠 EPIC"},
    "7️⃣ 7️⃣ 7️⃣": {"name": "ТРИ СЕМЁРКИ", "prize": "🥈 Серебро", "points": 300, "rarity": "🟡 RARE"},
    "3xBAR 3xBAR 3xBAR": {"name": "ТРИ 3xBAR", "prize": "🥇 Золотце", "points": 200, "rarity": "🟢 UNCOMMON"},
    "2xBAR 2xBAR 2xBAR": {"name": "ТРИ 2xBAR", "prize": "🥉 Медь", "points": 150, "rarity": "🔵 COMMON"},
    "1xBAR 1xBAR 1xBAR": {"name": "ТРИ 1xBAR", "prize": "🌹 Роза", "points": 100, "rarity": "⚪ COMMON"},
}
SLOT_SYMBOLS = ["🛩️", "BAR", "7️⃣", "3xBAR", "2xBAR", "1xBAR", "💎", "🔔", "🍒", "🍀"]
MINI_GAMES = {
    "dice": {"emoji": "🎲", "name": "Кубик", "win_condition": "custom"}, # Будет задаваться админом
    "dart": {"emoji": "🎯", "name": "Дартс", "win_condition": "custom"},
    "basketball": {"emoji": "🏀", "name": "Баскетбол", "win_condition": "custom"},
    "bowling": {"emoji": "🎳", "name": "Боулинг", "win_condition": "custom"},
    "football": {"emoji": "⚽", "name": "Футбол", "win_condition": "custom"},
    "slot": {"emoji": "🎰", "name": "Рулетка", "win_condition": "custom"}, # Добавлена рулетка
}
PRIZES = {
    "gifts": [
        {"id": "bear_15", "name": "🧸 Мишка за 15 ⭐"},
        {"id": "heart_50", "name": "❤️ Сердце за 50 ⭐"},
        {"id": "rose_100", "name": "🌹 Роза за 100 ⭐"},
        {"id": "silver_300", "name": "🥈 Серебро за 300 ⭐"},
        {"id": "gold_500", "name": "🥇 Золото за 500 ⭐"},
        {"id": "diamond_1000", "name": "💎 Алмаз за 1000 ⭐"},
    ],
    "nfts": [
        {"id": "nft_rare", "name": "🔴 Редкий NFT"},
        {"id": "nft_epic", "name": "🟠 Эпический NFT"},
        {"id": "nft_legendary", "name": "🟡 Легендарный NFT"},
    ]
}
SHOP_ITEMS = {
    "spins_10": {"name": "1 спин", "price": 200, "type": "spins", "value": 10},
    "spins_50": {"name": "5 спинов", "price": 800, "type": "spins", "value": 50},
    "x2_1h": {"name": "2x множитель (1 ч)", "price": 500, "type": "mult", "value": 2, "duration": 3600},
}
# ========= Л О Г И =========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()]
)
log = logging.getLogger(__name__)
# ========= К Е Ш =========
user_cache = defaultdict(dict)
user_cooldowns = defaultdict(float)
user_mini_cooldowns = defaultdict(float) # КД для мини-игр
# ========= Б А З А =========
class Database:
    def __init__(self, name: str = "casino.db"):
        self.name = name
    async def init(self):
        async with aiosqlite.connect(self.name) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS users(
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                referral_count INTEGER DEFAULT 0,
                spins_count INTEGER DEFAULT 0,
                wins_count INTEGER DEFAULT 0,
                total_points INTEGER DEFAULT 0,
                daily_spins INTEGER DEFAULT 15,
                last_daily_bonus TIMESTAMP,
                last_spin TIMESTAMP,
                last_two_day_spin TIMESTAMP,
                multiplier_end TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                free_spin_used INTEGER DEFAULT 0
            )""")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS achievements(
                user_id INTEGER,
                achievement TEXT,
                earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(user_id, achievement)
            )""")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS wins_history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                combination TEXT,
                prize TEXT,
                points INTEGER,
                chat_id INTEGER,
                message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referral_id INTEGER UNIQUE,
                earned_points INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS shop_purchases(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                item_id TEXT,
                price INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_games(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id INTEGER,
                game_type TEXT,
                emoji TEXT,
                win_condition TEXT,
                prize_type TEXT,
                prize_id TEXT,
                max_winners INTEGER,
                winners TEXT DEFAULT '',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ends_at TIMESTAMP,
                active INTEGER DEFAULT 1
            )""")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS settings(
                key TEXT PRIMARY KEY,
                value TEXT
            )""")
            await db.commit()
    # ===== основные CRUD =====
    async def add_user(self, user: types.User, code: str, ref: Optional[int] = None):
        async with aiosqlite.connect(self.name) as db:
            await db.execute("""
            INSERT OR IGNORE INTO users(user_id, username, full_name, referral_code, referred_by, daily_spins)
            VALUES(?,?,?,?,?,?)
            """, (user.id, user.username, user.full_name, code, ref, DAILY_SPINS))
            if ref:
                await db.execute("UPDATE users SET referral_count=referral_count+1 WHERE user_id=?", (ref,))
                await db.execute("INSERT OR IGNORE INTO referrals(referrer_id, referral_id) VALUES(?,?)", (ref, user.id))
            await db.commit()
    async def get_user(self, uid: int) -> Optional[Dict]:
        key = f"u{uid}"
        cached = user_cache.get(key)
        if cached and time.time() - cached.get("_ts", 0) < CACHE_TTL:
            return cached
        async with aiosqlite.connect(self.name) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM users WHERE user_id=?", (uid,))
            row = await cur.fetchone()
            if row:
                data = dict(row)
                data["_ts"] = time.time()
                user_cache[key] = data
                return data
        return None
    async def update_stats(self, uid: int, win: bool = False, points: int = 0, spins: int = 1):
        async with aiosqlite.connect(self.name) as db:
            # множитель
            cur = await db.execute("SELECT multiplier_end FROM users WHERE user_id=?", (uid,))
            row = await cur.fetchone()
            mult = 1
            if row and row[0]:
                if datetime.now() < datetime.fromisoformat(row[0]):
                    mult = 2
            points = points * mult
            await db.execute("""
            UPDATE users SET spins_count = spins_count + ?, daily_spins = daily_spins - ?,
            wins_count = wins_count + ?, total_points= total_points + ?, last_spin = ? WHERE user_id=?
            """, (spins, spins, int(win), points, datetime.now(), uid))
            await db.commit()
            user_cache.pop(f"u{uid}", None)
    async def update_two_day_spin(self, uid: int):
        async with aiosqlite.connect(self.name) as db:
            await db.execute("UPDATE users SET last_two_day_spin=? WHERE user_id=?", (datetime.now(), uid))
            await db.commit()
            user_cache.pop(f"u{uid}", None)
    async def reset_daily_spins(self):
        async with aiosqlite.connect(self.name) as db:
            await db.execute("UPDATE users SET daily_spins=?, free_spin_used=0", (DAILY_SPINS,))
            await db.commit()
        user_cache.clear()
    async def add_win(self, uid, combo, prize, pts, chat_id, msg_id):
        async with aiosqlite.connect(self.name) as db:
            await db.execute("""
            INSERT INTO wins_history(user_id, combination, prize, points, chat_id, message_id)
            VALUES(?,?,?,?,?,?)
            """, (uid, combo, prize, pts, chat_id, msg_id))
            await db.commit()
    async def top(self, lim: int = 100) -> List[Dict]:
        key = f"top{lim}"
        cached = user_cache.get(key)
        if cached and time.time() - cached["_ts"] < CACHE_TTL:
            return cached["data"]
        async with aiosqlite.connect(self.name) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("""
            SELECT user_id, username, full_name, wins_count, total_points FROM users
            ORDER BY total_points DESC, wins_count DESC LIMIT ?
            """, (lim,))
            rows = [dict(r) for r in await cur.fetchall()]
            user_cache[key] = {"_ts": time.time(), "data": rows}
            return rows
    # ===== админ-игры (мини-игры) =====
    async def create_admin_game(self, creator, game_type, emoji, win_condition, prize_type, prize_id, max_w):
        # Убрали duration, игра активна до заполнения победителей
        async with aiosqlite.connect(self.name) as db:
            await db.execute("""
            INSERT INTO admin_games(creator_id, game_type, emoji, win_condition, prize_type, prize_id, max_winners)
            VALUES(?,?,?,?,?,?,?)
            """, (creator, game_type, emoji, win_condition, prize_type, prize_id, max_w))
            await db.commit()
    async def get_active_admin_game(self) -> Optional[Dict]:
        async with aiosqlite.connect(self.name) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("""
            SELECT * FROM admin_games WHERE active=1 ORDER BY id DESC LIMIT 1
            """,)
            row = await cur.fetchone()
            return dict(row) if row else None
    async def add_admin_winner(self, game_id, uid) -> int:
        async with aiosqlite.connect(self.name) as db:
            cur = await db.execute("SELECT winners, max_winners FROM admin_games WHERE id=?", (game_id,))
            row = await cur.fetchone()
            if not row:
                return 0
            winners = list(map(int, filter(None, row[0].split(",")))) if row[0] else []
            if uid in winners:
                return len(winners)
            winners.append(uid)
            await db.execute("UPDATE admin_games SET winners=? WHERE id=?", (",".join(map(str, winners)), game_id))
            if len(winners) >= row[1]:
                await db.execute("UPDATE admin_games SET active=0 WHERE id=?", (game_id,))
            await db.commit()
            return len(winners)
    async def close_admin_game(self, game_id):
        async with aiosqlite.connect(self.name) as db:
            await db.execute("UPDATE admin_games SET active=0 WHERE id=?", (game_id,))
            await db.commit()
    # ===== ежедневный 777 =====
    async def use_free_spin(self, uid) -> bool:
        u = await self.get_user(uid)
        if u.get("free_spin_used"):
            return False
        async with aiosqlite.connect(self.name) as db:
            await db.execute("UPDATE users SET free_spin_used=1 WHERE user_id=?", (uid,))
            await db.commit()
            user_cache.pop(f"u{uid}", None)
        return True
    # ===== тех.работы =====
    async def get_maintenance_end(self) -> Optional[datetime]:
        async with aiosqlite.connect(self.name) as db:
            cur = await db.execute("SELECT value FROM settings WHERE key='maintenance_end'")
            row = await cur.fetchone()
            if row and row[0]:
                return datetime.fromisoformat(row[0])
            return None
    async def set_maintenance_end(self, end_time: datetime):
        async with aiosqlite.connect(self.name) as db:
            await db.execute("""
            INSERT OR REPLACE INTO settings(key, value) VALUES('maintenance_end', ?)
            """, (end_time.isoformat(),))
            await db.commit()
    async def clear_maintenance(self):
        async with aiosqlite.connect(self.name) as db:
            await db.execute("DELETE FROM settings WHERE key='maintenance_end'")
            await db.commit()
db = Database()
# ========= У Т И Л И =========
def fmt_num(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)
def level_info(points: int) -> Dict:
    for thr, data in sorted(USER_LEVELS.items(), reverse=True):
        if points >= thr:
            return data
    return USER_LEVELS[0]
def gen_ref_code(uid: int) -> str:
    return f"GT_{uid}_{random.randint(1000,9999)}"
def get_prize_name(prize_type, prize_id):
    if prize_type == "gifts":
        for p in PRIZES["gifts"]:
            if p["id"] == prize_id:
                return p["name"]
    elif prize_type == "nfts":
        for p in PRIZES["nfts"]:
            if p["id"] == prize_id:
                return p["name"]
    return "Неизвестный приз"
def format_remaining_time(remaining: timedelta) -> str:
    days = remaining.days
    hours, remainder = divmod(remaining.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    time_str = ""
    if days > 0:
        time_str += f"{days} дней "
    if hours > 0:
        time_str += f"{hours} часов "
    if minutes > 0:
        time_str += f"{minutes} минут "
    if seconds > 0 or not time_str:
        time_str += f"{seconds} секунд"
    return time_str.strip()
# ========= К Л А В И А Т У Р Ы =========
class KB:
    @staticmethod
    def main(user_data: Dict, has_active_game: bool, is_admin: bool = False) -> types.InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        spins = user_data.get("daily_spins", 0)
        pts = user_data.get("total_points", 0)
        if has_active_game:
            b.button(text="🎮 Мини-игра", callback_data="mini_game")
        b.button(text="👥 Рефералы", callback_data="ref")
        b.button(text="🏆 Топ-100", callback_data="top")
        b.button(text=f"🏪 Магазин (💎{fmt_num(pts)})", callback_data="shop")
        b.button(text="📈 Статистика", callback_data="stats")
        b.button(text="📞 Поддержка", callback_data="support")
        b.button(text="🎁 ежедневный 777-спин", callback_data="two_day_spin") # Изменено на двухдневный
        if is_admin:
            b.button(text="🔧 Админ-панель", callback_data="admin_panel")
        b.adjust(2)
        return b.as_markup()
    @staticmethod
    def back() -> types.InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="⬅️ Меню", callback_data="menu")
        return b.as_markup()
    @staticmethod
    def admin() -> types.InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="📊 Статистика", callback_data="a_stats")
        b.button(text="🔧 Сбросить спины", callback_data="a_reset")
        b.button(text="🎮 Создать мини-игру",callback_data="a_new_mini_game")
        b.button(text="📢 Рассылка", callback_data="a_broadcast")
        b.button(text="💰 Начислить спины", callback_data="a_add_spins")
        b.button(text="📊 Топ игроков", callback_data="a_top_players")
        b.button(text="🛠 Начать тех.работы", callback_data="a_maintenance_start")
        b.button(text="🗑 Удалить все в группе", callback_data="a_delete_all_group")
        b.adjust(2)
        return b.as_markup()
    @staticmethod
    def mini_game_start(game: Dict) -> types.InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="🎲 Бросить", callback_data="play_mini_game")
        b.button(text="⬅️ Меню", callback_data="menu")
        b.adjust(1)
        return b.as_markup()
    @staticmethod
    def select_game_type() -> types.InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        for code, info in MINI_GAMES.items():
            b.button(text=info["name"], callback_data=f"select_game_{code}")
        b.adjust(2)
        return b.as_markup()
    @staticmethod
    def select_prize_type() -> types.InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="Подарки", callback_data="prize_gifts")
        b.button(text="NFT", callback_data="prize_nfts")
        b.adjust(2)
        return b.as_markup()
    @staticmethod
    def select_prize(prize_type: str) -> types.InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        for p in PRIZES[prize_type]:
            b.button(text=p["name"], callback_data=f"select_prize_{prize_type}_{p['id']}")
        b.adjust(1)
        return b.as_markup()
    @staticmethod
    def shop_items(points: int) -> types.InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        for item_id, item in SHOP_ITEMS.items():
            can = "✅" if points >= item["price"] else "❌"
            b.button(text=f"{can} {item['name']} – 💎{fmt_num(item['price'])}", callback_data=f"buy_{item_id}")
        b.button(text="⬅️ Меню", callback_data="menu")
        b.adjust(1)
        return b.as_markup()
    @staticmethod
    def join_mini_game() -> types.InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="🎮 Участвовать в мини-игре", callback_data="mini_game")
        b.adjust(1)
        return b.as_markup()
# ========= И Г Р О В О Й Д В И Ж О К =========
class Engine:
    @staticmethod
    def spin() -> tuple[str, bool, Optional[Dict]]:
        sym = random.choices(SLOT_SYMBOLS, k=3)
        combo = " ".join(sym)
        for c, data in WIN_COMBOS.items():
            if combo == c:
                if random.random() < 0.02: # 2 % шанс легенды
                    return combo, True, data
        return combo, False, None
engine = Engine()
# ========= M I D D L E W A R E =========
class MaintenanceMiddleware:
    async def __call__(self, handler, event, data):
        if isinstance(event, (Message, CallbackQuery)):
            uid = event.from_user.id
            if uid in ADMIN_IDS:
                return await handler(event, data)
            maintenance_end = await db.get_maintenance_end()
            if maintenance_end and datetime.now() < maintenance_end:
                txt = f"🛠 Бот на тех.работах до {maintenance_end.strftime('%H:%M %d.%m.%Y')} МСК. Пожалуйста, подождите."
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer(txt, show_alert=True)
                    except:
                        pass
                else:
                    await event.reply(txt)
                return
        return await handler(event, data)
class SubMiddleware:
    async def __call__(self, handler, event, data):
        bot: Bot = data["bot"]
        if isinstance(event, (Message, CallbackQuery)):
            uid = event.from_user.id
            if uid in ADMIN_IDS:
                return await handler(event, data)
            try:
                mem = await bot.get_chat_member(CHANNEL_USERNAME, uid)
                if mem.status in {"member", "administrator", "creator"}:
                    return await handler(event, data)
            except TelegramBadRequest as e:
                if "member list is inaccessible" in str(e):
                    log.warning("Channel member list inaccessible. Ensure bot is admin in channel.")
                else:
                    log.exception(e)
            except Exception as e:
                log.exception(e)
            await self._prompt(event, bot)
            return
        return await handler(event, data)
    async def _prompt(self, event, bot: Bot):
        b = InlineKeyboardBuilder()
        ch = CHANNEL_USERNAME.replace("@", "")
        b.button(text="📢 Подписаться", url=f"https://t.me/{ch}")
        b.button(text="✅ Проверить", callback_data="check_sub")
        txt = f"❌ {hbold('ДОСТУП ЗАКРЫТ')}\nПодпишитесь на {hlink('канал', f'https://t.me/{ch}')}"
        try:
            if isinstance(event, CallbackQuery):
                await event.message.edit_text(txt, reply_markup=b.as_markup())
            else:
                await event.answer(txt, reply_markup=b.as_markup())
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass # Игнорируем, если сообщение не изменилось
            else:
                log.exception(e)
class SpamMiddleware:
    def __init__(self, cd: float = COOLDOWN):
        self.cd = cd
    async def __call__(self, handler, event, data):
        if isinstance(event, CallbackQuery):
            uid = event.from_user.id
            if time.time() < user_cooldowns.get(uid, 0):
                try:
                    await event.answer("⏳ Подождите 1 с", show_alert=False)
                except TelegramBadRequest as e:
                    if "query is too old" in str(e):
                        pass
                    else:
                        raise
                return
            user_cooldowns[uid] = time.time() + self.cd
        return await handler(event, data)
class MiniGameCooldownMiddleware:
    async def __call__(self, handler, event, data):
        if isinstance(event, CallbackQuery) and event.data == "play_mini_game":
            uid = event.from_user.id
            if time.time() < user_mini_cooldowns.get(uid, 0):
                try:
                    await event.answer("⏳ Подождите 15 секунд перед следующим броском", show_alert=False)
                except TelegramBadRequest as e:
                    if "query is too old" in str(e):
                        pass
                    else:
                        raise
                return
            user_mini_cooldowns[uid] = time.time() + MINI_GAME_COOLDOWN
        return await handler(event, data)
# ========= R O U T E R =========
rt = Router()
group_messages = set()
# --------- старт ---------
@rt.message(CommandStart())
async def start(m: Message, bot: Bot, command: CommandStart):
    user = m.from_user
    ref_code = gen_ref_code(user.id)
    ref_by = None
    arg = command.args
    if arg and arg.startswith("GT_"):
        try:
            rid = int(arg.split("_")[1])
            if rid != user.id: # Защита от self-ref
                await db.add_user(types.User(id=rid, is_bot=False, first_name="Unknown", username=None), gen_ref_code(rid)) # Добавляем referrer если нет
                ref_by = rid
        except Exception as e:
            log.exception(e)
            pass
    await db.add_user(user, ref_code, ref_by)
    if ref_by:
        user_cache.pop(f"u{ref_by}", None)
        ud_ref = await db.get_user(ref_by)
        if ud_ref["referral_count"] % REFS_FOR_SPIN == 0:
            await bot.send_message(ref_by, f"🎉 Вы пригласили {ud_ref['referral_count']} рефералов! Доступен новый ежедневный спин в меню!")
    ud = await db.get_user(user.id)
    active_game = await db.get_active_admin_game()
    is_admin = user.id in ADMIN_IDS
    try:
        await m.answer_sticker("CAACAgIAAxkBAAEK6vVlZAKx2jX5xE5U4VWv1H4AAb8jTQACJAADi_ruB60rH8cLe8O0MwQ")
    except:
        pass
    welcome_txt = f"🎁 {hbold('GIFT TO – ULTRA MAXIMUM!')}\n\n" \
                  f"🎉 {hbold('ДОБРО ПОЖАЛОВАТЬ В МИР АЗАРТА И ПРИЗОВ!')} 🚀\n\n" \
                  f"Здесь вы можете крутить барабан, участвовать в мини-играх, зарабатывать очки и выигрывать крутые призы!\n\n" \
                  f"{hbold('📜 ПРАВИЛА ИГРЫ:')}\n" \
                  f"• Крутите ежедневный 777-спин за рефералов или каждый день!\n" \
                  f"• Участвуйте в мини-играх от админа – бросает бот, вы только нажимаете!\n" \
                  f"• Приглашайте друзей за бонусы и спины!\n" \
                  f"• Обновление спинов в 00:00 МСК.\n\n" \
                  f"{hbold('🎁 ЧТО ВАС ЖДЕТ:')}\n" \
                  f"• Ежедневные бонусы и уровни от Новичка до Легенды!\n" \
                  f"• Магазин для покупки спинов и множителей!\n" \
                  f"• Топ-100 игроков и статистика!\n\n" \
                  f"{hitalic('Готовы к удаче? Выберите действие ниже!')} 💥"
    await m.answer(welcome_txt, reply_markup=KB.main(ud, bool(active_game), is_admin), parse_mode=ParseMode.HTML)
# --------- подписка ---------
@rt.callback_query(F.data == "check_sub")
async def check_sub(c: CallbackQuery, bot: Bot):
    try:
        mem = await bot.get_chat_member(CHANNEL_USERNAME, c.from_user.id)
        if mem.status in {"member", "administrator", "creator"}:
            await c.answer("✅ Подписка подтверждена! Добро пожаловать!", show_alert=True)
            ud = await db.get_user(c.from_user.id)
            active_game = await db.get_active_admin_game()
            is_admin = c.from_user.id in ADMIN_IDS
            await c.message.edit_text("🎁 Доступ открыт! Выберите действие:", reply_markup=KB.main(ud, bool(active_game), is_admin))
        else:
            await c.answer("❌ Вы не подписаны! Подпишитесь на канал.", show_alert=True)
    except TelegramBadRequest as e:
        if "member list is inaccessible" in str(e):
            await c.answer("❌ Канал недоступен для проверки. Обратитесь к админу.", show_alert=True)
    except Exception as e:
        log.exception(e)
        await c.answer("❌ Ошибка проверки! Попробуйте позже.", show_alert=True)
# --------- двухдневный 777-спин (требует 2 рефералов или 2 дня) ---------
@rt.callback_query(F.data == "two_day_spin")
async def two_day_spin(c: CallbackQuery, bot: Bot):
    uid = c.from_user.id
    ud = await db.get_user(uid)
    now = datetime.now()
    last_spin = ud.get("last_two_day_spin")
    can_spin = False
    condition_message = "🚨 Чтобы использовать ежедневный спин, пригласите 2 друзей или подождите 1день!"
    remaining_message = ""
    if ud["referral_count"] >= REFS_FOR_SPIN:
        can_spin = True
        condition_message = "✅ Благодаря 2 рефералам, спин доступен! Удачи! 🎉"
    elif last_spin:
        last_spin_dt = datetime.fromisoformat(last_spin)
        if now - last_spin_dt >= TWO_DAY_SPIN_INTERVAL:
            can_spin = True
            condition_message = "✅ Прошел 1 день, спин доступен! Крутим! 🔥"
        else:
            remaining = TWO_DAY_SPIN_INTERVAL - (now - last_spin_dt)
            remaining_message = f"⏳ Спин доступен через {format_remaining_time(remaining)}."
            await c.answer(remaining_message + " Или пригласите 2 друзей!", show_alert=True)
            await bot.send_message(uid, condition_message)
            return
    else: # Первый раз
        if ud["referral_count"] >= REFS_FOR_SPIN:
            can_spin = True
            condition_message = "✅ Благодаря 2 рефералам, спин доступен! Удачи! 🎉"
        else:
            await c.answer("❌ Пригласите 2 друзей для первого спина!", show_alert=True)
            await bot.send_message(uid, condition_message)
            return
    if not can_spin:
        await c.answer("❌ Спин недоступен.", show_alert=True)
        await bot.send_message(uid, condition_message)
        return
    await bot.send_message(uid, condition_message)
    await c.answer("🎲 Кручу 777...", show_alert=False)
    msg = await bot.send_dice(c.from_user.id, emoji="🎰")
    await asyncio.sleep(4)
    value = msg.dice.value
    win = value == 42 # 42 = 777 на слоте (проверьте значение для 777, для 🎰 777 это 42)
    if win:
        prize = "🧸 Мишка за 15 ⭐"
        await db.update_stats(uid, win=True, points=TWO_DAY_SPIN_POINTS, spins=0)
        win_txt = f"🎉🎉🎉 {hbold('БОЛЬШАЯ ПОБЕДА!!!')}\n\n777 ВЫПАЛО! Вы выиграли {prize}! 💥\n\n+10 очков добавлено!\nОткройте ЛС админу для получения приза. Ура! 🚀"
        await bot.send_message(uid, win_txt, parse_mode=ParseMode.HTML)
        group_msg = await bot.send_message(
            GROUP_ID,
            f"🎉 {c.from_user.mention_html()} в ежедневном спине выбил {prize}!",
            parse_mode=ParseMode.HTML
        )
        group_messages.add(group_msg.message_id)
        asyncio.create_task(delete_after(GROUP_ID, group_msg.message_id, 120))
    else:
        loss_txt = f"😔 {hbold('ОЙ, НЕ ПОВЕЗЛО!')}\n\nНадо было выбить 777, а выпало {value}...\n\n{condition_message}\n⏳ Ждите 30 секунд КД и пробуйте снова! Не сдавайтесь, удача близко! 🌟"
        await bot.send_message(uid, loss_txt, parse_mode=ParseMode.HTML)
    await db.update_two_day_spin(uid)
    active_game = await db.get_active_admin_game()
    is_admin = c.from_user.id in ADMIN_IDS
    await c.message.edit_reply_markup(reply_markup=KB.main(ud, bool(active_game), is_admin))
# --------- админка ---------
@rt.callback_query(F.data == "admin_panel")
async def admin_panel(c: CallbackQuery):
    if c.from_user.id not in ADMIN_IDS:
        await c.answer("❌ Вы не админ!", show_alert=True)
        return
    txt = f"🔧 {hbold('АДМИН-ПАНЕЛЬ')}\n\nДобро пожаловать, босс! Выберите действие ниже:\n\n• 📊 Статистика - посмотрите пользователей и выигрыши\n• 🔧 Сбросить спины - обновите всем спины\n• 🎮 Создать мини-игру - запустите новый розыгрыш\n• 📢 Рассылка - отправьте сообщение всем\n• 💰 Начислить спины - добавьте спины пользователю\n• 📊 Топ игроков - топ-20 по очкам\n• 🛠 Начать тех.работы - запустить режим тех.работ"
    await c.message.edit_text(txt, reply_markup=KB.admin(), parse_mode=ParseMode.HTML)
@rt.message(Command("admin"))
async def admin(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.answer("❌ Вы не админ!", show_alert=True)
        return
    txt = f"🔧 {hbold('АДМИН-ПАНЕЛЬ')}\n\nДобро пожаловать, босс! Выберите действие ниже:\n\n• 📊 Статистика - посмотрите пользователей и выигрыши\n• 🔧 Сбросить спины - обновите всем спины\n• 🎮 Создать мини-игру - запустите новый розыгрыш\n• 📢 Рассылка - отправьте сообщение всем\n• 💰 Начислить спины - добавьте спины пользователю\n• 📊 Топ игроков - топ-20 по очкам\n• 🛠 Начать тех.работы - запустить режим тех.работ"
    await m.answer(txt, reply_markup=KB.admin(), parse_mode=ParseMode.HTML)
@rt.callback_query(F.data == "a_stats")
async def a_stats(c: CallbackQuery):
    async with aiosqlite.connect(db.name) as db_:
        cur = await db_.execute("SELECT COUNT(*) FROM users")
        total = (await cur.fetchone())[0]
        cur = await db_.execute("SELECT COUNT(*) FROM wins_history WHERE DATE(created_at)=DATE('now')")
        today = (await cur.fetchone())[0]
    txt = f"📊 {hbold('СТАТИСТИКА БОТА')}\n\n👥 Всего пользователей: {total}\n🏆 Выигрышей сегодня: {today}\n\n{ hitalic('Бот работает на полную!') } 🚀"
    await c.message.edit_text(txt, reply_markup=KB.back(), parse_mode=ParseMode.HTML)
@rt.callback_query(F.data == "a_reset")
async def a_reset(c: CallbackQuery):
    await db.reset_daily_spins()
    await c.answer("✅ Спины сброшены для всех! Удачи игрокам!", show_alert=True)
    await c.message.edit_text("🔧 Админ-панель", reply_markup=KB.admin())
# --------- тех.работы (админ) ---------
@rt.callback_query(F.data == "a_maintenance_start")
async def a_maintenance_start(c: CallbackQuery):
    if c.from_user.id not in ADMIN_IDS:
        return
    await c.message.edit_text("🛠 Введите количество часов для тех.работ (например, 1):", reply_markup=KB.back())
    user_cache[c.from_user.id]["wait_maintenance_hours"] = True
@rt.message(Command("open"))
async def open_bot(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.answer("❌ Вы не админ!", show_alert=True)
        return
    await db.clear_maintenance()
    # Рассылка всем пользователям
    async with aiosqlite.connect(db.name) as db_:
        cur = await db_.execute("SELECT user_id FROM users")
        users = [r[0] for r in await cur.fetchall()]
    txt = f"✅ Бот вышел из тех.работ и работает в штатном режиме! Добро пожаловать обратно!"
    sent = 0
    for uid in users:
        try:
            await bot.send_message(uid, txt, parse_mode=ParseMode.HTML)
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await m.reply(f"✅ Бот открыт. Оповещено {sent} пользователей.")
# --------- создание мини-игры (админ) ---------
@rt.callback_query(F.data == "a_new_mini_game")
async def a_new_mini_game(c: CallbackQuery):
    txt = f"🎮 {hbold('СОЗДАНИЕ МИНИ-ИГРЫ')}\n\nШаг 1: Укажите количество победителей (отправьте число, например, 3):\n\n{ hitalic('Мини-игра будет активна, пока не наберется победителей!') } ⏳"
    await c.message.edit_text(txt, reply_markup=KB.back(), parse_mode=ParseMode.HTML)
    user_cache[c.from_user.id]["admin_create_step"] = "max_winners"
@rt.callback_query(F.data.startswith("select_game_"))
async def select_game(c: CallbackQuery):
    if c.from_user.id not in ADMIN_IDS:
        return
    game_type = c.data.replace("select_game_", "")
    if game_type not in MINI_GAMES:
        await c.answer("❌ Игра не найдена!", show_alert=True)
        return
    user_cache[c.from_user.id]["game_type"] = game_type
    user_cache[c.from_user.id]["emoji"] = MINI_GAMES[game_type]["emoji"]
    examples = (
        "Примеры условий выигрыша для игр:\n"
        "- Кубик (🎲): 6 или 5-6 (диапазон)\n"
        "- Дартс (🎯): 1 (центр) или 1-2\n"
        "- Баскетбол (🏀): 5 (гол) или 4-5\n"
        "- Боулинг (🎳): 6 (страйк) или 5-6\n"
        "- Футбол (⚽): 5 (гол) или 4-5\n"
        "- Рулетка (🎰): 42 (777) или 42-43\n"
    )
    await c.message.edit_text(
        f"Шаг 3: Игра выбрана - {MINI_GAMES[game_type]['name']}.\nУкажите условие выигрыша (например, '6' для кубика, '42' для 777 на рулетке):\n\n{examples}",
        reply_markup=KB.back()
    )
    user_cache[c.from_user.id]["admin_create_step"] = "win_condition"
@rt.callback_query(F.data.startswith("prize_"))
async def select_prize_type(c: CallbackQuery):
    if c.from_user.id not in ADMIN_IDS:
        return
    prize_type = c.data.replace("prize_", "")
    user_cache[c.from_user.id]["prize_type"] = prize_type
    await c.message.edit_text(
        f"Шаг 5: Выберите приз ({prize_type.capitalize()}):",
        reply_markup=KB.select_prize(prize_type)
    )
    user_cache[c.from_user.id]["admin_create_step"] = "prize_id"
@rt.callback_query(F.data.startswith("select_prize_"))
async def select_prize(c: CallbackQuery, bot: Bot):
    if c.from_user.id not in ADMIN_IDS:
        return
    parts = c.data.replace("select_prize_", "").split("_", 1)
    prize_type = parts[0]
    prize_id = parts[1]
    user_cache[c.from_user.id]["prize_id"] = prize_id
    # Сохраняем игру
    creator = c.from_user.id
    game_type = user_cache[creator]["game_type"]
    emoji = user_cache[creator]["emoji"]
    win_condition = user_cache[creator]["win_condition"]
    max_w = user_cache[creator]["max_winners"]
    await db.create_admin_game(creator, game_type, emoji, win_condition, prize_type, prize_id, max_w)
    # Оповещаем пользователей
    async with aiosqlite.connect(db.name) as db_:
        cur = await db_.execute("SELECT user_id FROM users")
        users = [r[0] for r in await cur.fetchall()]
    prize_name = get_prize_name(prize_type, prize_id)
    txt = f"🎮 {hbold('Новая мини-игра создана!')}\n\nИгра: {MINI_GAMES[game_type]['name']}\nПриз: {prize_name}\nПобедителей: {max_w}\nУсловие: {win_condition}\n\nУчаствуйте в главном меню!"
    sent = 0
    for uid in users:
        try:
            await bot.send_message(uid, txt, reply_markup=KB.join_mini_game(), parse_mode=ParseMode.HTML)
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass
    # Оповещаем группу
    group_msg = await bot.send_message(GROUP_ID, f"🎮 Мини-игра создана: {MINI_GAMES[game_type]['name']} на {prize_name} ({max_w} победителей)!")
    group_messages.add(group_msg.message_id)
    asyncio.create_task(delete_after(GROUP_ID, group_msg.message_id, 120))
    await c.answer("✅ Мини-игра успешно создана!", show_alert=True)
    await c.message.edit_text(f"✅ Мини-игра создана!\nОповещено {sent} пользователей.", reply_markup=KB.admin())
# --------- мини-игра (пользователь) ---------
@rt.callback_query(F.data == "mini_game")
async def mini_game(c: CallbackQuery):
    game = await db.get_active_admin_game()
    if not game:
        await c.answer("❌ Нет активной мини-игры!", show_alert=True)
        return
    prize_name = get_prize_name(game["prize_type"], game["prize_id"])
    txt = f"🎮 {hbold('МИНИ-ИГРА')}\n\n🚨 {hbold('!!! БРОСАЕТ БОТ !!!')}\nВы только нажимаете кнопку 'Бросить' каждые 30 секунд!!! ⏳\n\nНазвание: {MINI_GAMES[game['game_type']]['name']}\nПриз: {prize_name}\nПобедителей: {game['max_winners']}\nУсловие выигрыша: {game['win_condition']}\n\n{ hbold('Удачи! Вы можете стать победителем!') } 🌟"
    await c.message.edit_text(txt, reply_markup=KB.mini_game_start(game), parse_mode=ParseMode.HTML)
@rt.callback_query(F.data == "play_mini_game")
async def play_mini_game(c: CallbackQuery, bot: Bot):
    game = await db.get_active_admin_game()
    if not game:
        await c.answer("❌ Нет активной мини-игры!", show_alert=True)
        return
    try:
        await c.answer(f"🎮 Бросаем {game['emoji']}...", show_alert=False)
    except TelegramBadRequest as e:
        if "query is too old" in str(e):
            pass
        else:
            raise
    msg = await bot.send_dice(c.from_user.id, emoji=game["emoji"])
    await asyncio.sleep(4)
    val = msg.dice.value
    # Проверка условия выигрыша
    win_conditions = game["win_condition"].split("-") if "-" in game["win_condition"] else [game["win_condition"]]
    win_conditions = [int(v) for v in win_conditions]
    win = val in win_conditions
    prize_name = get_prize_name(game["prize_type"], game["prize_id"])
    if win:
        pos = await db.add_admin_winner(game["id"], c.from_user.id)
        if pos <= game["max_winners"]:
            await db.update_stats(c.from_user.id, win=True, points=100, spins=0) # +100 звезд за выигрыш
            await bot.send_message(
                c.from_user.id,
                f"🎉 {hbold('Победа!')} Вы {pos}-й победитель! Приз: {prize_name}\n+100 ⭐\nОткройте ЛС чтобы тебе мог написать админ\создатель для получения приза!",
                parse_mode=ParseMode.HTML
            )
            group_msg = await bot.send_message(
                GROUP_ID,
                f"🎉 {c.from_user.mention_html()} - {pos}-й победитель в мини-игре! Приз: {prize_name}",
                parse_mode=ParseMode.HTML
            )
            group_messages.add(group_msg.message_id)
            asyncio.create_task(delete_after(GROUP_ID, group_msg.message_id, 120))
            if pos == game["max_winners"]:
                await db.close_admin_game(game["id"])
                end_msg = await bot.send_message(GROUP_ID, f"🏁 Мини-игра завершена! {pos} победителей получили {prize_name}.")
                group_messages.add(end_msg.message_id)
                asyncio.create_task(delete_after(GROUP_ID, end_msg.message_id, 120))
        else:
            await bot.send_message(c.from_user.id, "😔 Места закончились!")
    else:
        await bot.send_message(c.from_user.id, f"😔 выпало другое...!")
# --------- остальное меню ---------
@rt.callback_query(F.data == "menu")
async def menu(c: CallbackQuery):
    ud = await db.get_user(c.from_user.id)
    active_game = await db.get_active_admin_game()
    is_admin = c.from_user.id in ADMIN_IDS
    await c.message.edit_text(f"🎁 {hbold('Главное меню')}", reply_markup=KB.main(ud, bool(active_game), is_admin), parse_mode=ParseMode.HTML)
@rt.callback_query(F.data == "top")
async def top(c: CallbackQuery):
    rows = await db.top(100)
    txt = f"🏆 {hbold('ТОП-100')}\n\n"
    for i, r in enumerate(rows[:10], 1):
        medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"#{i}"
        un = r["username"] or f"User{r['user_id']}"
        txt += f"{medal} {hcode(un)} → 💎{fmt_num(r['total_points'])} | 🏆{r['wins_count']}\n"
    ud = await db.get_user(c.from_user.id)
    if ud:
        async with aiosqlite.connect(db.name) as db_:
            cur = await db_.execute("SELECT COUNT(*)+1 FROM users WHERE total_points>?", (ud["total_points"],))
            rank = (await cur.fetchone())[0]
        txt += f"\n📍 Вы на #{rank} месте"
    await c.message.edit_text(txt, reply_markup=KB.back(), parse_mode=ParseMode.HTML)
@rt.callback_query(F.data == "stats")
async def stats(c: CallbackQuery):
    ud = await db.get_user(c.from_user.id)
    lvl = level_info(ud["total_points"])
    txt = f"📈 {hbold('ВАША СТАТИСТИКА')}\n\n"
    txt += f"👤 {hlink(c.from_user.full_name, f'tg://user?id={c.from_user.id}')}\n"
    txt += f"🏆 Уровень: {hbold(lvl['name'])}\n"
    txt += f"🎰 Спинов: {ud['spins_count']}\n"
    txt += f"🏅 Побед: {ud['wins_count']}\n"
    txt += f"💎 Очки: {fmt_num(ud['total_points'])}\n"
    txt += f"💰 Спинов: {ud['daily_spins']}\n"
    txt += f"👥 Рефералов: {ud['referral_count']}"
    await c.message.edit_text(txt, reply_markup=KB.back(), parse_mode=ParseMode.HTML)
@rt.callback_query(F.data == "ref")
async def ref(c: CallbackQuery, bot: Bot):
    ud = await db.get_user(c.from_user.id)
    link = f"https://t.me/{(await bot.get_me()).username}?start={ud['referral_code']}"
    txt = f"👥 {hbold('РЕФЕРАЛЫ')}\n\n🔗 {hcode(link)}\n🎁 За {REFS_FOR_SPIN} друзей: +1 ежедневный спин\nВаши рефералы: {ud['referral_count']}"
    await c.message.edit_text(txt, reply_markup=KB.back(), parse_mode=ParseMode.HTML)
@rt.callback_query(F.data == "shop")
async def shop(c: CallbackQuery):
    ud = await db.get_user(c.from_user.id)
    txt = f"🏪 {hbold('Магазин')}\n\nВаши очки: 💎{fmt_num(ud['total_points'])}"
    await c.message.edit_text(txt, reply_markup=KB.shop_items(ud["total_points"]), parse_mode=ParseMode.HTML)
@rt.callback_query(F.data.startswith("buy_"))
async def buy(c: CallbackQuery):
    item_id = c.data.replace("buy_", "")
    if item_id not in SHOP_ITEMS:
        await c.answer("❌ Товар не найден!", show_alert=True)
        return
    item = SHOP_ITEMS[item_id]
    uid = c.from_user.id
    ud = await db.get_user(uid)
    if ud["total_points"] < item["price"]:
        await c.answer("❌ Недостаточно очков!", show_alert=True)
        return
    async with aiosqlite.connect(db.name) as db_:
        await db_.execute("UPDATE users SET total_points=total_points-? WHERE user_id=?", (item["price"], uid))
        await db_.execute("INSERT INTO shop_purchases(user_id, item_id, price) VALUES(?,?,?)", (uid, item_id, item["price"]))
        if item["type"] == "spins":
            await db_.execute("UPDATE users SET daily_spins=daily_spins+? WHERE user_id=?", (item["value"], uid))
        elif item["type"] == "mult":
            end = datetime.now() + timedelta(seconds=item["duration"])
            await db_.execute("UPDATE users SET multiplier_end=? WHERE user_id=?", (end, uid))
        await db_.commit()
        user_cache.clear()
    await c.answer(f"✅ Куплено: {item['name']}!", show_alert=True)
    active_game = await db.get_active_admin_game()
    is_admin = c.from_user.id in ADMIN_IDS
    ud = await db.get_user(uid)
    txt = f"🎉 {hbold('Покупка успешна!')}\n\n📦 {item['name']}\n💎 Списано: {fmt_num(item['price'])}\n\nОстаток: 💎{fmt_num(ud['total_points'])}"
    await c.message.edit_text(txt, reply_markup=KB.main(ud, bool(active_game), is_admin), parse_mode=ParseMode.HTML)
@rt.callback_query(F.data == "support")
async def support(c: CallbackQuery):
    txt = f"📞 {hbold('ТЕХПОДДЕРЖКА')}\n\n🆘 {hlink('Админ', f'tg://user?id={ADMIN_IDS[0]}')}\n\n❓ FAQ:\n• Крутите барабан – получайте призы\n• Спины обновляются в 00:00 МСК\n• Приводите друзей – получайте бонусы\n• Мини-игры создаются админом"
    await c.message.edit_text(txt, reply_markup=KB.back(), parse_mode=ParseMode.HTML)
# --------- рассылка (админ) ---------
@rt.callback_query(F.data == "a_broadcast")
async def a_broadcast(c: CallbackQuery):
    await c.message.edit_text("📢 Введите текст рассылки:", reply_markup=KB.back())
    user_cache[c.from_user.id]["wait_broadcast"] = True
# --------- начислить спины (админ) ---------
@rt.callback_query(F.data == "a_add_spins")
async def a_add_spins(c: CallbackQuery):
    await c.message.edit_text("💰 Введите: <code>ID количество</code>", reply_markup=KB.back(), parse_mode=ParseMode.HTML)
    user_cache[c.from_user.id]["wait_add_spins"] = True
# --------- топ игроков (админ) ---------
@rt.callback_query(F.data == "a_top_players")
async def a_top_players(c: CallbackQuery):
    rows = await db.top(20)
    txt = f"📊 {hbold('ТОП-20')}\n\n"
    for i, r in enumerate(rows, 1):
        un = r["username"] or f"User{r['user_id']}"
        txt += f"#{i} {hcode(un)} – 💎{fmt_num(r['total_points'])}\n"
    await c.message.edit_text(txt, reply_markup=KB.back(), parse_mode=ParseMode.HTML)
# --------- удалить все сообщения в группе (админ) ---------
@rt.callback_query(F.data == "a_delete_all_group")
async def a_delete_all_group(c: CallbackQuery, bot: Bot):
    if c.from_user.id not in ADMIN_IDS:
        await c.answer("❌ Вы не админ!", show_alert=True)
        return
    deleted = 0
    for mid in list(group_messages):
        try:
            await bot.delete_message(GROUP_ID, mid)
            deleted += 1
        except:
            pass
        group_messages.discard(mid)
    await c.answer(f"🗑 Удалено {deleted} сообщений!", show_alert=True)
# --------- объединённый обработчик текстовых сообщений от админа ---------
@rt.message(F.text)
async def handle_admin_input(m: Message, bot: Bot):
    uid = m.from_user.id
    if uid not in ADMIN_IDS:
        return
    text = m.text.strip()
    if user_cache.get(uid, {}).get("wait_maintenance_hours"):
        if re.match(r"^\d+$", text):
            hours = int(text)
            if hours < 1:
                await m.reply("❌ Количество часов должно быть больше 0!")
                return
            end_time = datetime.now() + timedelta(hours=hours)
            await db.set_maintenance_end(end_time)
            user_cache[uid].pop("wait_maintenance_hours", None)
            # Рассылка всем пользователям
            async with aiosqlite.connect(db.name) as db_:
                cur = await db_.execute("SELECT user_id FROM users")
                users = [r[0] for r in await cur.fetchall()]
            txt = f"🛠 Бот уходит на тех.работы на {hours} час(ов). Извините за неудобства! Мы вернемся скоро."
            sent = 0
            for uid_ in users:
                try:
                    await bot.send_message(uid_, txt, parse_mode=ParseMode.HTML)
                    sent += 1
                    await asyncio.sleep(0.05)
                except:
                    pass
            await m.reply(f"✅ Тех.работы запущены на {hours} час(ов). Оповещено {sent} пользователей.")
        else:
            await m.reply("❌ Пожалуйста, введите число часов!")
        return
    if user_cache.get(uid, {}).get("wait_add_spins"):
        match = re.match(r"(\d+) (\d+)", text)
        if match:
            uid_, amt = map(int, match.groups())
            async with aiosqlite.connect(db.name) as db_:
                await db_.execute("UPDATE users SET daily_spins=daily_spins+? WHERE user_id=?", (amt, uid_))
                await db_.commit()
            user_cache.pop(f"u{uid_}", None)
            await m.reply(f"✅ Начислено {amt} спинов пользователю {uid_}")
            user_cache[uid].pop("wait_add_spins", None)
        else:
            await m.reply("❌ Формат: ID количество")
        return
    if user_cache.get(uid, {}).get("wait_broadcast"):
        async with aiosqlite.connect(db.name) as db_:
            cur = await db_.execute("SELECT user_id FROM users")
            users = [r[0] for r in await cur.fetchall()]
        ok = 0
        for uid_ in users:
            try:
                await bot.send_message(uid_, text, parse_mode=ParseMode.HTML)
                ok += 1
                await asyncio.sleep(0.05)
            except:
                pass
        await m.reply(f"✅ Рассылка завершена!\nДоставлено: {ok}")
        await bot.send_message(-1003199194395, text, parse_mode=ParseMode.HTML)
        user_cache[uid].pop("wait_broadcast", None)
        return
    step = user_cache.get(uid, {}).get("admin_create_step")
    if step:
        if step == "max_winners":
            if re.match(r"^\d+$", text):
                max_w = int(text)
                if max_w < 1:
                    await m.reply("❌ Количество победителей должно быть больше 0!")
                    return
                user_cache[uid]["max_winners"] = max_w
                await m.reply("Шаг 2: Выберите тип игры:", reply_markup=KB.select_game_type())
                user_cache[uid]["admin_create_step"] = "game_type"
            else:
                await m.reply("❌ Пожалуйста, введите число!")
        elif step == "win_condition":
            win_condition = text
            user_cache[uid]["win_condition"] = win_condition
            await m.reply("Шаг 4: Выберите тип приза:", reply_markup=KB.select_prize_type())
            user_cache[uid]["admin_create_step"] = "prize_type"
        return
async def delete_after(chat_id: int, message_id: int, delay: int):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception as e:
        log.exception(e)
    finally:
        group_messages.discard(message_id)
# ========= Г Л А В Н А Я Ф У Н К Ц И Я =========
async def main():
    await db.init()
    global bot
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.message.middleware(MaintenanceMiddleware()) # Тех.работы для всех, кроме админа
    dp.callback_query.middleware(MaintenanceMiddleware())
    dp.message.middleware(SubMiddleware()) # Подписка для всех, кроме админа
    dp.callback_query.middleware(SubMiddleware())
    dp.message.middleware(SpamMiddleware())
    dp.callback_query.middleware(SpamMiddleware())
    dp.callback_query.middleware(MiniGameCooldownMiddleware())
    dp.include_router(rt)
    await bot.set_my_commands([
        BotCommand(command="start", description="🎁 Запустить"),
        BotCommand(command="stats", description="📊 Статистика"),
        BotCommand(command="top", description="🏆 Топ"),
        BotCommand(command="admin", description="🔧 Админка"),
    ], scope=BotCommandScopeDefault())
    # ежедневный сброс в 00:00 МСК
    async def daily_reset():
        while True:
            now = datetime.now()
            nxt = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
            await asyncio.sleep((nxt - now).total_seconds())
            await db.reset_daily_spins()
            log.info("🔄 Daily reset done")
    asyncio.create_task(daily_reset())
    log.info("🎁 BOT STARTED")
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await bot.session.close()
        log.info("🔌 BOT STOPPED")
if __name__ == "__main__":
    asyncio.run(main())