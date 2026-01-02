import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
import sqlite3
import logging
from datetime import datetime
import time
from collections import defaultdict
import os

BOT_TOKEN = "8232720609:AAF9Xq6AZRludYuQRFPKrcqyZBSg-6iJi_o"
ADMIN_IDS = [6785759216, 1133203599]
REF_REWARD = 15
REF_NEEDED = 5

USER_MESSAGES = defaultdict(list)
SPAM_LIMIT_START = 5
SPAM_TIME_WINDOW = 5
BLOCKED_USERS = set()
BLOCK_DECISIONS = {}

os.makedirs('LogsChat', exist_ok=True)

def is_user_blocked(user_id: int) -> bool:
    return user_id in BLOCKED_USERS

def check_spam(user_id: int, message_text: str = None) -> bool:
    if is_user_blocked(user_id):
        return True
    
    current_time = time.time()
    
    USER_MESSAGES[user_id] = [
        (ts, msg) for ts, msg in USER_MESSAGES[user_id] 
        if current_time - ts <= SPAM_TIME_WINDOW
    ]
    
    USER_MESSAGES[user_id].append((current_time, message_text))
    
    message_count = len(USER_MESSAGES[user_id])
    
    if message_count > 3:
        logging.debug(f"User {user_id} has {message_count} messages in last {SPAM_TIME_WINDOW}s")
    
    if message_count >= SPAM_LIMIT_START:
        logging.warning(f"User {user_id} detected as spammer: {message_count} messages in {SPAM_TIME_WINDOW}s")
        BLOCKED_USERS.add(user_id)
        return True
    
    return False

def get_log_file_path(user_id: int) -> str:
    return f"LogsChat/chat_id{user_id}_.txt"

def update_user_log(user_id: int, username: str, message: str, is_bot: bool = False):
    try:
        log_file = get_log_file_path(user_id)
        current_time = datetime.now()
        
        if is_bot:
            sender = "[БОТ]"
        else:
            sender = f"[@{username if username else f'id{user_id}'}]"
        
        time_str = current_time.strftime("%H.%M.%S")
        date_str = current_time.strftime("%d.%m.%Y")
        
        if len(message) > 500:
            message = message[:497] + "..."
        
        log_entry = f"{time_str} / {date_str} {sender} — {message}\n"
        
        if is_bot:
            log_entry += "-" * 50 + "\n"
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
    except Exception as e:
        logging.error(f"Error updating log for user {user_id}: {e}")

def create_user_log(user_id: int, username: str):
    try:
        log_file = get_log_file_path(user_id)
        
        if not os.path.exists(log_file):
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"Последнее обновление: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n")
                f.write(f"Юзернейм: @{username if username else f'id{user_id}'}\n")
                f.write(f"Айди: {user_id}\n")
                f.write(f"Количество сообщений: 0\n")
                f.write(f"Больше всего повторяется: Нет данных\n")
                f.write("-" * 50 + "\n")
                
    except Exception as e:
        logging.error(f"Error creating log for user {user_id}: {e}")

async def send_logs_to_admin(bot, user_id: int, username: str, spam_count: int):
    try:
        create_user_log(user_id, username)
        
        for admin_id in ADMIN_IDS:
            try:
                log_file = get_log_file_path(user_id)
                
                with open(log_file, 'rb') as f:
                    await bot.send_document(
                        chat_id=admin_id,
                        document=types.InputFile(f, filename=f"logs_user_{user_id}.txt"),
                        caption=f"🚨 Пользователь заблокирован за спам!\n\n"
                               f"ID: {user_id}\n"
                               f"Юзернейм: @{username if username else f'id{user_id}'}\n"
                               f"Сообщений за {SPAM_TIME_WINDOW} секунд: {spam_count}\n"
                               f"Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
                    )
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="🔓 Разбанить", callback_data=f"unblock_{user_id}"),
                        InlineKeyboardButton(text="❌ Игнор", callback_data=f"ignore_block_{user_id}")
                    ]
                ])
                
                decision_msg = await bot.send_message(
                    admin_id,
                    f"🚨 Пользователь заблокирован за спам\n\n"
                    f"ID: {user_id}\n"
                    f"Юзернейм: @{username if username else f'id{user_id}'}\n"
                    f"Сообщений за {SPAM_TIME_WINDOW} секунд: {spam_count}\n\n"
                    f"Выберите действие:",
                    reply_markup=keyboard
                )
                
                BLOCK_DECISIONS[user_id] = {
                    'message_id': decision_msg.message_id,
                    'admin_id': None,
                    'decision': None,
                    'time': datetime.now()
                }
                
            except Exception as e:
                logging.error(f"Error sending logs to admin {admin_id}: {e}")
                
    except Exception as e:
        logging.error(f"Error in send_logs_to_admin: {e}")

async def check_user_blocked_handler(update, bot) -> bool:
    if not update.from_user:
        return True
        
    user_id = update.from_user.id
    
    if is_user_blocked(user_id):
        try:
            if hasattr(update, 'callback_query') and update.callback_query:
                try:
                    await update.callback_query.message.edit_reply_markup(reply_markup=None)
                except:
                    pass
                
                await update.callback_query.answer(
                    text="Вы заблокированы и не можете взаимодействовать с ботом",
                    show_alert=True
                )
                return True
                
            elif hasattr(update, 'message') and update.message and update.message.reply_markup:
                try:
                    await update.message.edit_reply_markup(reply_markup=None)
                except:
                    pass
            
        except Exception as e:
            logging.error(f"Error handling blocked user {user_id}: {e}")
        
        return True
    
    return False

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('referral_bot.db')
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT UNIQUE,
                channel_link TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance INTEGER DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                referrals_count INTEGER DEFAULT 0,
                withdraws_count INTEGER DEFAULT 0,
                total_withdrawn INTEGER DEFAULT 0,
                referrer_id INTEGER,
                registered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                status TEXT DEFAULT 'pending',
                admin_id INTEGER,
                processed_date TIMESTAMP,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                action TEXT,
                target_user_id INTEGER,
                amount INTEGER,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()

    def user_exists(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
        return cursor.fetchone() is not None
    
    def register_user(self, user_id, username, referrer_id=None):
        cursor = self.conn.cursor()
        if not self.user_exists(user_id):
            cursor.execute(
                'INSERT INTO users (user_id, username, referrer_id) VALUES (?, ?, ?)',
                (user_id, username, referrer_id)
            )
            if referrer_id and self.user_exists(referrer_id):
                cursor.execute(
                    'UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?',
                    (referrer_id,)
                )
                cursor.execute('SELECT referrals_count FROM users WHERE user_id = ?', (referrer_id,))
                ref_count = cursor.fetchone()[0]
                if ref_count % REF_NEEDED == 0:
                    cursor.execute(
                        'UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE user_id = ?',
                        (REF_REWARD, REF_REWARD, referrer_id)
                    )
            self.conn.commit()
            return True
        return False
    
    def get_user_data(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT user_id, username, balance, referrals_count, 
                   total_earned, withdraws_count, total_withdrawn 
            FROM users WHERE user_id = ?
        ''', (user_id,))
        return cursor.fetchone()
    
    def create_withdrawal(self, user_id, amount):
        cursor = self.conn.cursor()
        cursor.execute(
            'INSERT INTO withdrawals (user_id, amount) VALUES (?, ?)',
            (user_id, amount)
        )
        cursor.execute(
            'UPDATE users SET balance = balance - ? WHERE user_id = ?',
            (amount, user_id)
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def get_pending_withdrawals(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT w.*, u.username 
            FROM withdrawals w 
            JOIN users u ON w.user_id = u.user_id 
            WHERE w.status = 'pending'
            ORDER BY w.created_date
        ''')
        return cursor.fetchall()
    
    def process_withdrawal(self, withdrawal_id, admin_id, approve=True):
        cursor = self.conn.cursor()
        status = 'approved' if approve else 'rejected'
        
        cursor.execute('''
            UPDATE withdrawals 
            SET status = ?, admin_id = ?, processed_date = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (status, admin_id, withdrawal_id))
        
        if not approve:
            cursor.execute('SELECT user_id, amount FROM withdrawals WHERE id = ?', (withdrawal_id,))
            wd = cursor.fetchone()
            if wd:
                cursor.execute(
                    'UPDATE users SET balance = balance + ? WHERE user_id = ?',
                    (wd[1], wd[0])
                )
        else:
            cursor.execute('SELECT user_id, amount FROM withdrawals WHERE id = ?', (withdrawal_id,))
            wd = cursor.fetchone()
            if wd:
                cursor.execute('''
                    UPDATE users 
                    SET withdraws_count = withdraws_count + 1, 
                    total_withdrawn = total_withdrawn + ? 
                    WHERE user_id = ?
                ''', (wd[1], wd[0]))
        
        self.conn.commit()
    
    def update_balance(self, user_id, amount, add=True):
        cursor = self.conn.cursor()
        if add:
            cursor.execute(
                'UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE user_id = ?',
                (amount, amount, user_id)
            )
        else:
            cursor.execute(
                'UPDATE users SET balance = balance - ? WHERE user_id = ?',
                (amount, user_id)
            )
        self.conn.commit()
    
    def log_admin_action(self, admin_id, action, target_user_id, amount):
        cursor = self.conn.cursor()
        cursor.execute(
            'INSERT INTO admin_logs (admin_id, action, target_user_id, amount) VALUES (?, ?, ?, ?)',
            (admin_id, action, target_user_id, amount)
        )
        self.conn.commit()

    def add_channel(self, channel_id: str, channel_link: str):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO channels (channel_id, channel_link) VALUES (?, ?)',
                (channel_id, channel_link)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    
    def remove_channel(self, channel_id: str):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM channels WHERE channel_id = ?', (channel_id,))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def get_channels(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT channel_id, channel_link FROM channels')
        return cursor.fetchall()
    
    def get_channels_count(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM channels')
        return cursor.fetchone()[0]
    
    def get_all_users_count(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        return cursor.fetchone()[0]

db = Database()

class WithdrawalState(StatesGroup):
    waiting_for_amount = State()

class AdminState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_amount = State()
    waiting_for_action = State()
    waiting_for_channel_id = State()
    waiting_for_channel_link = State()
    waiting_for_broadcast = State()

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def main_menu():
    keyboard = [
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="💎 Вывод"), KeyboardButton(text="👥 Рефералы")],
        [KeyboardButton(text="ℹ️ Помощь")]
    ]
    if ADMIN_IDS:
        keyboard.append([KeyboardButton(text="⚙️ Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def profile_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="💎 Вывод", callback_data="withdraw"),
        InlineKeyboardButton(text="👥 Рефералы", callback_data="refs"),
        InlineKeyboardButton(text="📊 Статистика", callback_data="stats")
    )
    return builder.as_markup()

def admin_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="💰 Выдать звёзды", callback_data="admin_give"),
        InlineKeyboardButton(text="🔨 Забрать звёзды", callback_data="admin_take"),
        InlineKeyboardButton(text="📊 Статистика пользователя", callback_data="admin_stats"),
        InlineKeyboardButton(text="📝 Заявки на вывод", callback_data="admin_withdrawals")
    )
    builder.row(
        InlineKeyboardButton(text="➕ Добавить канал", callback_data="admin_add_channel"),
        InlineKeyboardButton(text="➖ Удалить канал", callback_data="admin_remove_channel")
    )
    builder.row(
        InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
        InlineKeyboardButton(text="📈 Статистика бота", callback_data="admin_bot_stats")
    )
    builder.row(
        InlineKeyboardButton(text="🚫 Блокировки", callback_data="admin_blocks"),
        InlineKeyboardButton(text="🔙 Выход", callback_data="admin_exit")
    )
    builder.adjust(2)
    return builder.as_markup()

def withdrawal_decision_keyboard(withdrawal_id):
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{withdrawal_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{withdrawal_id}")
    )
    return builder.as_markup()

def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )

def format_profile(user_id, username, balance, referrals, earned, withdraws, withdrawn):
    return f"""
✨ *ПРОФИЛЬ* ✨
┌─────────────────
│ *Пользователь:* @{username if username else 'нет'}
│ *ID:* `{user_id}`
├─────────────────
│ 💰 *Баланс:* `{balance} звёзд`
│ 👥 *Рефералов:* `{referrals}`
│ 📈 *Всего заработано:* `{earned} звёзд`
│ 🏦 *Выводов:* `{withdraws}`
│ 💸 *Выведено:* `{withdrawn} звёзд`
└─────────────────
"""

async def check_subscription(user_id: int) -> list:
    unsubscribed_channels = []
    channels = db.get_channels()
    
    for channel_id, channel_link in channels:
        try:
            await asyncio.sleep(0.2)
            member = await bot.get_chat_member(channel_id, user_id)
            if member.status in ['left', 'kicked']:
                unsubscribed_channels.append((channel_id, channel_link))
        except Exception as e:
            logging.error(f"Ошибка проверки подписки на канал {channel_id}: {e}")
            unsubscribed_channels.append((channel_id, channel_link))
    
    return unsubscribed_channels

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not message.from_user:
        return
    
    user_id = message.from_user.id
    username = message.from_user.username
    
    if await check_user_blocked_handler(message, bot):
        return
    
    message_text = message.text if message.text else "/start"
    
    if check_spam(user_id, message_text):
        create_user_log(user_id, username or "")
        update_user_log(user_id, username or "", f"🚫 ЗАБЛОКИРОВАН ЗА СПАМ: {len(USER_MESSAGES[user_id])} сообщений за {SPAM_TIME_WINDOW} секунд", is_bot=True)
        
        try:
            await message.answer(
                "🚫 *Вы были заблокированы за спам!*\n\n"
                f"Обнаружено {len(USER_MESSAGES[user_id])} сообщений за {SPAM_TIME_WINDOW} секунд.\n"
                "Обратитесь к администраторам для разблокировки.",
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Ошибка отправки уведомления о блокировке: {e}")
        
        await send_logs_to_admin(bot, user_id, username or "", len(USER_MESSAGES[user_id]))
        return
    
    create_user_log(user_id, username or "")
    
    update_user_log(user_id, username or "", "/start", is_bot=False)
    
    referrer_id = None
    if len(message.text.split()) > 1:
        try:
            referrer_id = int(message.text.split()[1])
            if referrer_id == user_id:
                referrer_id = None
        except:
            pass
    
    is_new = db.register_user(user_id, username, referrer_id)
    
    unsubscribed_channels = await check_subscription(user_id)
    
    if unsubscribed_channels:
        keyboard = []
        for channel_id, channel_link in unsubscribed_channels:
            keyboard.append([InlineKeyboardButton("➕ Подписаться", url=channel_link)])
        
        keyboard.append([InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription")])
        
        response = await message.answer(
            "🚫 *Для использования бота подпишитесь на каналы!*",
            reply_markup=InlineKeyboardMarkup(keyboard=keyboard),
            parse_mode="Markdown"
        )
        update_user_log(user_id, username or "", "Запрос на подписку на каналы", is_bot=True)
        return
    
    if is_new:
        await message.answer(
            f"🎉 *Добро пожаловать!*\n\n"
            f"Зарабатывай звёзды, приглашая друзей!\n"
            f"За каждые *{REF_NEEDED} рефералов* получаешь *{REF_REWARD} звёзд*!\n\n"
            f"✨ *Бесконечные рефералы = бесконечные звёзды!*",
            reply_markup=main_menu(),
            parse_mode="Markdown"
        )
        update_user_log(user_id, username or "", "Новый пользователь зарегистрирован", is_bot=True)
    else:
        user_data = db.get_user_data(user_id)
        balance = user_data[2] if user_data else 0
        await message.answer(
            f"✨ С возвращением, @{username if username else 'друг'}!\n"
            f"Твой баланс: *{balance} звёзд*",
            reply_markup=main_menu(),
            parse_mode="Markdown"
        )
        update_user_log(user_id, username or "", f"Пользователь вернулся, баланс: {balance}", is_bot=True)

@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    if await check_user_blocked_handler(message, bot):
        return
    
    user_data = db.get_user_data(message.from_user.id)
    if user_data:
        text = format_profile(*user_data)
        update_user_log(message.from_user.id, message.from_user.username or "", "Просмотр профиля", is_bot=False)
        await message.answer(text, parse_mode="Markdown", reply_markup=profile_keyboard())
        update_user_log(message.from_user.id, message.from_user.username or "", "Профиль показан", is_bot=True)

@dp.message(F.text == "📊 Статистика")
@dp.message(F.text == "👥 Рефералы")
async def stats(message: types.Message):
    if await check_user_blocked_handler(message, bot):
        return
    
    user_data = db.get_user_data(message.from_user.id)
    if user_data:
        user_id, username, balance, referrals = user_data[0], user_data[1], user_data[2], user_data[3]
        bot_info = await bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        
        text = f"""
📊 *СТАТИСТИКА* 📊
┌─────────────────
│ *Реферальная ссылка:*
│ `{ref_link}`
├─────────────────
│ *Приглашено:* `{referrals} чел.`
│ *Текущий баланс:* `{balance} звёзд`
│ *Награда:* `{REF_REWARD} звёзд за каждые {REF_NEEDED} рефералов`
├─────────────────
│ *Следующая награда через:* `{REF_NEEDED - (referrals % REF_NEEDED)} реф.`
└─────────────────
*Бесконечные рефералы = бесконечные звёзды!* 🚀
"""
        update_user_log(message.from_user.id, message.from_user.username or "", "Просмотр статистики", is_bot=False)
        await message.answer(text, parse_mode="Markdown")
        update_user_log(message.from_user.id, message.from_user.username or "", "Статистика показана", is_bot=True)

@dp.message(F.text == "ℹ️ Помощь")
async def help_command(message: types.Message):
    if await check_user_blocked_handler(message, bot):
        return
    
    help_text = """
🤖 *Помощь по боту* 🤖

*Как зарабатывать звёзды:*
1. Приглашайте друзей по своей реферальной ссылке
2. За каждые *5 приглашённых* вы получаете *15 звёзд*
3. Рефералы должны нажать на вашу ссылку и начать работу с ботом

*Основные команды:*
• 👤 Профиль - ваша статистика и баланс
• 📊 Статистика - реферальная ссылка и информация
• 💎 Вывод - вывести звёзды на счёт
• 👥 Рефералы - пригласить друзей

*Администраторам:*
• ⚙️ Админ-панель - управление ботом

💰 *Бесконечные рефералы = бесконечные звёзды!* 🚀
"""
    update_user_log(message.from_user.id, message.from_user.username or "", "Просмотр помощи", is_bot=False)
    await message.answer(help_text, parse_mode="Markdown")
    update_user_log(message.from_user.id, message.from_user.username or "", "Помощь показана", is_bot=True)

@dp.message(F.text == "💎 Вывод")
async def withdraw_init(message: types.Message, state: FSMContext):
    if await check_user_blocked_handler(message, bot):
        return
    
    user_data = db.get_user_data(message.from_user.id)
    if user_data and user_data[2] > 0:
        update_user_log(message.from_user.id, message.from_user.username or "", "Начало вывода", is_bot=False)
        await message.answer(
            f"💰 *Ваш баланс:* `{user_data[2]} звёзд`\n"
            f"Введите количество звёзд для вывода:",
            parse_mode="Markdown",
            reply_markup=cancel_keyboard()
        )
        await state.set_state(WithdrawalState.waiting_for_amount)
        update_user_log(message.from_user.id, message.from_user.username or "", "Запрос суммы вывода", is_bot=True)
    else:
        await message.answer("❌ *На балансе недостаточно звёзд!*", parse_mode="Markdown")
        update_user_log(message.from_user.id, message.from_user.username or "", "Ошибка: недостаточно звёзд для вывода", is_bot=True)

@dp.message(WithdrawalState.waiting_for_amount)
async def withdraw_amount(message: types.Message, state: FSMContext):
    if await check_user_blocked_handler(message, bot):
        await state.clear()
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        update_user_log(message.from_user.id, message.from_user.username or "", "Отмена вывода", is_bot=False)
        await message.answer("❌ Вывод отменён.", reply_markup=main_menu())
        update_user_log(message.from_user.id, message.from_user.username or "", "Вывод отменен", is_bot=True)
        return
    
    try:
        amount = int(message.text)
        user_data = db.get_user_data(message.from_user.id)
        
        if amount <= 0:
            await message.answer("❌ Введите положительное число!")
            update_user_log(message.from_user.id, message.from_user.username or "", f"Ошибка: отрицательная сумма вывода {amount}", is_bot=True)
            return
        
        if user_data[2] < amount:
            await message.answer(f"❌ Недостаточно звёзд! Доступно: `{user_data[2]}`", parse_mode="Markdown")
            update_user_log(message.from_user.id, message.from_user.username or "", f"Ошибка: недостаточно звёзд для вывода {amount}", is_bot=True)
            return
        
        wd_id = db.create_withdrawal(message.from_user.id, amount)
        
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"📥 *НОВАЯ ЗАЯВКА НА ВЫВОД!*\n\n"
                    f"├ ID заявки: `{wd_id}`\n"
                    f"├ Пользователь: @{user_data[1]}\n"
                    f"├ User ID: `{user_data[0]}`\n"
                    f"└ Сумма: `{amount} звёзд`\n\n"
                    f"*Статистика пользователя:*\n"
                    f"• Рефералов: `{user_data[3]}`\n"
                    f"• Выводов: `{user_data[5]}`\n"
                    f"• Выведено всего: `{user_data[6]} звёзд`",
                    parse_mode="Markdown",
                    reply_markup=withdrawal_decision_keyboard(wd_id)
                )
            except Exception as e:
                logging.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")
        
        update_user_log(message.from_user.id, message.from_user.username or "", f"Создана заявка на вывод #{wd_id} на {amount} звёзд", is_bot=False)
        await message.answer(
            f"✅ *Заявка #{wd_id} создана!*\n"
            f"Сумма: `{amount} звёзд`\n"
            f"Ожидайте решения администратора.",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        await state.clear()
        update_user_log(message.from_user.id, message.from_user.username or "", f"Заявка на вывод #{wd_id} создана успешно", is_bot=True)
        
    except ValueError:
        await message.answer("❌ Введите число!")
        update_user_log(message.from_user.id, message.from_user.username or "", "Ошибка: введено не число для вывода", is_bot=True)

@dp.message(F.text == "⚙️ Админ-панель")
async def admin_panel(message: types.Message):
    if await check_user_blocked_handler(message, bot):
        return
    
    if message.from_user.id in ADMIN_IDS:
        update_user_log(message.from_user.id, message.from_user.username or "", "Вход в админ-панель", is_bot=False)
        await message.answer(
            "⚙️ *Административная панель*",
            parse_mode="Markdown",
            reply_markup=admin_keyboard()
        )
        update_user_log(message.from_user.id, message.from_user.username or "", "Админ-панель показана", is_bot=True)
    else:
        await message.answer("❌ Доступ запрещён!")
        update_user_log(message.from_user.id, message.from_user.username or "", "Попытка доступа к админ-панели без прав", is_bot=True)

@dp.callback_query(F.data == "withdraw")
async def inline_withdraw(callback: types.CallbackQuery, state: FSMContext):
    if await check_user_blocked_handler(callback, bot):
        return
    
    user_data = db.get_user_data(callback.from_user.id)
    if user_data and user_data[2] > 0:
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Начало вывода (инлайн)", is_bot=False)
        await callback.message.answer(
            f"💰 *Ваш баланс:* `{user_data[2]} звёзд`\n"
            f"Введите количество звёзд для вывода:",
            parse_mode="Markdown",
            reply_markup=cancel_keyboard()
        )
        await state.set_state(WithdrawalState.waiting_for_amount)
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Запрос суммы вывода (инлайн)", is_bot=True)
    else:
        await callback.message.answer("❌ *На балансе недостаточно звёзд!*", parse_mode="Markdown")
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Ошибка: недостаточно звёзд для вывода (инлайн)", is_bot=True)
    await callback.answer()

@dp.callback_query(F.data == "refs")
async def inline_refs(callback: types.CallbackQuery):
    if await check_user_blocked_handler(callback, bot):
        return
    
    user_data = db.get_user_data(callback.from_user.id)
    if user_data:
        user_id, username, balance, referrals = user_data[0], user_data[1], user_data[2], user_data[3]
        bot_info = await bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        
        text = f"""
📊 *ВАША СТАТИСТИКА* 📊
┌─────────────────
│ *Реферальная ссылка:*
│ `{ref_link}`
├─────────────────
│ *Приглашено:* `{referrals} чел.`
│ *Текущий баланс:* `{balance} звёзд`
│ *Награда:* `{REF_REWARD} звёзд за каждые {REF_NEEDED} рефералов`
└─────────────────
*Бесконечные рефералы = бесконечные звёзды!* 🚀
"""
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Просмотр статистики (инлайн)", is_bot=False)
        await callback.message.answer(text, parse_mode="Markdown")
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Статистика показана (инлайн)", is_bot=True)
    await callback.answer()

@dp.callback_query(F.data == "stats")
async def inline_stats(callback: types.CallbackQuery):
    if await check_user_blocked_handler(callback, bot):
        return
    
    user_data = db.get_user_data(callback.from_user.id)
    if user_data:
        text = format_profile(*user_data)
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Просмотр профиля (инлайн)", is_bot=False)
        await callback.message.answer(text, parse_mode="Markdown")
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Профиль показан (инлайн)", is_bot=True)
    await callback.answer()

@dp.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: types.CallbackQuery):
    if await check_user_blocked_handler(callback, bot):
        return
    
    await callback.answer()
    
    user_id = callback.from_user.id
    update_user_log(user_id, callback.from_user.username or "", "Проверка подписки (callback)", is_bot=False)
    
    unsubscribed_channels = await check_subscription(user_id)
    
    if unsubscribed_channels:
        keyboard = []
        for channel_id, channel_link in unsubscribed_channels:
            keyboard.append([InlineKeyboardButton("➕ Подписаться", url=channel_link)])
        
        keyboard.append([InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription")])
        
        await callback.message.edit_text(
            "🚫 *Для использования бота подпишитесь на каналы!*",
            reply_markup=InlineKeyboardMarkup(keyboard=keyboard),
            parse_mode="Markdown"
        )
        update_user_log(user_id, callback.from_user.username or "", "Запрос на подписку на каналы", is_bot=True)
    else:
        await show_main_menu_from_callback(callback)

async def show_main_menu_from_callback(callback: types.CallbackQuery):
    user = callback.from_user
    user_id = user.id
    
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    
    caption = f"✨ С возвращением, @{user.username if user.username else 'друг'}!\n\nИспользуйте меню ниже:"
    
    keyboard = [
        [InlineKeyboardButton("👤 Профиль", callback_data="stats")],
        [InlineKeyboardButton("📊 Статистика", callback_data="refs")],
        [InlineKeyboardButton("💎 Вывод", callback_data="withdraw")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")],
    ]
    
    if user_id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin_panel")])
    
    await callback.message.edit_text(
        caption,
        reply_markup=InlineKeyboardMarkup(keyboard=keyboard),
        parse_mode="Markdown"
    )
    update_user_log(user_id, user.username or "", "Главное меню показано", is_bot=True)

@dp.callback_query(F.data == "help")
async def help_callback(callback: types.CallbackQuery):
    if await check_user_blocked_handler(callback, bot):
        return
    
    help_text = """
🤖 *Помощь по боту* 🤖

*Как зарабатывать звёзды:*
1. Приглашайте друзей по своей реферальной ссылке
2. За каждые *5 приглашённых* вы получаете *15 звёзд*
3. Рефералы должны нажать на вашу ссылку и начать работу с ботом

💰 *Бесконечные рефералы = бесконечные звёзды!* 🚀
"""
    update_user_log(callback.from_user.id, callback.from_user.username or "", "Просмотр помощи (инлайн)", is_bot=False)
    await callback.message.answer(help_text, parse_mode="Markdown")
    update_user_log(callback.from_user.id, callback.from_user.username or "", "Помощь показана (инлайн)", is_bot=True)
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_"))
async def admin_callback(callback: types.CallbackQuery, state: FSMContext):
    if await check_user_blocked_handler(callback, bot):
        return
    
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещён!")
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Попытка доступа к админ-панели без прав (инлайн)", is_bot=True)
        return
    
    action = callback.data
    
    if action == "admin_give":
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Админ: выдача звёзд", is_bot=False)
        await callback.message.answer(
            "Введите ID пользователя для выдачи звёзд:",
            reply_markup=cancel_keyboard()
        )
        await state.set_state(AdminState.waiting_for_user_id)
        await state.update_data(action="give")
        
    elif action == "admin_take":
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Админ: изъятие звёзд", is_bot=False)
        await callback.message.answer(
            "Введите ID пользователя для изъятия звёзд:",
            reply_markup=cancel_keyboard()
        )
        await state.set_state(AdminState.waiting_for_user_id)
        await state.update_data(action="take")
        
    elif action == "admin_stats":
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Админ: статистика пользователя", is_bot=False)
        await callback.message.answer(
            "Введите ID пользователя для просмотра статистики:",
            reply_markup=cancel_keyboard()
        )
        await state.set_state(AdminState.waiting_for_user_id)
        await state.update_data(action="stats")
        
    elif action == "admin_withdrawals":
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Админ: просмотр заявок на вывод", is_bot=False)
        withdrawals = db.get_pending_withdrawals()
        if withdrawals:
            text = "📝 *Ожидающие заявки:*\n\n"
            for wd in withdrawals:
                text += (
                    f"├ *Заявка #{wd[0]}*\n"
                    f"│ Пользователь: @{wd[6]}\n"
                    f"│ ID: `{wd[1]}`\n"
                    f"│ Сумма: `{wd[2]} звёзд`\n"
                    f"│ Дата: `{wd[7]}`\n"
                    f"└──────\n"
                )
            await callback.message.answer(text, parse_mode="Markdown")
        else:
            await callback.message.answer("✅ Нет ожидающих заявок.")
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Показаны заявки на вывод", is_bot=True)
    
    elif action == "admin_add_channel":
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Админ: добавление канала", is_bot=False)
        if db.get_channels_count() >= 10:
            await callback.message.answer("❌ Достигнут лимит каналов (10)")
            return
        
        await callback.message.answer(
            "Введите ID канала (например: -1001234567890):",
            reply_markup=cancel_keyboard()
        )
        await state.set_state(AdminState.waiting_for_channel_id)
        
    elif action == "admin_remove_channel":
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Админ: удаление канала", is_bot=False)
        channels = db.get_channels()
        if not channels:
            await callback.message.answer("❌ Нет добавленных каналов")
            return
        
        text = "📋 *Выберите канал для удаления:*\n\n"
        keyboard = []
        for i, (channel_id, channel_link) in enumerate(channels, 1):
            keyboard.append([InlineKeyboardButton(f"❌ {channel_link}", callback_data=f"remove_channel_{channel_id}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")])
        
        await callback.message.answer(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard=keyboard),
            parse_mode="Markdown"
        )
        
    elif action == "admin_broadcast":
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Админ: рассылка", is_bot=False)
        await callback.message.answer(
            "📢 *Рассылка сообщения*\n\n"
            "Отправьте сообщение для рассылки всем пользователям:",
            reply_markup=cancel_keyboard(),
            parse_mode="Markdown"
        )
        await state.set_state(AdminState.waiting_for_broadcast)
        
    elif action == "admin_bot_stats":
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Админ: статистика бота", is_bot=False)
        total_users = db.get_all_users_count()
        channels_count = db.get_channels_count()
        pending_withdrawals = len(db.get_pending_withdrawals())
        
        text = f"""
📊 *Статистика бота:*
├─ 👥 Всего пользователей: `{total_users}`
├─ 📢 Каналов для подписки: `{channels_count}/10`
└─ 📝 Ожидающих выводов: `{pending_withdrawals}`
"""
        await callback.message.answer(text, parse_mode="Markdown")
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Показана статистика бота", is_bot=True)
        
    elif action == "admin_blocks":
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Админ: просмотр блокировок", is_bot=False)
        if not BLOCKED_USERS:
            await callback.message.answer("✅ Нет заблокированных пользователей.")
        else:
            text = "🚫 *Заблокированные пользователи:*\n\n"
            for user_id in BLOCKED_USERS:
                text += f"├ ID: `{user_id}`\n"
            
            keyboard = []
            for user_id in BLOCKED_USERS:
                keyboard.append([InlineKeyboardButton(f"🔓 Разблокировать {user_id}", callback_data=f"unblock_{user_id}")])
            
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")])
            
            await callback.message.answer(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard=keyboard),
                parse_mode="Markdown"
            )
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Показаны блокировки", is_bot=True)
        
    elif action == "admin_exit":
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Админ: выход из панели", is_bot=False)
        await callback.message.answer(
            "✅ *Выход из админ-панели*",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Выход из админ-панели", is_bot=True)
        
    elif action == "admin_panel":
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Админ: вход в панель (инлайн)", is_bot=False)
        await callback.message.answer(
            "⚙️ *Административная панель*",
            parse_mode="Markdown",
            reply_markup=admin_keyboard()
        )
        update_user_log(callback.from_user.id, callback.from_user.username or "", "Админ-панель показана (инлайн)", is_bot=True)
    
    await callback.answer()

@dp.message(AdminState.waiting_for_user_id)
async def admin_user_id(message: types.Message, state: FSMContext):
    if await check_user_blocked_handler(message, bot):
        await state.clear()
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        update_user_log(message.from_user.id, message.from_user.username or "", "Админ: отмена действия", is_bot=False)
        await message.answer("❌ Отменено.", reply_markup=main_menu())
        update_user_log(message.from_user.id, message.from_user.username or "", "Действие отменено", is_bot=True)
        return
    
    try:
        user_id = int(message.text)
        data = await state.get_data()
        
        if data['action'] == 'stats':
            user_data = db.get_user_data(user_id)
            if user_data:
                text = format_profile(*user_data)
                await message.answer(text, parse_mode="Markdown")
                update_user_log(message.from_user.id, message.from_user.username or "", f"Админ: просмотр статистики пользователя {user_id}", is_bot=False)
            else:
                await message.answer("❌ Пользователь не найден!")
                update_user_log(message.from_user.id, message.from_user.username or "", f"Админ: пользователь {user_id} не найден", is_bot=True)
            await state.clear()
            return
        
        await state.update_data(target_user_id=user_id)
        
        if data['action'] in ['give', 'take']:
            await message.answer(
                f"Введите количество звёзд для {'выдачи' if data['action'] == 'give' else 'изъятия'}:",
                reply_markup=cancel_keyboard()
            )
            await state.set_state(AdminState.waiting_for_amount)
        else:
            await state.clear()
            
    except ValueError:
        await message.answer("❌ Введите корректный ID (число)!")
        update_user_log(message.from_user.id, message.from_user.username or "", "Админ: ошибка ввода ID", is_bot=True)

@dp.message(AdminState.waiting_for_amount)
async def admin_amount(message: types.Message, state: FSMContext):
    if await check_user_blocked_handler(message, bot):
        await state.clear()
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        update_user_log(message.from_user.id, message.from_user.username or "", "Админ: отмена действия", is_bot=False)
        await message.answer("❌ Отменено.", reply_markup=main_menu())
        update_user_log(message.from_user.id, message.from_user.username or "", "Действие отменено", is_bot=True)
        return
    
    try:
        amount = int(message.text)
        if amount <= 0:
            await message.answer("❌ Введите положительное число!")
            update_user_log(message.from_user.id, message.from_user.username or "", "Админ: ошибка ввода суммы", is_bot=True)
            return
        
        data = await state.get_data()
        user_id = data['target_user_id']
        action = data['action']
        
        user_data = db.get_user_data(user_id)
        if not user_data:
            await message.answer("❌ Пользователь не найден!")
            update_user_log(message.from_user.id, message.from_user.username or "", f"Админ: пользователь {user_id} не найден", is_bot=True)
            await state.clear()
            return
        
        if action == 'give':
            db.update_balance(user_id, amount, add=True)
            db.log_admin_action(message.from_user.id, "give", user_id, amount)
            await message.answer(
                f"✅ *{amount} звёзд выдано пользователю* @{user_data[1]}",
                parse_mode="Markdown"
            )
            update_user_log(message.from_user.id, message.from_user.username or "", f"Админ: выдано {amount} звёзд пользователю {user_id}", is_bot=False)
            
        elif action == 'take':
            if user_data[2] < amount:
                await message.answer(f"❌ У пользователя только {user_data[2]} звёзд!")
                update_user_log(message.from_user.id, message.from_user.username or "", f"Админ: у пользователя {user_id} только {user_data[2]} звёзд", is_bot=True)
                return
            
            db.update_balance(user_id, amount, add=False)
            db.log_admin_action(message.from_user.id, "take", user_id, amount)
            await message.answer(
                f"✅ *{amount} звёзд изъято у пользователя* @{user_data[1]}",
                parse_mode="Markdown"
            )
            update_user_log(message.from_user.id, message.from_user.username or "", f"Админ: изъято {amount} звёзд у пользователя {user_id}", is_bot=False)
        
        await state.clear()
        await message.answer("⚙️ *Административная панель*", parse_mode="Markdown", reply_markup=admin_keyboard())
        update_user_log(message.from_user.id, message.from_user.username or "", "Возврат в админ-панель", is_bot=True)
        
    except ValueError:
        await message.answer("❌ Введите число!")
        update_user_log(message.from_user.id, message.from_user.username or "", "Админ: ошибка ввода числа", is_bot=True)

@dp.message(AdminState.waiting_for_channel_id)
async def admin_channel_id(message: types.Message, state: FSMContext):
    if await check_user_blocked_handler(message, bot):
        await state.clear()
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        update_user_log(message.from_user.id, message.from_user.username or "", "Админ: отмена добавления канала", is_bot=False)
        await message.answer("❌ Отменено.", reply_markup=main_menu())
        update_user_log(message.from_user.id, message.from_user.username or "", "Добавление канала отменено", is_bot=True)
        return
    
    update_user_log(message.from_user.id, message.from_user.username or "", f"Админ: ID канала: {message.text}", is_bot=False)
    await state.update_data(channel_id=message.text.strip())
    
    await message.answer(
        "Теперь введите ссылку на канал (например: https://t.me/channel):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AdminState.waiting_for_channel_link)

@dp.message(AdminState.waiting_for_channel_link)
async def admin_channel_link(message: types.Message, state: FSMContext):
    if await check_user_blocked_handler(message, bot):
        await state.clear()
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        update_user_log(message.from_user.id, message.from_user.username or "", "Админ: отмена добавления канала", is_bot=False)
        await message.answer("❌ Отменено.", reply_markup=main_menu())
        update_user_log(message.from_user.id, message.from_user.username or "", "Добавление канала отменено", is_bot=True)
        return
    
    data = await state.get_data()
    channel_id = data['channel_id']
    channel_link = message.text.strip()
    
    update_user_log(message.from_user.id, message.from_user.username or "", f"Админ: добавление канала {channel_id} - {channel_link}", is_bot=False)
    
    try:
        await asyncio.sleep(0.2)
        chat_member = await bot.get_chat_member(channel_id, (await bot.get_me()).id)
        if chat_member.status not in ['administrator', 'creator']:
            await message.answer(
                "🚫 *Я не администратор этого канала!*\n\n"
                "Добавьте бота как администратора в канал.",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
            update_user_log(message.from_user.id, message.from_user.username or "", "Админ: бот не админ канала", is_bot=True)
            await state.clear()
            return
    except Exception as e:
        logging.error(f"Ошибка проверки админства: {e}")
        await message.answer(
            "❌ *Ошибка при проверке канала.*\n\n"
            "Убедитесь, что:\n"
            "• ID канала корректен\n"
            "• Бот добавлен в канал\n"
            "• Бот является администратором",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        update_user_log(message.from_user.id, message.from_user.username or "", f"Админ: ошибка проверки канала: {e}", is_bot=True)
        await state.clear()
        return
    
    if db.add_channel(channel_id, channel_link):
        await message.answer(
            f"✅ *Канал успешно добавлен!*\n\n"
            f"ID: `{channel_id}`\n"
            f"Ссылка: {channel_link}",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        update_user_log(message.from_user.id, message.from_user.username or "", f"Админ: канал {channel_id} добавлен", is_bot=True)
    else:
        await message.answer(
            "❌ *Канал уже добавлен!*",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        update_user_log(message.from_user.id, message.from_user.username or "", "Админ: канал уже добавлен", is_bot=True)
    
    await state.clear()

@dp.message(AdminState.waiting_for_broadcast)
async def admin_broadcast(message: types.Message, state: FSMContext):
    if await check_user_blocked_handler(message, bot):
        await state.clear()
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        update_user_log(message.from_user.id, message.from_user.username or "", "Админ: отмена рассылки", is_bot=False)
        await message.answer("❌ Отменено.", reply_markup=main_menu())
        update_user_log(message.from_user.id, message.from_user.username or "", "Рассылка отменена", is_bot=True)
        return
    
    update_user_log(message.from_user.id, message.from_user.username or "", f"Админ: начало рассылки: {message.text[:100]}...", is_bot=False)
    
    users = db.get_all_users_count()
    await message.answer(f"📢 *Начинаю рассылку...*\n\n👥 Всего пользователей: `{users}`", parse_mode="Markdown")
    
    success = 0
    failed = 0
    
    all_users = []
    cursor = db.conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    for row in cursor.fetchall():
        all_users.append(row[0])
    
    for user_id in all_users:
        try:
            await bot.send_message(user_id, message.text, parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
    
    await message.answer(
        f"✅ *Рассылка завершена!*\n\n"
        f"👥 Всего пользователей: `{users}`\n"
        f"✅ Успешно: `{success}`\n"
        f"❌ Ошибок: `{failed}`",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )
    update_user_log(message.from_user.id, message.from_user.username or "", f"Админ: рассылка завершена: {success}/{users} успешно", is_bot=True)
    
    await state.clear()

@dp.callback_query(F.data.startswith("remove_channel_"))
async def remove_channel_callback(callback: types.CallbackQuery):
    if await check_user_blocked_handler(callback, bot):
        return
    
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещён!")
        return
    
    channel_id = callback.data.replace('remove_channel_', '')
    update_user_log(callback.from_user.id, callback.from_user.username or "", f"Админ: удаление канала {channel_id}", is_bot=False)
    
    if db.remove_channel(channel_id):
        await callback.message.answer(
            "✅ *Канал успешно удален!*",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        update_user_log(callback.from_user.id, callback.from_user.username or "", f"Админ: канал {channel_id} удален", is_bot=True)
    else:
        await callback.message.answer(
            "❌ *Ошибка при удалении канала*",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        update_user_log(callback.from_user.id, callback.from_user.username or "", f"Админ: ошибка удаления канала {channel_id}", is_bot=True)
    
    await callback.answer()

@dp.callback_query(F.data.startswith("approve_") | F.data.startswith("reject_"))
async def withdrawal_decision(callback: types.CallbackQuery):
    if await check_user_blocked_handler(callback, bot):
        return
    
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещён!")
        return
    
    action, wd_id = callback.data.split("_")
    wd_id = int(wd_id)
    approve = action == "approve"
    
    update_user_log(callback.from_user.id, callback.from_user.username or "", f"Админ: обработка заявки #{wd_id} - {'одобрена' if approve else 'отклонена'}", is_bot=False)
    
    db.process_withdrawal(wd_id, callback.from_user.id, approve)
    
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT w.*, u.username, u.user_id 
        FROM withdrawals w 
        JOIN users u ON w.user_id = u.user_id 
        WHERE w.id = ?
    ''', (wd_id,))
    wd = cursor.fetchone()
    conn.close()
    
    if wd:
        user_id = wd[1]
        amount = wd[2]
        
        status_text = "одобрен" if approve else "отклонён"
        try:
            await bot.send_message(
                user_id,
                f"📢 *Ваша заявка #{wd_id} {status_text}!*\n"
                f"Сумма: `{amount} звёзд`\n"
                f"{'✅ Средства отправлены!' if approve else '❌ Средства возвращены на баланс.'}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление пользователю {user_id}: {e}")
        
        await callback.message.edit_text(
            f"📢 *Заявка #{wd_id} {status_text.upper()}!*\n\n"
            f"├ Администратор: @{callback.from_user.username if callback.from_user.username else 'N/A'}\n"
            f"├ Пользователь: @{wd[7] if wd[7] else 'N/A'}\n"
            f"├ User ID: `{wd[1]}`\n"
            f"├ Сумма: `{amount} звёзд`\n"
            f"└ Дата: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
            parse_mode="Markdown"
        )
        update_user_log(callback.from_user.id, callback.from_user.username or "", f"Админ: заявка #{wd_id} {status_text}", is_bot=True)
    
    await callback.answer(f"Заявка {'одобрена' if approve else 'отклонена'}!")

@dp.callback_query(F.data.startswith("unblock_"))
async def handle_unblock(callback: types.CallbackQuery):
    await callback.answer()
    
    admin_id = callback.from_user.id
    if admin_id not in ADMIN_IDS:
        return
    
    try:
        user_id = int(callback.data.replace('unblock_', ''))
    except ValueError:
        await callback.message.edit_text(
            "❌ *Ошибка при разблокировке!*",
            parse_mode="Markdown"
        )
        return
    
    if user_id in BLOCK_DECISIONS and BLOCK_DECISIONS[user_id]['decision'] is not None:
        await callback.message.edit_text(
            f"❌ *Решение уже принято другим администратором!*\n\n"
            f"Пользователь @id{user_id} уже был обработан.",
            parse_mode="Markdown"
        )
        return
    
    if user_id in BLOCKED_USERS:
        BLOCKED_USERS.remove(user_id)
    
    if user_id in USER_MESSAGES:
        USER_MESSAGES[user_id] = []
    
    BLOCK_DECISIONS[user_id] = {
        'message_id': callback.message.message_id,
        'admin_id': admin_id,
        'decision': 'unblock',
        'time': datetime.now()
    }
    
    try:
        await bot.send_message(
            user_id,
            "✅ *Вы были разблокированы администратором!*\n\n"
            "Теперь вы можете снова пользоваться ботом.\n"
            "Пожалуйста, соблюдайте правила и не спамьте.",
            parse_mode="Markdown"
        )
        update_user_log(user_id, "", "РАЗБЛОКИРОВАН АДМИНИСТРАТОРОМ", is_bot=True)
    except Exception as e:
        logging.error(f"Ошибка отправки уведомления о разблокировке: {e}")
    
    await callback.message.edit_text(
        f"✅ *Пользователь @id{user_id} был разблокирован!*\n\n"
        f"Решение принял администратор @{callback.from_user.username if callback.from_user.username else callback.from_user.first_name}",
        parse_mode="Markdown"
    )
    
    update_user_log(admin_id, callback.from_user.username or "", f"Разблокирован пользователь: {user_id}", is_bot=False)

@dp.callback_query(F.data.startswith("ignore_block_"))
async def handle_ignore_block(callback: types.CallbackQuery):
    await callback.answer()
    
    admin_id = callback.from_user.id
    if admin_id not in ADMIN_IDS:
        return
    
    try:
        user_id = int(callback.data.replace('ignore_block_', ''))
    except ValueError:
        await callback.message.edit_text(
            "❌ *Ошибка при обработке блокировки!*",
            parse_mode="Markdown"
        )
        return
    
    if user_id in BLOCK_DECISIONS and BLOCK_DECISIONS[user_id]['decision'] is not None:
        await callback.message.edit_text(
            f"❌ *Решение уже принято другим администратором!*\n\n"
            f"Пользователь @id{user_id} уже был обработан.",
            parse_mode="Markdown"
        )
        return
    
    BLOCK_DECISIONS[user_id] = {
        'message_id': callback.message.message_id,
        'admin_id': admin_id,
        'decision': 'ignore',
        'time': datetime.now()
    }
    
    await callback.message.edit_text(
        f"⚠️ *Блокировка пользователя @id{user_id} проигнорирована.*\n\n"
        f"Решение принял администратор @{callback.from_user.username if callback.from_user.username else callback.from_user.first_name}\n"
        f"Пользователь останется заблокированным.",
        parse_mode="Markdown"
    )
    
    update_user_log(admin_id, callback.from_user.username or "", f"Игнорирована блокировка пользователя: {user_id}", is_bot=False)

async def main():
    print("🤖 Бот запущен!")
    print(f"⚙️ Админы: {ADMIN_IDS}")
    print(f"💰 Награда: {REF_REWARD} звёзд за {REF_NEEDED} рефералов")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
