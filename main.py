import asyncio
import logging
import os
import sqlite3
import re
import random
import string
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties

# ==========================================
# ⚙️ 1. НАСТРОЙКИ
# ==========================================
logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("API_TOKEN")
OWNER_ID_STR = os.getenv("DRIVER_ID") 

if not API_TOKEN or not OWNER_ID_STR:
    exit("⛔ CRITICAL ERROR: Token or ID missing")

OWNER_ID = int(OWNER_ID_STR)
SECOND_ADMIN_ID = 6004764782
SUPER_ADMINS = [OWNER_ID, SECOND_ADMIN_ID]

VIP_LIMIT = 10          
MIN_COMMISSION = 4      
DEFAULT_COMMISSION = 10 
LAWYER_LINK = "https://t.me/Ai_advokatrobot"

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

active_orders = {} 

# ==========================================
# 📜 2. КОНТЕНТ
# ==========================================
LEGAL_TEXT = (
    "<b>📜 ПУБЛИЧНАЯ ОФЕРТА</b>\n\n"
    "1. <b>Суть:</b> Агрегатор развлекательных услуг.\n"
    "2. <b>Роли:</b> Водитель — Артист, Пассажир — Зритель.\n"
    "3. <b>Безопасность:</b> Соблюдайте ПДД и УК РФ.\n"
    "4. <b>Финансы:</b> Оплата — это донат за шоу."
)

WELCOME_TEXT = (
    "🎪 <b>ДОБРО ПОЖАЛОВАТЬ В ЦИРК НА КОЛЕСАХ!</b>\n\n"
    "Здесь ты платишь не за километры, а за <b>ЭМОЦИИ</b>.\n\n"
    "🎭 <b>В меню:</b>\n"
    "• Психология на ходу\n"
    "• Танцы на светофорах\n"
    "• Сжигание авто (дорого)\n\n"
    "⚖️ <i>Крыша — <a href='https://t.me/Ai_advokatrobot'>Робот-Адвокат</a>.</i>\n\n"
    "<b>Погнали?</b> 👇"
)

CRAZY_SERVICES = {
    "candy": {"cat": 1, "price": 0, "name": "🍬 Презент", "desc": "Вручение конфеты с пафосным лицом."},
    "nose": {"cat": 1, "price": 300, "name": "👃 Палец в носу", "desc": "Всю поездку водитель ковыряет в носу."},
    "butler": {"cat": 1, "price": 200, "name": "🤵 Дворецкий", "desc": "Открываем дверь, называем 'Сир'."},
    "joke": {"cat": 1, "price": 50, "name": "🤡 Анекдот", "desc": "Тупая шутка. Смеяться обязательно."},
    "silence": {"cat": 1, "price": 150, "name": "🤐 Ниндзя", "desc": "Полная тишина."},
    "granny": {"cat": 2, "price": 800, "name": "👵 Бабуля", "desc": "Ворчание: 'Наркоманы!', 'Шапку надень!'."},
    "gopnik": {"cat": 2, "price": 500, "name": "🍺 Пацанчик", "desc": "Рэпчик, семки, вопросики."},
    "guide": {"cat": 2, "price": 600, "name": "🗣 Горе-Гид", "desc": "Выдуманные факты о городе."},
    "psych": {"cat": 2, "price": 1000, "name": "🧠 Психолог", "desc": "Слушаем нытье, даем советы."},
    "spy": {"cat": 3, "price": 2000, "name": "🕵️‍♂️ 007", "desc": "Паранойя, проверка хвоста."},
    "karaoke": {"cat": 3, "price": 5000, "name": "🎤 Караоке", "desc": "Орем песни дуэтом."},
    "dance": {"cat": 3, "price": 15000, "name": "💃 Танцы", "desc": "Макарена на капоте."},
    "kidnap": {"cat": 4, "price": 30000, "name": "🎭 Похищение", "desc": "В лес (понарошку)."},
    "tarzan": {"cat": 4, "price": 50000, "name": "🦍 Тарзан", "desc": "Рычим на прохожих."},
    "burn": {"cat": 4, "price": 1000000, "name": "🔥 Сжечь авто", "desc": "Едем на пустырь и сжигаем тачку."},
    "eyes": {"cat": 5, "price": 0, "name": "👁️ Глаз-алмаз", "desc": "Комплимент глазам."},
    "smile": {"cat": 5, "price": 0, "name": "😁 Улыбка", "desc": "Комплимент улыбке."},
    "style": {"cat": 5, "price": 0, "name": "👠 Стиль", "desc": "Восхищение одеждой."},
    "improv": {"cat": 5, "price": 0, "name": "✨ Импровизация", "desc": "Артист импровизирует."},
    "propose": {"cat": 5, "price": 1000, "name": "💍 Предложение", "desc": "Предложение руки и сердца."}
}

CATEGORIES = {1: "🟢 ЛАЙТ", 2: "🟡 МЕДИУМ", 3: "🔴 ХАРД", 4: "☠️ VIP БЕЗУМИЕ", 5: "🌹 ДЛЯ ДАМ"}

# ==========================================
# 🗄️ 3. БАЗА ДАННЫХ
# ==========================================
DB_PATH = "/data/taxi_db.sqlite" if os.path.exists("/data") else "taxi_db.sqlite"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Водители
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            user_id INTEGER PRIMARY KEY,
            username TEXT, fio TEXT, car_info TEXT, payment_info TEXT,
            access_code TEXT UNIQUE, vip_code TEXT UNIQUE,
            status TEXT DEFAULT 'pending', role TEXT DEFAULT 'driver',
            balance INTEGER DEFAULT 0, rating_sum INTEGER DEFAULT 0, rating_count INTEGER DEFAULT 0, 
            commission INTEGER DEFAULT 10,
            referred_by INTEGER,
            promo_end_date TIMESTAMP
        )
    """)
    # Услуги
    cursor.execute("CREATE TABLE IF NOT EXISTS driver_services (driver_id INTEGER, service_key TEXT, is_active BOOLEAN DEFAULT 1, PRIMARY KEY (driver_id, service_key))")
    # Кастомные услуги
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custom_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id INTEGER, category_id INTEGER, name TEXT, description TEXT, price INTEGER
        )
    """)
    # Промокоды
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY,
            commission INTEGER,
            duration INTEGER
        )
    """)
    # Клиенты
    cursor.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER DEFAULT NULL, total_spent INTEGER DEFAULT 0, trips_count INTEGER DEFAULT 0, vip_unlocked BOOLEAN DEFAULT 0)")
    # История
    cursor.execute("CREATE TABLE IF NOT EXISTS order_history (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, driver_id INTEGER, service_name TEXT, price INTEGER, rating INTEGER DEFAULT 0, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    
    # Админы
    for admin_id in SUPER_ADMINS:
        try:
            cursor.execute("INSERT OR IGNORE INTO drivers (user_id, username, fio, car_info, payment_info, access_code, vip_code, status, role, commission) VALUES (?, 'BOSS', 'Продюсер', 'VIP', 'CASH', ?, ?, 'active', 'owner', 0)", 
                           (admin_id, f"ADMIN_{admin_id}", f"VIP_BOSS_{admin_id}"))
            cursor.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (admin_id,))
            for key in CRAZY_SERVICES:
                cursor.execute("INSERT OR REPLACE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, 1)", (admin_id, key))
        except: pass
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 🛠 4. УТИЛИТЫ
# ==========================================
def generate_vip_code(name):
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"VIP-{name.split()[0].upper()}-{suffix}"

def is_client_accepted(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT 1 FROM clients WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return bool(res)

def get_client_stats(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT total_spent, trips_count, vip_unlocked FROM clients WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return res if res else (0, 0, 0)

def unlock_vip_for_client(client_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE clients SET vip_unlocked = 1 WHERE user_id=?", (client_id,))
    conn.commit()
    conn.close()

def update_client_after_trip(user_id, amount):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE clients SET total_spent = total_spent + ?, trips_count = trips_count + 1 WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

def get_status_name(spent, trips, vip_unlocked):
    if vip_unlocked: return "👹 МЕЦЕНАТ ХАОСА (VIP)"
    if trips >= VIP_LIMIT: return "💀 ВЕТЕРАН"
    if trips > 3: return "🤪 ЦЕНИТЕЛЬ"
    return "👶 ЗРИТЕЛЬ"

def get_driver_menu(driver_id):
    conn = sqlite3.connect(DB_PATH)
    active_keys = [r[0] for r in conn.execute("SELECT service_key FROM driver_services WHERE driver_id=? AND is_active=1", (driver_id,)).fetchall()]
    customs = conn.execute("SELECT id, category_id, name, description, price FROM custom_services WHERE driver_id=?", (driver_id,)).fetchall()
    conn.close()
    return active_keys, customs

def get_driver_info(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT username, car_info, payment_info, balance, status, access_code, role, fio, rating_sum, rating_count, vip_code, commission, promo_end_date FROM drivers WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return res

def get_linked_driver(client_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT linked_driver_id FROM clients WHERE user_id=?", (client_id,)).fetchone()
    conn.close()
    return res[0] if res and res[0] else None

def set_linked_driver(client_id, driver_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO clients (user_id, linked_driver_id, total_spent, trips_count, vip_unlocked) VALUES (?, ?, (SELECT total_spent FROM clients WHERE user_id=?), (SELECT trips_count FROM clients WHERE user_id=?), (SELECT vip_unlocked FROM clients WHERE user_id=?))", (client_id, driver_id, client_id, client_id, client_id))
    conn.commit()
    conn.close()

def unlink_client(client_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE clients SET linked_driver_id = NULL WHERE user_id=?", (client_id,))
    conn.commit()
    conn.close()

def init_driver_services_defaults(driver_id):
    conn = sqlite3.connect(DB_PATH)
    for k in CRAZY_SERVICES:
        conn.execute("INSERT OR IGNORE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, 1)", (driver_id, k))
    conn.commit()
    conn.close()

def toggle_driver_service(driver_id, service_key):
    conn = sqlite3.connect(DB_PATH)
    curr = conn.execute("SELECT is_active FROM driver_services WHERE driver_id=? AND service_key=?", (driver_id, service_key)).fetchone()
    new_status = 0 if (curr and curr[0] == 1) else 1
    conn.execute("INSERT OR REPLACE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, ?)", (driver_id, service_key, new_status))
    conn.commit()
    conn.close()

def delete_custom_service(service_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM custom_services WHERE id=?", (service_id,))
    conn.commit()
    conn.close()

def get_all_admins_ids():
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT user_id FROM drivers WHERE role IN ('owner', 'admin') AND status='active'").fetchall()
    conn.close()
    return list(set([r[0] for r in res] + SUPER_ADMINS))

def get_active_drivers():
    conn = sqlite3.connect(DB_PATH)
    res = [d[0] for d in conn.execute("SELECT user_id FROM drivers WHERE status='active'").fetchall()]
    conn.close()
    return res

def update_driver_field(user_id, field, value):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(f"UPDATE drivers SET {field} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

def extract_price(text):
    nums = re.findall(r'\d+', str(text))
    return int("".join(nums)) if nums else 0

def log_order(client_id, driver_id, service_name, price):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO order_history (client_id, driver_id, service_name, price) VALUES (?, ?, ?, ?)", (client_id, driver_id, service_name, price))
    conn.commit()
    conn.close()

def update_order_rating(rating, driver_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE drivers SET rating_sum = rating_sum + ?, rating_count = rating_count + 1 WHERE user_id = ?", (rating, driver_id))
    conn.commit()
    conn.close()

def check_and_reset_promo(driver_id):
    info = get_driver_info(driver_id)
    if info and info[12]: # promo_end_date
        end_date = datetime.strptime(info[12], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > end_date:
            conn = sqlite3.connect(DB_PATH)
            ref_count = conn.execute("SELECT COUNT(*) FROM drivers WHERE referred_by=?", (driver_id,)).fetchone()[0]
            new_comm = max(MIN_COMMISSION, DEFAULT_COMMISSION - ref_count)
            conn.execute("UPDATE drivers SET commission = ?, promo_end_date = NULL WHERE user_id = ?", (new_comm, driver_id))
            conn.commit()
            conn.close()

def add_commission(driver_id, amount):
    check_and_reset_promo(driver_id)
    if is_admin(driver_id): return 
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT commission FROM drivers WHERE user_id=?", (driver_id,)).fetchone()
    percent = row[0] if row else 10
    val = int(amount * (percent / 100))
    conn.execute("UPDATE drivers SET balance = balance + ? WHERE user_id=?", (val, driver_id))
    conn.commit()
    conn.close()

async def safe_send_message(chat_id, text, reply_markup=None):
    try: await bot.send_message(chat_id, text, reply_markup=reply_markup); return True
    except: return False

async def check_tos(message: types.Message) -> bool:
    if not is_client_accepted(message.from_user.id): 
        await message.answer("🛑 <b>Сначала нажмите /start!</b>")
        return False
    return True

# ==========================================
# 5. FSM STATES
# ==========================================
class OrderRide(StatesGroup): waiting_for_from = State(); waiting_for_to = State(); waiting_for_phone = State(); waiting_for_price = State()
class DriverRegistration(StatesGroup): waiting_for_fio = State(); waiting_for_car = State(); waiting_for_payment_info = State(); waiting_for_referral = State(); waiting_for_code = State()
class UnlockMenu(StatesGroup): waiting_for_key = State()
class AdminBilling(StatesGroup): waiting_for_custom_req = State()
class AdminEditComm(StatesGroup): waiting_for_new_comm = State()
class AdminBroadcast(StatesGroup): waiting_for_text = State()
class AdminPromo(StatesGroup): code = State(); comm = State(); dur = State()
class ChatState(StatesGroup): active = State()
class ChatWithBoss(StatesGroup): active = State()
class DriverEdit(StatesGroup): waiting_for_new_pay = State(); waiting_for_new_code = State()
class DriverCounterOffer(StatesGroup): waiting_for_offer = State()
class AddStop(StatesGroup): waiting_for_address = State(); waiting_for_price = State()
class AddCustomService(StatesGroup): name = State(); desc = State(); price = State(); cat = State()

# ==========================================
# 6. КЛАВИАТУРЫ
# ==========================================
main_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🎭 Найти Артиста (с авто)")],[KeyboardButton(text="📜 CRAZY МЕНЮ (Категории)")],[KeyboardButton(text="👤 Мой Кабинет"), KeyboardButton(text="⚖️ Вызвать адвоката")]], resize_keyboard=True)
tos_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПОДПИСАТЬ КРОВЬЮ", callback_data="accept_tos")],[InlineKeyboardButton(text="❌ Я слишком нормальный", callback_data="decline_tos")]])

# ==========================================
# 7. ЛОГИКА - КЛИЕНТ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if is_client_accepted(message.from_user.id): await message.answer("⚠️ <b>CRAZY MOOD:</b> С возвращением!", reply_markup=main_kb)
    else: await message.answer(WELCOME_TEXT, reply_markup=tos_kb)

@dp.callback_query(F.data == "accept_tos")
async def tos_accepted(callback: types.CallbackQuery, state: FSMContext):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO clients (user_id, trips_count) VALUES (?, 0)", (callback.from_user.id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("🔥 <b>ВЫ В ИГРЕ!</b>")
    await callback.message.answer("Выбирайте 👇", reply_markup=main_kb)

@dp.callback_query(F.data == "decline_tos")
async def tos_declined(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🚶‍♂️ Скука - это выбор.")

@dp.message(F.text == "📄 ОФЕРТА")
async def show_legal(message: types.Message, state: FSMContext):
    await message.answer(LEGAL_TEXT)

@dp.message(F.text == "⚖️ Вызвать адвоката")
async def lawyer_menu(message: types.Message, state: FSMContext):
    await message.answer("⚖️ <b>ЮРИДИЧЕСКИЙ ОТДЕЛ</b>\n<i>Когда шутка зашла слишком далеко...</i>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚨 ПЕРЕЙТИ", url=LAWYER_LINK)]]))

@dp.message(F.text == "👤 Мой Кабинет")
async def client_cab(message: types.Message, state: FSMContext):
    if not is_client_accepted(message.from_user.id): return await message.answer("/start")
    spent, trips, unlocked = get_client_stats(message.from_user.id)
    status = get_status_name(spent, trips, unlocked)
    
    progress = ""
    if not unlocked and trips < VIP_LIMIT:
        progress = f"\n🔒 До VIP уровня: <b>{VIP_LIMIT - trips} шоу</b>"
    elif unlocked or trips >= VIP_LIMIT:
        progress = "\n🔥 <b>VIP ДОСТУП ОТКРЫТ!</b>"
    
    conn = sqlite3.connect(DB_PATH)
    hist = conn.execute("SELECT service_name, price FROM order_history WHERE client_id=? ORDER BY id DESC LIMIT 5", (message.from_user.id,)).fetchall()
    conn.close()
    h_txt = "\n".join([f"▪ {h[0]} ({h[1]}₽)" for h in hist]) or "Нет истории."
    
    kb = []
    if message.from_user.id in active_orders: kb.append([InlineKeyboardButton(text="💬 ЧАТ С АРТИСТОМ", callback_data="enter_chat")])
    await message.answer(f"👤 <b>КАБИНЕТ ЗРИТЕЛЯ</b>\n👑 {status}\n💰 {spent}₽ | 🎬 {trips}\n{progress}\n\n📜 <b>ИСТОРИЯ:</b>\n{h_txt}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb) if kb else None)

# ==========================================
# 8. ЛОГИКА - АРТИСТ (ВОДИТЕЛЬ)
# ==========================================
@dp.message(Command("cab"))
async def cab(message: types.Message, state: FSMContext):
    await state.clear()
    i = get_driver_info(message.from_user.id)
    if not i: return await message.answer("❌ Нет регистрации. /drive")
    
    check_and_reset_promo(message.from_user.id)
    i = get_driver_info(message.from_user.id) # Re-fetch
    
    active_cid = None
    for cid, o in active_orders.items():
        if o.get('driver_id') == message.from_user.id: active_cid = cid; break
            
    kb = [
        [InlineKeyboardButton(text="🎛 Мой Репертуар (Услуги)", callback_data="driver_menu_edit")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="driver_settings"), InlineKeyboardButton(text="📊 История", callback_data="driver_history")],
        [InlineKeyboardButton(text="🤝 Реферальная программа", callback_data="driver_referral")],
        [InlineKeyboardButton(text="🆘 Чат с Продюсером", callback_data="chat_with_boss")]
    ]
    
    status_txt = "📴 Статус: Свободен"
    if active_cid:
        status_txt = f"🎬 <b>В ЭФИРЕ (Зритель {active_cid})</b>"
        kb.insert(0, [InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ СЕАНС", callback_data=f"ask_finish_{active_cid}")])
        kb.insert(1, [InlineKeyboardButton(text="💬 ЧАТ С ЗРИТЕЛЕМ", callback_data="enter_chat")])
    
    kb.append([InlineKeyboardButton(text="💎 Мой VIP-код для клиентов", callback_data="show_vip_code")])
    kb.append([InlineKeyboardButton(text="💸 Баланс / Продюсер", callback_data="cab_pay")])
    
    promo_info = ""
    if i[12]: promo_info = f" (Промо до {i[12]})"
    
    await message.answer(f"🪪 <b>ГРИМЕРКА: {i[7]}</b>\n💰 Долг: {i[3]}₽\n🔑 Код доступа: <code>{i[5]}</code>\n⭐ Рейтинг: {i[8]}\n📉 Комиссия: <b>{i[11]}%</b>{promo_info}\n━━━━━━━━━━━━\n{status_txt}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- РЕФЕРАЛКА ---
@dp.callback_query(F.data == "driver_referral")
async def driver_ref(callback: types.CallbackQuery, state: FSMContext):
    i = get_driver_info(callback.from_user.id)
    await callback.message.answer(f"🤝 <b>ПАРТНЕРСКАЯ ПРОГРАММА</b>\n\nПриводи друзей-водителей и снижай комиссию!\nТвоя текущая комиссия: <b>{i[11]}%</b>\nМинимальная комиссия: <b>{MIN_COMMISSION}%</b>\n\nТвой код для приглашения: <code>{i[5]}</code>\n(Друг должен ввести его при регистрации).")
    await callback.answer()

# --- МЕНЮ (КАСТОМ + ДЕФОЛТ) ---
@dp.callback_query(F.data == "driver_menu_edit")
async def d_menu(callback: types.CallbackQuery, state: FSMContext):
    act, customs = get_driver_menu(callback.from_user.id)
    kb = []
    for k, v in CRAZY_SERVICES.items():
        status = "✅" if k in act else "❌"
        kb.append([InlineKeyboardButton(text=f"{status} {v['name']}", callback_data=f"tgl_{k}")])
    for cs in customs:
        kb.append([InlineKeyboardButton(text=f"🗑 {cs[2]} ({cs[4]}₽)", callback_data=f"del_cust_{cs[0]}")])
    kb.append([InlineKeyboardButton(text="➕ ДОБАВИТЬ СВОЮ УСЛУГУ", callback_data="add_custom_srv")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_cab")])
    await callback.message.edit_text("🎛 <b>КОНСТРУКТОР МЕНЮ:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "add_custom_srv")
async def add_cust_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("1. Название услуги:")
    await state.set_state(AddCustomService.name)

@dp.message(AddCustomService.name)
async def add_cust_n(message: types.Message, state: FSMContext):
    await state.update_data(n=message.text)
    await message.answer("2. Описание (коротко и ярко):")
    await state.set_state(AddCustomService.desc)

@dp.message(AddCustomService.desc)
async def add_cust_d(message: types.Message, state: FSMContext):
    await state.update_data(d=message.text)
    await message.answer("3. Цена (только число):")
    await state.set_state(AddCustomService.price)

@dp.message(AddCustomService.price)
async def add_cust_p(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число!")
    await state.update_data(p=int(message.text))
    btns = [[InlineKeyboardButton(text=n, callback_data=f"set_cat_{i}")] for i, n in CATEGORIES.items()]
    await message.answer("4. Выберите категорию сложности:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
    await state.set_state(AddCustomService.cat)

@dp.callback_query(F.data.startswith("set_cat_"))
async def add_cust_fin(callback: types.CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[2])
    d = await state.get_data()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO custom_services (driver_id, category_id, name, description, price) VALUES (?, ?, ?, ?, ?)", (callback.from_user.id, cat_id, d['n'], d['d'], d['p']))
    conn.commit()
    conn.close()
    await callback.message.answer("✅ Услуга добавлена в меню!")
    await d_menu(callback, state)

@dp.callback_query(F.data.startswith("del_cust_"))
async def del_cust(callback: types.CallbackQuery, state: FSMContext):
    delete_custom_service(int(callback.data.split("_")[2]))
    await d_menu(callback, state)

@dp.callback_query(F.data.startswith("tgl_"))
async def tgl(callback: types.CallbackQuery, state: FSMContext):
    toggle_driver_service(callback.from_user.id, callback.data.split("_")[1])
    await d_menu(callback, state)

# --- НАСТРОЙКИ ---
@dp.callback_query(F.data == "show_vip_code")
async def show_vip(callback: types.CallbackQuery, state: FSMContext):
    i = get_driver_info(callback.from_user.id)
    await callback.message.answer(f"💎 <b>VIP ПРОМОКОД:</b>\n<code>{i[10]}</code>\nДля клиентов.")
    await callback.answer()

@dp.callback_query(F.data == "driver_settings")
async def driver_settings(callback: types.CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Сменить реквизиты", callback_data="edit_pay")],[InlineKeyboardButton(text="🔑 Сменить Код", callback_data="edit_code")],[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_cab")]])
    await callback.message.edit_text("⚙️ <b>НАСТРОЙКИ:</b>", reply_markup=kb)

@dp.callback_query(F.data == "edit_pay")
async def edit_pay(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Новые реквизиты (Карта/Телефон):")
    await state.set_state(DriverEdit.waiting_for_new_pay)

@dp.message(DriverEdit.waiting_for_new_pay)
async def save_pay(message: types.Message, state: FSMContext):
    update_driver_field(message.from_user.id, "payment_info", message.text)
    await message.answer("✅ Сохранено")
    await cab(message, state)

@dp.callback_query(F.data == "edit_code")
async def edit_code(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Новый Код доступа:")
    await state.set_state(DriverEdit.waiting_for_new_code)

@dp.message(DriverEdit.waiting_for_new_code)
async def save_code(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    conn = sqlite3.connect(DB_PATH)
    if conn.execute("SELECT 1 FROM drivers WHERE access_code=? AND user_id!=?", (code, message.from_user.id)).fetchone():
        conn.close()
        return await message.answer("❌ Этот код уже занят!")
    conn.close()
    update_driver_field(message.from_user.id, "access_code", code)
    await message.answer("✅ Код изменен!")
    await cab(message, state)

@dp.callback_query(F.data == "driver_history")
async def driver_history(callback: types.CallbackQuery, state: FSMContext):
    conn = sqlite3.connect(DB_PATH)
    hist = conn.execute("SELECT service_name, price, date FROM order_history WHERE driver_id=? ORDER BY id DESC LIMIT 5", (callback.from_user.id,)).fetchall()
    conn.close()
    txt = "\n".join([f"▪ {h[0]} ({h[1]}₽)" for h in hist]) or "Пусто."
    await callback.message.edit_text(f"📊 <b>ВАША ИСТОРИЯ:</b>\n{txt}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙", callback_data="back_to_cab")]]))

@dp.callback_query(F.data == "chat_with_boss")
async def chat_boss(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ChatWithBoss.active)
    await callback.message.answer("✍️ Пишите сообщение Продюсеру:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🚪 Конец связи")]], resize_keyboard=True))

@dp.message(ChatWithBoss.active)
async def chat_boss_r(message: types.Message, state: FSMContext):
    if message.text=="🚪 Конец связи": await cab(message, state); return
    await bot.send_message(OWNER_ID, f"📩 <b>СООБЩЕНИЕ ОТ АРТИСТА {message.from_user.id}:</b>\n{message.text}")
    await message.answer("✅ Отправлено.")

@dp.callback_query(F.data == "back_to_cab")
async def b_cab(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await cab(callback.message, state)

@dp.callback_query(F.data == "cab_pay")
async def cab_pay(callback: types.CallbackQuery, state: FSMContext):
    i = get_driver_info(callback.from_user.id)
    b = get_driver_info(OWNER_ID)
    await callback.message.answer(f"💸 Комиссия сервиса: <b>{i[3]}₽</b>\nПеревод Продюсеру: <b>{b[2]}</b>")
    await callback.answer()

# ==========================================
# 📜 CRAZY МЕНЮ (VIEW)
# ==========================================
@dp.message(F.text == "📜 CRAZY МЕНЮ (Категории)")
async def show_cats(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    did = get_linked_driver(message.from_user.id)
    if not did:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Я В МАШИНЕ (ВВЕСТИ КОД)", callback_data="enter_code_dialog")],[InlineKeyboardButton(text="👀 ВИТРИНА", callback_data="start_showcase")]])
        return await message.answer("🚖 <b>Введите код Артиста:</b>", reply_markup=kb)
    
    act_def, customs = get_driver_menu(did)
    spent, trips, unlocked = get_client_stats(message.from_user.id)
    btns = []
    for i, n in CATEGORIES.items():
        if i == 4 and not unlocked and trips < VIP_LIMIT:
            btns.append([InlineKeyboardButton(text=f"🔒 {n} (Нужен VIP код)", callback_data="locked_vip")])
            continue
        # Показываем категорию, если в ней есть хоть одна услуга
        if any(v['cat']==i and k in act_def for k,v in CRAZY_SERVICES.items()) or any(c[1]==i for c in customs):
            btns.append([InlineKeyboardButton(text=n, callback_data=f"cat_{i}")])
    await message.answer("🔥 <b>ВЫБЕРИТЕ УРОВЕНЬ БЕЗУМИЯ:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "enter_code_dialog")
async def enter_cd(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите код:")
    await state.set_state(UnlockMenu.waiting_for_key)

@dp.callback_query(F.data == "start_showcase")
async def start_sc(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(showcase=True)
    btns = [[InlineKeyboardButton(text=n, callback_data=f"cat_{i}")] for i, n in CATEGORIES.items()]
    await callback.message.edit_text("👀 <b>ВИТРИНА (Демо):</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "locked_vip")
async def l_vip(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("⛔ Введите VIP-код водителя!", show_alert=True)

@dp.callback_query(F.data.startswith("cat_"))
async def cat_op(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[1])
    d = await state.get_data()
    showcase = d.get('showcase')
    did = get_linked_driver(callback.from_user.id)
    btns = []
    if showcase:
        [btns.append([InlineKeyboardButton(text=f"{v['name']} — {v['price']}₽", callback_data=f"srv_{k}")]) for k,v in CRAZY_SERVICES.items() if v['cat']==cid]
    else:
        act_def, customs = get_driver_menu(did)
        [btns.append([InlineKeyboardButton(text=f"{v['name']} — {v['price']}₽", callback_data=f"srv_{k}")]) for k,v in CRAZY_SERVICES.items() if v['cat']==cid and k in act_def]
        [btns.append([InlineKeyboardButton(text=f"★ {cs[2]} — {cs[4]}₽", callback_data=f"custsrv_{cs[0]}")]) for cs in customs if cs[1]==cid]
    btns.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_c")])
    await callback.message.edit_text(f"📂 <b>{CATEGORIES[cid]}</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "back_c")
async def back_c(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await show_cats(callback.message, state)

@dp.callback_query(F.data.startswith("srv_"))
async def srv_sel(callback: types.CallbackQuery, state: FSMContext):
    k = callback.data.split("_")[1]; v = CRAZY_SERVICES[k]; d = await state.get_data()
    btn = "✅ ЗАКАЗАТЬ ШОУ" if not d.get('showcase') else "🔒 В ПОЕЗДКЕ"
    cb = f"do_{k}" if not d.get('showcase') else "al_sc"
    await callback.message.edit_text(f"🎭 <b>{v['name']}</b>\n💰 {v['price']}₽\n<i>{v['desc']}</i>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn, callback_data=cb)],[InlineKeyboardButton(text="🔙", callback_data=f"cat_{v['cat']}")]]))

@dp.callback_query(F.data.startswith("custsrv_"))
async def srv_cust(callback: types.CallbackQuery, state: FSMContext):
    sid = int(callback.data.split("_")[1])
    conn = sqlite3.connect(DB_PATH)
    srv = conn.execute("SELECT name, description, price, category_id FROM custom_services WHERE id=?", (sid,)).fetchone()
    conn.close()
    if not srv: return await callback.answer("Удалено")
    d = await state.get_data()
    btn = "✅ ЗАКАЗАТЬ ШОУ" if not d.get('showcase') else "🔒 В ПОЕЗДКЕ"
    cb = f"docust_{sid}" if not d.get('showcase') else "al_sc"
    await callback.message.edit_text(f"🎭 <b>{srv[0]}</b>\n💰 {srv[2]}₽\n<i>{srv[1]}</i>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn, callback_data=cb)],[InlineKeyboardButton(text="🔙", callback_data=f"cat_{srv[3]}")]]))

@dp.callback_query(F.data == "al_sc")
async def al_sc(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Это демо! Сядьте в машину.", show_alert=True)

@dp.callback_query(F.data.startswith("do_"))
async def do_ord(callback: types.CallbackQuery, state: FSMContext):
    k = callback.data.split("_")[1]; cid = callback.from_user.id; did = get_linked_driver(cid); v = CRAZY_SERVICES[k]
    active_orders[cid] = {"type":"crazy", "status":"pending", "price":str(v['price']), "driver_id":did}
    await bot.send_message(did, f"🔔 <b>ЗАКАЗ: {v['name']}</b>\n💰 {v['price']}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"t_ok_{cid}"), InlineKeyboardButton(text="💬 ЧАТ", callback_data="enter_chat")]]))
    await callback.message.edit_text("⏳ Ждем подтверждения...")

@dp.callback_query(F.data.startswith("docust_"))
async def do_cust(callback: types.CallbackQuery, state: FSMContext):
    sid = int(callback.data.split("_")[1]); cid = callback.from_user.id; did = get_linked_driver(cid)
    conn = sqlite3.connect(DB_PATH)
    srv = conn.execute("SELECT name, price FROM custom_services WHERE id=?", (sid,)).fetchone()
    conn.close()
    active_orders[cid] = {"type":"crazy", "status":"pending", "price":str(srv[1]), "driver_id":did}
    await bot.send_message(did, f"🔔 <b>ЗАКАЗ: {srv[0]}</b>\n💰 {srv[1]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"t_ok_{cid}"), InlineKeyboardButton(text="💬 ЧАТ", callback_data="enter_chat")]]))
    await callback.message.edit_text("⏳ Ждем подтверждения...")

# --- ORDER & PAYMENT LOGIC ---
@dp.callback_query(F.data.startswith("t_ok_"))
async def t_ok(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2]); did = callback.from_user.id; o = active_orders.get(cid)
    if not o or o.get("status") != "pending": return await callback.answer("Занято!")
    o["status"] = "accepted"; o["driver_id"] = did; set_linked_driver(cid, did); info = get_driver_info(did)
    for aid, mid in o.get('admin_msg_ids', {}).items():
        try: await bot.edit_message_text(chat_id=aid, message_id=mid, text=f"🚫 <b>ВЗЯЛ: {info[7]}</b>", reply_markup=None)
        except: pass
    await callback.message.edit_text(f"✅ Взято. Клиент: {o.get('phone', 'Crazy')}"); await cab(callback.message, state)
    await bot.send_message(cid, f"🎭 <b>АРТИСТ ГОТОВ!</b>\n👤 {info[7]}\n🚘 {info[1]}\n💰 {o['price']}₽", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 ЧАТ", callback_data="enter_chat"), InlineKeyboardButton(text="💸 ОПЛАТИЛ", callback_data=f"cli_pay_{cid}"), InlineKeyboardButton(text="➕ ЗАЕЗД", callback_data="add_stop"), InlineKeyboardButton(text="🆘 SOS", callback_data=f"sos_{did}")]]) )

@dp.callback_query(F.data.startswith("cli_pay_"))
async def cli_pay(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2]); did = active_orders[cid]['driver_id']
    await bot.send_message(did, "💸 <b>Оплата!</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data=f"drv_confirm_{cid}"), InlineKeyboardButton(text="❌ НЕ ПРИШЛО", callback_data=f"drv_deny_{cid}")]]))
    await callback.message.edit_text("⏳ Ждем подтверждения...")

@dp.callback_query(F.data.startswith("drv_confirm_"))
async def drv_con(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2])
    if cid in active_orders: update_client_after_trip(cid, extract_price(active_orders[cid]['price']))
    await bot.send_message(cid, "✅ <b>Принято!</b>")
    await callback.message.edit_text("✅ Принято.")

@dp.callback_query(F.data.startswith("drv_deny_"))
async def drv_d(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2])
    await bot.send_message(cid, "❌ <b>Нет оплаты!</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 ПОВТОРИТЬ", callback_data=f"cli_pay_{cid}")]]))
    await callback.message.edit_text("❌")

@dp.callback_query(F.data.startswith("ask_finish_"))
async def ask_fin(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2])
    await bot.send_message(cid, "🏁 <b>Финал! Оценка:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⭐ 5", callback_data=f"rate_{cid}_5")]]))
    await callback.message.edit_text("✅")
    await unlink_client(cid)
    await cab(callback.message, state)

@dp.callback_query(F.data.startswith("rate_"))
async def rate(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[1]); o = active_orders.get(cid)
    if o:
        did = o['driver_id']; pr = extract_price(o['price']); log_order(cid, did, "Шоу", pr); update_order_rating(5, did); add_commission(did, pr)
        await bot.send_message(did, "🎉 5⭐"); del active_orders[cid]
    await callback.message.edit_text("Спасибо!")

# --- TAXI SEARCH ---
@dp.message(F.text == "🎭 Найти Артиста (с авто)")
async def t_s(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("📍 <b>Где вы?</b>", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(OrderRide.waiting_for_from)

@dp.message(OrderRide.waiting_for_from)
async def t_f(message: types.Message, state: FSMContext):
    await state.update_data(fr=message.text)
    await message.answer("🏁 <b>Куда?</b>")
    await state.set_state(OrderRide.waiting_for_to)

@dp.message(OrderRide.waiting_for_to)
async def t_t(message: types.Message, state: FSMContext):
    await state.update_data(to=message.text)
    await message.answer("📞 <b>Телефон:</b>")
    await state.set_state(OrderRide.waiting_for_phone)

@dp.message(OrderRide.waiting_for_phone)
async def t_p(message: types.Message, state: FSMContext):
    await state.update_data(ph=message.text)
    await message.answer("💰 <b>Цена?</b>")
    await state.set_state(OrderRide.waiting_for_price)

@dp.message(OrderRide.waiting_for_price)
async def t_end(message: types.Message, state: FSMContext):
    d = await state.get_data(); cid = message.from_user.id
    active_orders[cid] = {"type":"taxi", "status":"pending", "price":message.text, "from":d['fr'], "to":d['to'], "phone":d['ph']}
    await message.answer("✅ <b>Ищем Артиста...</b>", reply_markup=main_kb); await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"t_ok_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"t_bid_{cid}")]])
    
    adm = get_all_admins_ids(); msg_map = {}
    for a in adm:
        try: m = await bot.send_message(a, f"🎭 {d['fr']} -> {d['to']}\n💰 {message.text}", reply_markup=kb); msg_map[a] = m.message_id
        except: pass
    active_orders[cid]['admin_msg_ids'] = msg_map
    tasks = [safe_send_message(d, f"🎭 {d['fr']} -> {d['to']}\n💰 {message.text}", kb) for d in get_active_drivers() if d not in adm]
    if tasks: await asyncio.gather(*tasks)

# --- EXTRAS ---
@dp.callback_query(F.data.startswith("sos_"))
async def sos_btn(callback: types.CallbackQuery, state: FSMContext):
    did = int(callback.data.split("_")[1]); cid = callback.from_user.id
    for aid in get_all_admins_ids(): await safe_send_message(aid, f"🆘 <b>SOS!</b>\nКлиент: {cid}\nВодитель: {did}")
    await callback.answer("🚨 SOS ОТПРАВЛЕН!", show_alert=True)

@dp.callback_query(F.data.startswith("t_bid_"))
async def cnt_s(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(cid=int(callback.data.split("_")[2]))
    await callback.message.answer("Ваша цена:")
    await state.set_state(DriverCounterOffer.waiting_for_offer)

@dp.message(DriverCounterOffer.waiting_for_offer)
async def cnt_snd(message: types.Message, state: FSMContext):
    d = await state.get_data(); cid = d['cid']
    await bot.send_message(cid, f"⚡ <b>Предложение:</b> {message.text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"t_ok_{cid}")] ])); await message.answer("Отправлено."); await state.clear()

@dp.callback_query(F.data == "add_stop")
async def add_stop(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Адрес:")
    await state.set_state(AddStop.waiting_for_address)

@dp.message(AddStop.waiting_for_address)
async def add_stop_p(message: types.Message, state: FSMContext):
    await state.update_data(a=message.text)
    await message.answer("Доплата:")
    await state.set_state(AddStop.waiting_for_price)

@dp.message(AddStop.waiting_for_price)
async def add_stop_f(message: types.Message, state: FSMContext):
    d = await state.get_data(); cid = message.from_user.id; did = active_orders[cid]['driver_id']
    await bot.send_message(did, f"📍 <b>Заезд:</b> {d['a']}\n💰 +{message.text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"stop_ok_{cid}_{message.text}")]])); await message.answer("⏳"); await state.clear()

@dp.callback_query(F.data.startswith("stop_ok_"))
async def stop_ok(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2]); pr = int(callback.data.split("_")[3]); active_orders[cid]['price'] = str(extract_price(active_orders[cid]['price']) + pr)
    await bot.send_message(cid, f"✅ <b>Принято!</b> Итог: {active_orders[cid]['price']}"); await callback.message.edit_text("✅")

# --- REGISTRATION ---
@dp.message(Command("driver", "drive"))
async def reg_s(message: types.Message, state: FSMContext):
    if get_driver_info(message.from_user.id): return await message.answer("Уже есть.")
    await state.clear(); await message.answer("ФИО:"); await state.set_state(DriverRegistration.waiting_for_fio)

@dp.message(DriverRegistration.waiting_for_fio)
async def reg_f(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await message.answer("Авто:")
    await state.set_state(DriverRegistration.waiting_for_car)

@dp.message(DriverRegistration.waiting_for_car)
async def reg_c(message: types.Message, state: FSMContext):
    await state.update_data(car=message.text)
    await message.answer("Реквизиты:")
    await state.set_state(DriverRegistration.waiting_for_payment_info)

@dp.message(DriverRegistration.waiting_for_payment_info)
async def reg_r(message: types.Message, state: FSMContext):
    await state.update_data(pay=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Пропустить")]], resize_keyboard=True)
    await message.answer("Промокод (если есть):", reply_markup=kb)
    await state.set_state(DriverRegistration.waiting_for_referral)

@dp.message(DriverRegistration.waiting_for_referral)
async def reg_p(message: types.Message, state: FSMContext):
    ref_code = message.text.strip().upper() if message.text != "Пропустить" else None
    await state.update_data(ref=ref_code)
    await message.answer("Придумайте Ваш Код-пароль:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(DriverRegistration.waiting_for_code)

@dp.message(DriverRegistration.waiting_for_code)
async def reg_fin(message: types.Message, state: FSMContext):
    c = message.text.upper().strip(); d = await state.get_data(); conn = sqlite3.connect(DB_PATH)
    if conn.execute("SELECT 1 FROM drivers WHERE access_code=? AND user_id!=?", (c, message.from_user.id)).fetchone(): return await message.answer("❌ Занят!")
    
    # PROMO & REFERRAL LOGIC
    ref_id = None
    start_comm = DEFAULT_COMMISSION
    end_date = None
    
    if d.get('ref'):
        promo = conn.execute("SELECT commission, duration FROM promo_codes WHERE code=?", (d['ref'],)).fetchone()
        if promo:
            start_comm = promo[0]
            end_date = datetime.now() + timedelta(days=promo[1])
        else:
            inviter = conn.execute("SELECT user_id, commission FROM drivers WHERE access_code=?", (d['ref'],)).fetchone()
            if inviter:
                ref_id = inviter[0]
                start_comm = 5 # Referral Promo
                end_date = datetime.now() + timedelta(days=30)
                new_comm_inv = max(MIN_COMMISSION, inviter[1] - 1)
                conn.execute("UPDATE drivers SET commission = ? WHERE user_id = ?", (new_comm_inv, ref_id))
                await safe_send_message(ref_id, f"🎉 <b>РЕФЕРАЛ!</b> Друг зарегистрировался.\nВаша комиссия: <b>{new_comm_inv}%</b>")

    vip = generate_vip_code(d['fio'])
    conn.execute("INSERT OR REPLACE INTO drivers (user_id, username, fio, car_info, payment_info, access_code, vip_code, status, referred_by, commission, promo_end_date) VALUES (?,?,?,?,?,?,?, 'pending', ?, ?, ?)", 
                 (message.from_user.id, message.from_user.username, d['fio'], d['car'], d['pay'], c, vip, ref_id, start_comm, end_date))
    conn.commit(); conn.close(); init_driver_services_defaults(message.from_user.id)
    
    msg = f"✅ Заявка! VIP-промо: {vip}\nКомиссия: {start_comm}%"
    if end_date: msg += f" (до {end_date.strftime('%d.%m')})"
    await message.answer(msg); await state.clear()
    
    for a in get_all_admins_ids(): await safe_send_message(a, f"🚨 НОВЫЙ: {d['fio']}", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"adm_app_{message.from_user.id}")]]))

# --- KEY ---
@dp.message(UnlockMenu.waiting_for_key)
async def key_fin(message: types.Message, state: FSMContext):
    code = message.text.strip().upper(); conn = sqlite3.connect(DB_PATH)
    drv = conn.execute("SELECT user_id, fio FROM drivers WHERE access_code=? AND status='active'", (code,)).fetchone()
    if drv:
        set_linked_driver(message.from_user.id, drv[0]); await message.answer(f"🔓 Вход. Артист: {drv[1]}", reply_markup=main_kb)
    else:
        drv = conn.execute("SELECT user_id, fio FROM drivers WHERE vip_code=? AND status='active'", (code,)).fetchone()
        if drv:
            set_linked_driver(message.from_user.id, drv[0]); unlock_vip_for_client(message.from_user.id)
            await message.answer(f"💎 <b>VIP!</b> Артист: {drv[1]}", reply_markup=main_kb)
        else: await message.answer("❌ Неверно.")
    conn.close(); await state.clear()

# --- ADMIN ---
@dp.message(Command("admin"))
async def adm(message: types.Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id): return await message.answer("⛔")
    conn = sqlite3.connect(DB_PATH); drs = conn.execute("SELECT user_id, fio, balance, commission FROM drivers").fetchall(); conn.close()
    txt = "👑 <b>ПРОДЮСЕРСКИЙ ЦЕНТР</b>\n" + "\n".join([f"• {d[1]} | {d[2]}₽ | {d[3]}% | /edit_{d[0]}" for d in drs])
    kb = [[InlineKeyboardButton(text="📢 РАССЫЛКА", callback_data="admin_broadcast"), InlineKeyboardButton(text="🎟 Создать Промокод", callback_data="create_promo")]]
    await message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.message(F.text.startswith("/edit_"))
async def ed(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    did = int(message.text.split("_")[1]); await state.update_data(target_did=did)
    await message.answer("Действие:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Счет", callback_data=f"adm_bill_{did}"), InlineKeyboardButton(text="📉 Комиссия", callback_data=f"adm_comm_{did}")]]))

@dp.callback_query(F.data == "create_promo")
async def cr_promo(callback: types.CallbackQuery, state: FSMContext): await callback.message.answer("Введите КОД (например START2026):"); await state.set_state(AdminPromo.code)
@dp.message(AdminPromo.code)
async def promo_c(message: types.Message, state: FSMContext): await state.update_data(c=message.text.upper()); await message.answer("Процент комиссии (число):"); await state.set_state(AdminPromo.comm)
@dp.message(AdminPromo.comm)
async def promo_p(message: types.Message, state: FSMContext): await state.update_data(p=int(message.text)); await message.answer("Длительность (дней):"); await state.set_state(AdminPromo.dur)
@dp.message(AdminPromo.dur)
async def promo_d(message: types.Message, state: FSMContext):
    d = await state.get_data(); conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO promo_codes (code, commission, duration) VALUES (?, ?, ?)", (d['c'], d['p'], int(message.text)))
    conn.commit(); conn.close(); await message.answer(f"✅ Промокод <b>{d['c']}</b> создан!\n{d['p']}% на {message.text} дней."); await state.clear()

@dp.callback_query(F.data.startswith("adm_comm_"))
async def adm_comm(callback: types.CallbackQuery, state: FSMContext): await callback.message.answer("Новый процент (число):"); await state.set_state(AdminEditComm.waiting_for_new_comm)
@dp.message(AdminEditComm.waiting_for_new_comm)
async def save_comm(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    d = await state.get_data(); update_driver_field(d['target_did'], "commission", int(message.text)); await message.answer("✅"); await state.clear()

@dp.callback_query(F.data.startswith("adm_bill_"))
async def bl(callback: types.CallbackQuery, state: FSMContext): await state.update_data(target_did=int(callback.data.split("_")[2])); await callback.message.answer("Текст:"); await state.set_state(AdminBilling.waiting_for_custom_req)
@dp.message(AdminBilling.waiting_for_custom_req)
async def bl_s(message: types.Message, state: FSMContext):
    d = await state.get_data(); await bot.send_message(d['target_did'], f"⚠️ <b>СЧЕТ:</b>\n{message.text}"); await message.answer("✅"); await state.clear()

@dp.callback_query(F.data.startswith("adm_app_"))
async def adm_app(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    did = int(callback.data.split("_")[2]); update_driver_field(did, "status", "active")
    await callback.message.edit_text("✅ Принят"); await safe_send_message(did, "🎉 Вы в труппе! /cab")

@dp.callback_query(F.data == "admin_broadcast")
async def brd(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Текст рассылки:")
    await state.set_state(AdminBroadcast.waiting_for_text)

@dp.message(AdminBroadcast.waiting_for_text)
async def brd_s(message: types.Message, state: FSMContext):
    count = 0
    for d in get_active_drivers():
        if await safe_send_message(d, f"📢 <b>НОВОСТИ:</b>\n{message.text}"): count += 1
    await message.answer(f"✅ Доставлено: {count}"); await state.clear()

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
``````python
import asyncio
import logging
import os
import sqlite3
import re
import random
import string
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties

# ==========================================
# ⚙️ 1. ГЛОБАЛЬНЫЕ НАСТРОЙКИ
# ==========================================
logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("API_TOKEN")
OWNER_ID_STR = os.getenv("DRIVER_ID") 

if not API_TOKEN or not OWNER_ID_STR:
    exit("⛔ CRITICAL ERROR: Token or ID missing in Environment Variables")

OWNER_ID = int(OWNER_ID_STR)
SECOND_ADMIN_ID = 6004764782
SUPER_ADMINS = [OWNER_ID, SECOND_ADMIN_ID]

VIP_LIMIT = 10          # Поездок для открытия VIP категории
MIN_COMMISSION = 4      # Минимально возможная комиссия (%)
DEFAULT_COMMISSION = 10 # Стартовая комиссия (%)
LAWYER_LINK = "https://t.me/Ai_advokatrobot"

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Кэш активных заказов в памяти (для скорости)
active_orders = {} 

# ==========================================
# 📜 2. КОНТЕНТ И АТМОСФЕРА
# ==========================================
LEGAL_TEXT = (
    "<b>📜 ПУБЛИЧНАЯ ОФЕРТА И ПРАВИЛА ИГРЫ</b>\n\n"
    "1. <b>Концепция:</b> Вы находитесь на агрегаторе иммерсивных шоу. Водитель — это Артист. Машина — это Сцена.\n"
    "2. <b>Отказ от ответственности:</b> Сервис является информационным посредником. Мы соединяем таланты и поклонников.\n"
    "3. <b>Безопасность:</b> Если шоу выходит из-под контроля — жмите кнопку «АДВОКАТ».\n"
    "4. <b>Финансы:</b> Оплата поездки является добровольным пожертвованием (донатом) на развитие творчества Артиста."
)

WELCOME_TEXT = (
    "🎪 <b>ДОБРО ПОЖАЛОВАТЬ В ТЕАТР НА КОЛЕСАХ!</b>\n\n"
    "Устал от молчаливых таксистов и скучных поездок?\n"
    "Здесь ты платишь не за километры, а за <b>ЭМОЦИИ</b>.\n\n"
    "🎭 <b>В нашем репертуаре:</b>\n"
    "• Водитель-Психолог (выслушает)\n"
    "• Танцы на капоте (взбодрит)\n"
    "• Ограбление (понарошку, адреналин)\n\n"
    "⚖️ <i>Генеральный спонсор — <a href='https://t.me/Ai_advokatrobot'>Робот-Адвокат</a>. Вытащит, если вечеринка зайдет слишком далеко.</i>\n\n"
    "<b>Готовы подписать контракт?</b> 👇"
)

# Базовые услуги (Вшиты в код, нельзя удалить, только отключить)
CRAZY_SERVICES = {
    "candy": {"cat": 1, "price": 0, "name": "🍬 Презент", "desc": "Артист с лицом дипломата вручает вам элитную барбариску."},
    "nose": {"cat": 1, "price": 300, "name": "👃 Палец в носу", "desc": "Всю поездку Артист едет с пальцем в носу. Вы платите за его унижение."},
    "butler": {"cat": 1, "price": 200, "name": "🤵 Дворецкий", "desc": "Вам открывают дверь, кланяются и называют 'Ваше Высочество'."},
    "joke": {"cat": 1, "price": 50, "name": "🤡 Тупой анекдот", "desc": "Шутка из 90-х. Смеяться обязательно, чтобы не обидеть творца."},
    "silence": {"cat": 1, "price": 150, "name": "🤐 Режим 'Ниндзя'", "desc": "Полная тишина. Музыка выкл. Водитель общается жестами."},
    "granny": {"cat": 2, "price": 800, "name": "👵 Бабуля", "desc": "Ворчание всю дорогу: 'Наркоманы!', 'Шапку надень!', 'Раньше было лучше'."},
    "gopnik": {"cat": 2, "price": 500, "name": "🍺 Пацанчик", "desc": "Русский рэп, семечки, решение вопросиков по телефону громко."},
    "guide": {"cat": 2, "price": 600, "name": "🗣 Горе-Гид", "desc": "Экскурсия с выдуманными фактами о каждой столбе."},
    "psych": {"cat": 2, "price": 1000, "name": "🧠 Психолог", "desc": "Вы ноете про жизнь и бывших, Артист кивает и дает житейские советы."},
    "spy": {"cat": 3, "price": 2000, "name": "🕵️‍♂️ Агент 007", "desc": "Черные очки, проверка хвоста, шифрованные переговоры по рации."},
    "karaoke": {"cat": 3, "price": 5000, "name": "🎤 Адское Караоке", "desc": "Орем песни дуэтом на всю улицу. Фальшиво, но с душой."},
    "dance": {"cat": 3, "price": 15000, "name": "💃 Танцы на капоте", "desc": "На красном светофоре Артист танцует макарену перед авто."},
    "kidnap": {"cat": 4, "price": 30000, "name": "🎭 Похищение", "desc": "Вас (понарошку) грузят в багажник и везут в лес пить чай."},
    "tarzan": {"cat": 4, "price": 50000, "name": "🦍 Тарзан", "desc": "Удары в грудь, рычание на прохожих, животная энергия."},
    "burn": {"cat": 4, "price": 1000000, "name": "🔥 Сжечь авто", "desc": "Едем на пустырь. Вы платите миллион. Мы сжигаем реквизит (машину)."},
    "eyes": {"cat": 5, "price": 0, "name": "👁️ Глаз-алмаз", "desc": "Изысканный комплимент вашим глазам."},
    "smile": {"cat": 5, "price": 0, "name": "😁 Улыбка", "desc": "Комплимент вашей улыбке."},
    "style": {"cat": 5, "price": 0, "name": "👠 Икона стиля", "desc": "Восхищение вашим образом."},
    "improv": {"cat": 5, "price": 0, "name": "✨ Импровизация", "desc": "Артист сам найдет, за что вас похвалить."},
    "propose": {"cat": 5, "price": 1000, "name": "💍 Предложение", "desc": "Вы делаете предложение Артисту. Шанс 50/50. Деньги не возвращаются."}
}

CATEGORIES = {1: "🟢 ЛАЙТ", 2: "🟡 МЕДИУМ", 3: "🔴 ХАРД", 4: "☠️ VIP БЕЗУМИЕ", 5: "🌹 ДЛЯ ДАМ"}

# ==========================================
# 🗄️ 3. БАЗА ДАННЫХ
# ==========================================
DB_PATH = "/data/taxi_db.sqlite" if os.path.exists("/data") else "taxi_db.sqlite"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Таблица Водителей (Артистов)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS drivers (
                user_id INTEGER PRIMARY KEY,
                username TEXT, fio TEXT, car_info TEXT, payment_info TEXT,
                access_code TEXT UNIQUE, vip_code TEXT UNIQUE,
                status TEXT DEFAULT 'pending', role TEXT DEFAULT 'driver',
                balance INTEGER DEFAULT 0, rating_sum INTEGER DEFAULT 0, rating_count INTEGER DEFAULT 0, 
                commission INTEGER DEFAULT 10,
                referred_by INTEGER,
                promo_end_date TIMESTAMP
            )
        """)
        # Таблица Стандартных Услуг (вкл/выкл)
        cursor.execute("CREATE TABLE IF NOT EXISTS driver_services (driver_id INTEGER, service_key TEXT, is_active BOOLEAN DEFAULT 1, PRIMARY KEY (driver_id, service_key))")
        # Таблица Кастомных Услуг (SaaS)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS custom_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_id INTEGER, category_id INTEGER, name TEXT, description TEXT, price INTEGER
            )
        """)
        # Таблица Промокодов Админа
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                code TEXT PRIMARY KEY,
                commission INTEGER,
                duration INTEGER
            )
        """)
        # Таблица Клиентов (Зрителей)
        cursor.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER DEFAULT NULL, total_spent INTEGER DEFAULT 0, trips_count INTEGER DEFAULT 0, vip_unlocked BOOLEAN DEFAULT 0)")
        # История Заказов
        cursor.execute("CREATE TABLE IF NOT EXISTS order_history (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, driver_id INTEGER, service_name TEXT, price INTEGER, rating INTEGER DEFAULT 0, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        
        # Создание Админов
        for admin_id in SUPER_ADMINS:
            try:
                cursor.execute("INSERT OR IGNORE INTO drivers (user_id, username, fio, car_info, payment_info, access_code, vip_code, status, role, commission) VALUES (?, 'BOSS', 'Продюсер', 'VIP', 'CASH', ?, ?, 'active', 'owner', 0)", 
                               (admin_id, f"ADMIN_{admin_id}", f"VIP_BOSS_{admin_id}"))
                cursor.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (admin_id,))
                for key in CRAZY_SERVICES:
                    cursor.execute("INSERT OR REPLACE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, 1)", (admin_id, key))
            except: pass
        conn.commit()

init_db()

# ==========================================
# 🛠 4. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def generate_vip_code(name):
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"VIP-{name.split()[0].upper()}-{suffix}"

def is_client_accepted(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute("SELECT 1 FROM clients WHERE user_id = ?", (user_id,)).fetchone()
    return bool(res)

def get_client_stats(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute("SELECT total_spent, trips_count, vip_unlocked FROM clients WHERE user_id=?", (user_id,)).fetchone()
    return res if res else (0, 0, 0)

def unlock_vip_for_client(client_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE clients SET vip_unlocked = 1 WHERE user_id=?", (client_id,))

def update_client_after_trip(user_id, amount):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE clients SET total_spent = total_spent + ?, trips_count = trips_count + 1 WHERE user_id=?", (amount, user_id))

def get_status_name(spent, trips, vip_unlocked):
    if vip_unlocked: return "👹 МЕЦЕНАТ ХАОСА (VIP)"
    if trips >= VIP_LIMIT: return "💀 ВЕТЕРАН БЕЗУМИЯ"
    if trips > 3: return "🤪 ЦЕНИТЕЛЬ"
    return "👶 ЗРИТЕЛЬ"

def get_driver_menu(driver_id):
    with sqlite3.connect(DB_PATH) as conn:
        active_keys = [r[0] for r in conn.execute("SELECT service_key FROM driver_services WHERE driver_id=? AND is_active=1", (driver_id,)).fetchall()]
        customs = conn.execute("SELECT id, category_id, name, description, price FROM custom_services WHERE driver_id=?", (driver_id,)).fetchall()
    return active_keys, customs

def get_driver_info(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute("SELECT username, car_info, payment_info, balance, status, access_code, role, fio, rating_sum, rating_count, vip_code, commission, promo_end_date FROM drivers WHERE user_id=?", (user_id,)).fetchone()
    return res

def get_linked_driver(client_id):
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute("SELECT linked_driver_id FROM clients WHERE user_id=?", (client_id,)).fetchone()
    return res[0] if res and res[0] else None

def set_linked_driver(client_id, driver_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO clients (user_id, linked_driver_id, total_spent, trips_count, vip_unlocked) VALUES (?, ?, (SELECT total_spent FROM clients WHERE user_id=?), (SELECT trips_count FROM clients WHERE user_id=?), (SELECT vip_unlocked FROM clients WHERE user_id=?))", (client_id, driver_id, client_id, client_id, client_id))

def unlink_client(client_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE clients SET linked_driver_id = NULL WHERE user_id=?", (client_id,))

def init_driver_services_defaults(driver_id):
    with sqlite3.connect(DB_PATH) as conn:
        for k in CRAZY_SERVICES:
            conn.execute("INSERT OR IGNORE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, 1)", (driver_id, k))

def toggle_driver_service(driver_id, service_key):
    with sqlite3.connect(DB_PATH) as conn:
        curr = conn.execute("SELECT is_active FROM driver_services WHERE driver_id=? AND service_key=?", (driver_id, service_key)).fetchone()
        new_status = 0 if (curr and curr[0] == 1) else 1
        conn.execute("INSERT OR REPLACE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, ?)", (driver_id, service_key, new_status))

def delete_custom_service(service_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM custom_services WHERE id=?", (service_id,))

def get_all_admins_ids():
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute("SELECT user_id FROM drivers WHERE role IN ('owner', 'admin') AND status='active'").fetchall()
    return list(set([r[0] for r in res] + SUPER_ADMINS))

def get_active_drivers():
    with sqlite3.connect(DB_PATH) as conn:
        res = [d[0] for d in conn.execute("SELECT user_id FROM drivers WHERE status='active'").fetchall()]
    return res

def update_driver_field(user_id, field, value):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(f"UPDATE drivers SET {field} = ? WHERE user_id = ?", (value, user_id))

def extract_price(text):
    nums = re.findall(r'\d+', str(text))
    return int("".join(nums)) if nums else 0

def log_order(client_id, driver_id, service_name, price):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO order_history (client_id, driver_id, service_name, price) VALUES (?, ?, ?, ?)", (client_id, driver_id, service_name, price))

def update_order_rating(rating, driver_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE drivers SET rating_sum = rating_sum + ?, rating_count = rating_count + 1 WHERE user_id = ?", (rating, driver_id))

def check_and_reset_promo(driver_id):
    """Проверяет таймер промо-комиссии и пересчитывает, если истек"""
    info = get_driver_info(driver_id)
    if info and info[12]: # promo_end_date
        end_date = datetime.strptime(info[12], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > end_date:
            with sqlite3.connect(DB_PATH) as conn:
                # Считаем скидку за рефералов (1 друг = -1%, но не ниже 4%)
                ref_count = conn.execute("SELECT COUNT(*) FROM drivers WHERE referred_by=?", (driver_id,)).fetchone()[0]
                new_comm = max(MIN_COMMISSION, DEFAULT_COMMISSION - ref_count)
                conn.execute("UPDATE drivers SET commission = ?, promo_end_date = NULL WHERE user_id = ?", (new_comm, driver_id))

def add_commission(driver_id, amount):
    check_and_reset_promo(driver_id) # Сначала проверка таймера
    if is_admin(driver_id): return 
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT commission FROM drivers WHERE user_id=?", (driver_id,)).fetchone()
        percent = row[0] if row else 10
        val = int(amount * (percent / 100))
        conn.execute("UPDATE drivers SET balance = balance + ? WHERE user_id=?", (val, driver_id))

async def safe_send_message(chat_id, text, reply_markup=None):
    try: await bot.send_message(chat_id, text, reply_markup=reply_markup); return True
    except: return False

async def check_tos(message: types.Message) -> bool:
    if not is_client_accepted(message.from_user.id): 
        await message.answer("🛑 <b>Сначала нажмите /start!</b>")
        return False
    return True

# ==========================================
# 5. FSM STATES
# ==========================================
class OrderRide(StatesGroup): waiting_for_from = State(); waiting_for_to = State(); waiting_for_phone = State(); waiting_for_price = State()
class DriverRegistration(StatesGroup): waiting_for_fio = State(); waiting_for_car = State(); waiting_for_payment_info = State(); waiting_for_referral = State(); waiting_for_code = State()
class UnlockMenu(StatesGroup): waiting_for_key = State()
class AdminBilling(StatesGroup): waiting_for_custom_req = State()
class AdminEditComm(StatesGroup): waiting_for_new_comm = State()
class AdminBroadcast(StatesGroup): waiting_for_text = State()
class AdminPromo(StatesGroup): code = State(); comm = State(); dur = State()
class ChatState(StatesGroup): active = State()
class ChatWithBoss(StatesGroup): active = State()
class DriverEdit(StatesGroup): waiting_for_new_pay = State(); waiting_for_new_code = State()
class DriverCounterOffer(StatesGroup): waiting_for_offer = State()
class AddStop(StatesGroup): waiting_for_address = State(); waiting_for_price = State()
class AddCustomService(StatesGroup): name = State(); desc = State(); price = State(); cat = State()

# ==========================================
# 6. КЛАВИАТУРЫ
# ==========================================
main_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🎭 Найти Артиста (с авто)")],[KeyboardButton(text="📜 CRAZY МЕНЮ (Категории)")],[KeyboardButton(text="👤 Мой Кабинет"), KeyboardButton(text="⚖️ Вызвать адвоката")]], resize_keyboard=True)
tos_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПОДПИСАТЬ КРОВЬЮ", callback_data="accept_tos")],[InlineKeyboardButton(text="❌ Я слишком нормальный", callback_data="decline_tos")]])

# ==========================================
# 7. ЛОГИКА - КЛИЕНТ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if is_client_accepted(message.from_user.id): await message.answer("⚠️ <b>CRAZY MOOD:</b> С возвращением!", reply_markup=main_kb)
    else: await message.answer(WELCOME_TEXT, reply_markup=tos_kb)

@dp.callback_query(F.data == "accept_tos")
async def tos_accepted(callback: types.CallbackQuery, state: FSMContext):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO clients (user_id, trips_count) VALUES (?, 0)", (callback.from_user.id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("🔥 <b>ВЫ В ИГРЕ!</b>")
    await callback.message.answer("Выбирайте 👇", reply_markup=main_kb)

@dp.callback_query(F.data == "decline_tos")
async def tos_declined(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🚶‍♂️ Скука - это выбор.")

@dp.message(F.text == "📄 ОФЕРТА")
async def show_legal(message: types.Message, state: FSMContext):
    await message.answer(LEGAL_TEXT)

@dp.message(F.text == "⚖️ Вызвать адвоката")
async def lawyer_menu(message: types.Message, state: FSMContext):
    await message.answer("⚖️ <b>ЮРИДИЧЕСКИЙ ОТДЕЛ</b>\n<i>Когда шутка зашла слишком далеко...</i>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚨 ПЕРЕЙТИ", url=LAWYER_LINK)]]))

@dp.message(F.text == "👤 Мой Кабинет")
async def client_cab(message: types.Message, state: FSMContext):
    if not is_client_accepted(message.from_user.id): return await message.answer("/start")
    spent, trips, unlocked = get_client_stats(message.from_user.id)
    status = get_status_name(spent, trips, unlocked)
    
    progress = ""
    if not unlocked and trips < VIP_LIMIT:
        progress = f"\n🔒 До VIP уровня: <b>{VIP_LIMIT - trips} шоу</b>"
    elif unlocked or trips >= VIP_LIMIT:
        progress = "\n🔥 <b>VIP ДОСТУП ОТКРЫТ!</b>"
    
    conn = sqlite3.connect(DB_PATH)
    hist = conn.execute("SELECT service_name, price FROM order_history WHERE client_id=? ORDER BY id DESC LIMIT 5", (message.from_user.id,)).fetchall()
    conn.close()
    h_txt = "\n".join([f"▪ {h[0]} ({h[1]}₽)" for h in hist]) or "Нет истории."
    
    kb = []
    if message.from_user.id in active_orders: kb.append([InlineKeyboardButton(text="💬 ЧАТ С АРТИСТОМ", callback_data="enter_chat")])
    await message.answer(f"👤 <b>КАБИНЕТ ЗРИТЕЛЯ</b>\n👑 {status}\n💰 {spent}₽ | 🎬 {trips}\n{progress}\n\n📜 <b>ИСТОРИЯ:</b>\n{h_txt}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb) if kb else None)

# ==========================================
# 8. ЛОГИКА - АРТИСТ (ВОДИТЕЛЬ)
# ==========================================
@dp.message(Command("cab"))
async def cab(message: types.Message, state: FSMContext):
    await state.clear()
    i = get_driver_info(message.from_user.id)
    if not i: return await message.answer("❌ Нет регистрации. /drive")
    
    check_and_reset_promo(message.from_user.id)
    i = get_driver_info(message.from_user.id) # Re-fetch
    
    active_cid = None
    for cid, o in active_orders.items():
        if o.get('driver_id') == message.from_user.id: active_cid = cid; break
            
    kb = [
        [InlineKeyboardButton(text="🎛 Мой Репертуар (Услуги)", callback_data="driver_menu_edit")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="driver_settings"), InlineKeyboardButton(text="📊 История", callback_data="driver_history")],
        [InlineKeyboardButton(text="🤝 Реферальная программа", callback_data="driver_referral")],
        [InlineKeyboardButton(text="🆘 Чат с Продюсером", callback_data="chat_with_boss")]
    ]
    
    status_txt = "📴 Статус: Свободен"
    if active_cid:
        status_txt = f"🎬 <b>В ЭФИРЕ (Зритель {active_cid})</b>"
        kb.insert(0, [InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ СЕАНС", callback_data=f"ask_finish_{active_cid}")])
        kb.insert(1, [InlineKeyboardButton(text="💬 ЧАТ С ЗРИТЕЛЕМ", callback_data="enter_chat")])
    
    kb.append([InlineKeyboardButton(text="💎 Мой VIP-код для клиентов", callback_data="show_vip_code")])
    kb.append([InlineKeyboardButton(text="💸 Баланс / Продюсер", callback_data="cab_pay")])
    
    promo_info = ""
    if i[12]: promo_info = f" (Промо до {i[12]})"
    
    await message.answer(f"🪪 <b>ГРИМЕРКА: {i[7]}</b>\n💰 Долг: {i[3]}₽\n🔑 Код доступа: <code>{i[5]}</code>\n⭐ Рейтинг: {i[8]}\n📉 Комиссия: <b>{i[11]}%</b>{promo_info}\n━━━━━━━━━━━━\n{status_txt}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- РЕФЕРАЛКА ---
@dp.callback_query(F.data == "driver_referral")
async def driver_ref(callback: types.CallbackQuery, state: FSMContext):
    i = get_driver_info(callback.from_user.id)
    await callback.message.answer(f"🤝 <b>ПАРТНЕРСКАЯ ПРОГРАММА</b>\n\nПриводи друзей-водителей и снижай комиссию!\nТвоя текущая комиссия: <b>{i[11]}%</b>\nМинимальная комиссия: <b>{MIN_COMMISSION}%</b>\n\nТвой код для приглашения: <code>{i[5]}</code>\n(Друг должен ввести его при регистрации).")
    await callback.answer()

# --- МЕНЮ (КАСТОМ + ДЕФОЛТ) ---
@dp.callback_query(F.data == "driver_menu_edit")
async def d_menu(callback: types.CallbackQuery, state: FSMContext):
    act, customs = get_driver_menu(callback.from_user.id)
    kb = []
    for k, v in CRAZY_SERVICES.items():
        status = "✅" if k in act else "❌"
        kb.append([InlineKeyboardButton(text=f"{status} {v['name']}", callback_data=f"tgl_{k}")])
    for cs in customs:
        kb.append([InlineKeyboardButton(text=f"🗑 {cs[2]} ({cs[4]}₽)", callback_data=f"del_cust_{cs[0]}")])
    kb.append([InlineKeyboardButton(text="➕ ДОБАВИТЬ СВОЮ УСЛУГУ", callback_data="add_custom_srv")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_cab")])
    await callback.message.edit_text("🎛 <b>КОНСТРУКТОР МЕНЮ:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "add_custom_srv")
async def add_cust_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("1. Название услуги:")
    await state.set_state(AddCustomService.name)

@dp.message(AddCustomService.name)
async def add_cust_n(message: types.Message, state: FSMContext):
    await state.update_data(n=message.text)
    await message.answer("2. Описание (коротко и ярко):")
    await state.set_state(AddCustomService.desc)

@dp.message(AddCustomService.desc)
async def add_cust_d(message: types.Message, state: FSMContext):
    await state.update_data(d=message.text)
    await message.answer("3. Цена (только число):")
    await state.set_state(AddCustomService.price)

@dp.message(AddCustomService.price)
async def add_cust_p(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число!")
    await state.update_data(p=int(message.text))
    btns = [[InlineKeyboardButton(text=n, callback_data=f"set_cat_{i}")] for i, n in CATEGORIES.items()]
    await message.answer("4. Выберите категорию сложности:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
    await state.set_state(AddCustomService.cat)

@dp.callback_query(F.data.startswith("set_cat_"))
async def add_cust_fin(callback: types.CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[2])
    d = await state.get_data()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO custom_services (driver_id, category_id, name, description, price) VALUES (?, ?, ?, ?, ?)", (callback.from_user.id, cat_id, d['n'], d['d'], d['p']))
    conn.commit()
    conn.close()
    await callback.message.answer("✅ Услуга добавлена в меню!")
    await d_menu(callback, state)

@dp.callback_query(F.data.startswith("del_cust_"))
async def del_cust(callback: types.CallbackQuery, state: FSMContext):
    delete_custom_service(int(callback.data.split("_")[2]))
    await d_menu(callback, state)

@dp.callback_query(F.data.startswith("tgl_"))
async def tgl(callback: types.CallbackQuery, state: FSMContext):
    toggle_driver_service(callback.from_user.id, callback.data.split("_")[1])
    await d_menu(callback, state)

# --- НАСТРОЙКИ ---
@dp.callback_query(F.data == "show_vip_code")
async def show_vip(callback: types.CallbackQuery, state: FSMContext):
    i = get_driver_info(callback.from_user.id)
    await callback.message.answer(f"💎 <b>VIP ПРОМОКОД:</b>\n<code>{i[10]}</code>\nДля клиентов.")
    await callback.answer()

@dp.callback_query(F.data == "driver_settings")
async def driver_settings(callback: types.CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Сменить реквизиты", callback_data="edit_pay")],[InlineKeyboardButton(text="🔑 Сменить Код", callback_data="edit_code")],[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_cab")]])
    await callback.message.edit_text("⚙️ <b>НАСТРОЙКИ:</b>", reply_markup=kb)

@dp.callback_query(F.data == "edit_pay")
async def edit_pay(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Новые реквизиты (Карта/Телефон):")
    await state.set_state(DriverEdit.waiting_for_new_pay)

@dp.message(DriverEdit.waiting_for_new_pay)
async def save_pay(message: types.Message, state: FSMContext):
    update_driver_field(message.from_user.id, "payment_info", message.text)
    await message.answer("✅ Сохранено")
    await cab(message, state)

@dp.callback_query(F.data == "edit_code")
async def edit_code(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Новый Код доступа:")
    await state.set_state(DriverEdit.waiting_for_new_code)

@dp.message(DriverEdit.waiting_for_new_code)
async def save_code(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    conn = sqlite3.connect(DB_PATH)
    if conn.execute("SELECT 1 FROM drivers WHERE access_code=? AND user_id!=?", (code, message.from_user.id)).fetchone():
        conn.close()
        return await message.answer("❌ Этот код уже занят!")
    conn.close()
    update_driver_field(message.from_user.id, "access_code", code)
    await message.answer("✅ Код изменен!")
    await cab(message, state)

@dp.callback_query(F.data == "driver_history")
async def driver_history(callback: types.CallbackQuery, state: FSMContext):
    conn = sqlite3.connect(DB_PATH)
    hist = conn.execute("SELECT service_name, price, date FROM order_history WHERE driver_id=? ORDER BY id DESC LIMIT 5", (callback.from_user.id,)).fetchall()
    conn.close()
    txt = "\n".join([f"▪ {h[0]} ({h[1]}₽)" for h in hist]) or "Пусто."
    await callback.message.edit_text(f"📊 <b>ВАША ИСТОРИЯ:</b>\n{txt}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙", callback_data="back_to_cab")]]))

@dp.callback_query(F.data == "chat_with_boss")
async def chat_boss(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ChatWithBoss.active)
    await callback.message.answer("✍️ Пишите сообщение Продюсеру:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🚪 Конец связи")]], resize_keyboard=True))

@dp.message(ChatWithBoss.active)
async def chat_boss_r(message: types.Message, state: FSMContext):
    if message.text=="🚪 Конец связи": await cab(message, state); return
    await bot.send_message(OWNER_ID, f"📩 <b>СООБЩЕНИЕ ОТ АРТИСТА {message.from_user.id}:</b>\n{message.text}")
    await message.answer("✅ Отправлено.")

@dp.callback_query(F.data == "back_to_cab")
async def b_cab(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await cab(callback.message, state)

@dp.callback_query(F.data == "cab_pay")
async def cab_pay(callback: types.CallbackQuery, state: FSMContext):
    i = get_driver_info(callback.from_user.id)
    b = get_driver_info(OWNER_ID)
    await callback.message.answer(f"💸 Комиссия сервиса: <b>{i[3]}₽</b>\nПеревод Продюсеру: <b>{b[2]}</b>")
    await callback.answer()

# ==========================================
# 📜 CRAZY МЕНЮ (VIEW)
# ==========================================
@dp.message(F.text == "📜 CRAZY МЕНЮ (Категории)")
async def show_cats(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    did = get_linked_driver(message.from_user.id)
    if not did:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Я В МАШИНЕ (ВВЕСТИ КОД)", callback_data="enter_code_dialog")],[InlineKeyboardButton(text="👀 ВИТРИНА", callback_data="start_showcase")]])
        return await message.answer("🚖 <b>Введите код Артиста:</b>", reply_markup=kb)
    
    act_def, customs = get_driver_menu(did)
    spent, trips, unlocked = get_client_stats(message.from_user.id)
    btns = []
    for i, n in CATEGORIES.items():
        if i == 4 and not unlocked and trips < VIP_LIMIT:
            btns.append([InlineKeyboardButton(text=f"🔒 {n} (Нужен VIP код)", callback_data="locked_vip")])
            continue
        # Показываем категорию, если в ней есть хоть одна услуга
        if any(v['cat']==i and k in act_def for k,v in CRAZY_SERVICES.items()) or any(c[1]==i for c in customs):
            btns.append([InlineKeyboardButton(text=n, callback_data=f"cat_{i}")])
    await message.answer("🔥 <b>ВЫБЕРИТЕ УРОВЕНЬ БЕЗУМИЯ:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "enter_code_dialog")
async def enter_cd(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите код:")
    await state.set_state(UnlockMenu.waiting_for_key)

@dp.callback_query(F.data == "start_showcase")
async def start_sc(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(showcase=True)
    btns = [[InlineKeyboardButton(text=n, callback_data=f"cat_{i}")] for i, n in CATEGORIES.items()]
    await callback.message.edit_text("👀 <b>ВИТРИНА (Демо):</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "locked_vip")
async def l_vip(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("⛔ Введите VIP-код водителя!", show_alert=True)

@dp.callback_query(F.data.startswith("cat_"))
async def cat_op(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[1])
    d = await state.get_data()
    showcase = d.get('showcase')
    did = get_linked_driver(callback.from_user.id)
    btns = []
    if showcase:
        [btns.append([InlineKeyboardButton(text=f"{v['name']} — {v['price']}₽", callback_data=f"srv_{k}")]) for k,v in CRAZY_SERVICES.items() if v['cat']==cid]
    else:
        act_def, customs = get_driver_menu(did)
        [btns.append([InlineKeyboardButton(text=f"{v['name']} — {v['price']}₽", callback_data=f"srv_{k}")]) for k,v in CRAZY_SERVICES.items() if v['cat']==cid and k in act_def]
        [btns.append([InlineKeyboardButton(text=f"★ {cs[2]} — {cs[4]}₽", callback_data=f"custsrv_{cs[0]}")]) for cs in customs if cs[1]==cid]
    btns.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_c")])
    await callback.message.edit_text(f"📂 <b>{CATEGORIES[cid]}</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "back_c")
async def back_c(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await show_cats(callback.message, state)

@dp.callback_query(F.data.startswith("srv_"))
async def srv_sel(callback: types.CallbackQuery, state: FSMContext):
    k = callback.data.split("_")[1]; v = CRAZY_SERVICES[k]; d = await state.get_data()
    btn = "✅ ЗАКАЗАТЬ ШОУ" if not d.get('showcase') else "🔒 В ПОЕЗДКЕ"
    cb = f"do_{k}" if not d.get('showcase') else "al_sc"
    await callback.message.edit_text(f"🎭 <b>{v['name']}</b>\n💰 {v['price']}₽\n<i>{v['desc']}</i>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn, callback_data=cb)],[InlineKeyboardButton(text="🔙", callback_data=f"cat_{v['cat']}")]]))

@dp.callback_query(F.data.startswith("custsrv_"))
async def srv_cust(callback: types.CallbackQuery, state: FSMContext):
    sid = int(callback.data.split("_")[1])
    conn = sqlite3.connect(DB_PATH)
    srv = conn.execute("SELECT name, description, price, category_id FROM custom_services WHERE id=?", (sid,)).fetchone()
    conn.close()
    if not srv: return await callback.answer("Удалено")
    d = await state.get_data()
    btn = "✅ ЗАКАЗАТЬ ШОУ" if not d.get('showcase') else "🔒 В ПОЕЗДКЕ"
    cb = f"docust_{sid}" if not d.get('showcase') else "al_sc"
    await callback.message.edit_text(f"🎭 <b>{srv[0]}</b>\n💰 {srv[2]}₽\n<i>{srv[1]}</i>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn, callback_data=cb)],[InlineKeyboardButton(text="🔙", callback_data=f"cat_{srv[3]}")]]))

@dp.callback_query(F.data == "al_sc")
async def al_sc(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Это демо! Сядьте в машину.", show_alert=True)

@dp.callback_query(F.data.startswith("do_"))
async def do_ord(callback: types.CallbackQuery, state: FSMContext):
    k = callback.data.split("_")[1]; cid = callback.from_user.id; did = get_linked_driver(cid); v = CRAZY_SERVICES[k]
    active_orders[cid] = {"type":"crazy", "status":"pending", "price":str(v['price']), "driver_id":did}
    await bot.send_message(did, f"🔔 <b>ЗАКАЗ: {v['name']}</b>\n💰 {v['price']}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"t_ok_{cid}"), InlineKeyboardButton(text="💬 ЧАТ", callback_data="enter_chat")]]))
    await callback.message.edit_text("⏳ Ждем подтверждения...")

@dp.callback_query(F.data.startswith("docust_"))
async def do_cust(callback: types.CallbackQuery, state: FSMContext):
    sid = int(callback.data.split("_")[1]); cid = callback.from_user.id; did = get_linked_driver(cid)
    conn = sqlite3.connect(DB_PATH)
    srv = conn.execute("SELECT name, price FROM custom_services WHERE id=?", (sid,)).fetchone()
    conn.close()
    active_orders[cid] = {"type":"crazy", "status":"pending", "price":str(srv[1]), "driver_id":did}
    await bot.send_message(did, f"🔔 <b>ЗАКАЗ: {srv[0]}</b>\n💰 {srv[1]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"t_ok_{cid}"), InlineKeyboardButton(text="💬 ЧАТ", callback_data="enter_chat")]]))
    await callback.message.edit_text("⏳ Ждем подтверждения...")

# --- ORDER & PAYMENT LOGIC ---
@dp.callback_query(F.data.startswith("t_ok_"))
async def t_ok(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2]); did = callback.from_user.id; o = active_orders.get(cid)
    if not o or o.get("status") != "pending": return await callback.answer("Занято!")
    o["status"] = "accepted"; o["driver_id"] = did; set_linked_driver(cid, did); info = get_driver_info(did)
    for aid, mid in o.get('admin_msg_ids', {}).items():
        try: await bot.edit_message_text(chat_id=aid, message_id=mid, text=f"🚫 <b>ВЗЯЛ: {info[7]}</b>", reply_markup=None)
        except: pass
    await callback.message.edit_text(f"✅ Взято. Клиент: {o.get('phone', 'Crazy')}"); await cab(callback.message, state)
    await bot.send_message(cid, f"🎭 <b>АРТИСТ ГОТОВ!</b>\n👤 {info[7]}\n🚘 {info[1]}\n💰 {o['price']}₽", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 ЧАТ", callback_data="enter_chat"), InlineKeyboardButton(text="💸 ОПЛАТИЛ", callback_data=f"cli_pay_{cid}"), InlineKeyboardButton(text="➕ ЗАЕЗД", callback_data="add_stop"), InlineKeyboardButton(text="🆘 SOS", callback_data=f"sos_{did}")]]) )

@dp.callback_query(F.data.startswith("cli_pay_"))
async def cli_pay(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2]); did = active_orders[cid]['driver_id']
    await bot.send_message(did, "💸 <b>Оплата!</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data=f"drv_confirm_{cid}"), InlineKeyboardButton(text="❌ НЕ ПРИШЛО", callback_data=f"drv_deny_{cid}")]]))
    await callback.message.edit_text("⏳ Ждем подтверждения...")

@dp.callback_query(F.data.startswith("drv_confirm_"))
async def drv_con(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2])
    if cid in active_orders: update_client_after_trip(cid, extract_price(active_orders[cid]['price']))
    await bot.send_message(cid, "✅ <b>Принято!</b>")
    await callback.message.edit_text("✅ Принято.")

@dp.callback_query(F.data.startswith("drv_deny_"))
async def drv_d(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2])
    await bot.send_message(cid, "❌ <b>Нет оплаты!</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 ПОВТОРИТЬ", callback_data=f"cli_pay_{cid}")]]))
    await callback.message.edit_text("❌")

@dp.callback_query(F.data.startswith("ask_finish_"))
async def ask_fin(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2])
    await bot.send_message(cid, "🏁 <b>Финал! Оценка:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⭐ 5", callback_data=f"rate_{cid}_5")]]))
    await callback.message.edit_text("✅")
    await unlink_client(cid)
    await cab(callback.message, state)

@dp.callback_query(F.data.startswith("rate_"))
async def rate(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[1]); o = active_orders.get(cid)
    if o:
        did = o['driver_id']; pr = extract_price(o['price']); log_order(cid, did, "Шоу", pr); update_order_rating(5, did); add_commission(did, pr)
        await bot.send_message(did, "🎉 5⭐"); del active_orders[cid]
    await callback.message.edit_text("Спасибо!")

# --- TAXI SEARCH ---
@dp.message(F.text == "🎭 Найти Артиста (с авто)")
async def t_s(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("📍 <b>Где вы?</b>", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(OrderRide.waiting_for_from)

@dp.message(OrderRide.waiting_for_from)
async def t_f(message: types.Message, state: FSMContext):
    await state.update_data(fr=message.text)
    await message.answer("🏁 <b>Куда?</b>")
    await state.set_state(OrderRide.waiting_for_to)

@dp.message(OrderRide.waiting_for_to)
async def t_t(message: types.Message, state: FSMContext):
    await state.update_data(to=message.text)
    await message.answer("📞 <b>Телефон:</b>")
    await state.set_state(OrderRide.waiting_for_phone)

@dp.message(OrderRide.waiting_for_phone)
async def t_p(message: types.Message, state: FSMContext):
    await state.update_data(ph=message.text)
    await message.answer("💰 <b>Цена?</b>")
    await state.set_state(OrderRide.waiting_for_price)

@dp.message(OrderRide.waiting_for_price)
async def t_end(message: types.Message, state: FSMContext):
    d = await state.get_data(); cid = message.from_user.id
    active_orders[cid] = {"type":"taxi", "status":"pending", "price":message.text, "from":d['fr'], "to":d['to'], "phone":d['ph']}
    await message.answer("✅ <b>Ищем Артиста...</b>", reply_markup=main_kb); await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"t_ok_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"t_bid_{cid}")]])
    
    adm = get_all_admins_ids(); msg_map = {}
    for a in adm:
        try: m = await bot.send_message(a, f"🎭 {d['fr']} -> {d['to']}\n💰 {message.text}", reply_markup=kb); msg_map[a] = m.message_id
        except: pass
    active_orders[cid]['admin_msg_ids'] = msg_map
    tasks = [safe_send_message(d, f"🎭 {d['fr']} -> {d['to']}\n💰 {message.text}", kb) for d in get_active_drivers() if d not in adm]
    if tasks: await asyncio.gather(*tasks)

# --- EXTRAS ---
@dp.callback_query(F.data.startswith("sos_"))
async def sos_btn(callback: types.CallbackQuery, state: FSMContext):
    did = int(callback.data.split("_")[1]); cid = callback.from_user.id
    for aid in get_all_admins_ids(): await safe_send_message(aid, f"🆘 <b>SOS!</b>\nКлиент: {cid}\nВодитель: {did}")
    await callback.answer("🚨 SOS ОТПРАВЛЕН!", show_alert=True)

@dp.callback_query(F.data.startswith("t_bid_"))
async def cnt_s(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(cid=int(callback.data.split("_")[2]))
    await callback.message.answer("Ваша цена:")
    await state.set_state(DriverCounterOffer.waiting_for_offer)

@dp.message(DriverCounterOffer.waiting_for_offer)
async def cnt_snd(message: types.Message, state: FSMContext):
    d = await state.get_data(); cid = d['cid']
    await bot.send_message(cid, f"⚡ <b>Предложение:</b> {message.text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"t_ok_{cid}")] ])); await message.answer("Отправлено."); await state.clear()

@dp.callback_query(F.data == "add_stop")
async def add_stop(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Адрес:")
    await state.set_state(AddStop.waiting_for_address)

@dp.message(AddStop.waiting_for_address)
async def add_stop_p(message: types.Message, state: FSMContext):
    await state.update_data(a=message.text)
    await message.answer("Доплата:")
    await state.set_state(AddStop.waiting_for_price)

@dp.message(AddStop.waiting_for_price)
async def add_stop_f(message: types.Message, state: FSMContext):
    d = await state.get_data(); cid = message.from_user.id; did = active_orders[cid]['driver_id']
    await bot.send_message(did, f"📍 <b>Заезд:</b> {d['a']}\n💰 +{message.text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"stop_ok_{cid}_{message.text}")]])); await message.answer("⏳"); await state.clear()

@dp.callback_query(F.data.startswith("stop_ok_"))
async def stop_ok(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2]); pr = int(callback.data.split("_")[3]); active_orders[cid]['price'] = str(extract_price(active_orders[cid]['price']) + pr)
    await bot.send_message(cid, f"✅ <b>Принято!</b> Итог: {active_orders[cid]['price']}"); await callback.message.edit_text("✅")

# --- REGISTRATION ---
@dp.message(Command("driver", "drive"))
async def reg_s(message: types.Message, state: FSMContext):
    if get_driver_info(message.from_user.id): return await message.answer("Уже есть.")
    await state.clear(); await message.answer("ФИО:"); await state.set_state(DriverRegistration.waiting_for_fio)

@dp.message(DriverRegistration.waiting_for_fio)
async def reg_f(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await message.answer("Авто:")
    await state.set_state(DriverRegistration.waiting_for_car)

@dp.message(DriverRegistration.waiting_for_car)
async def reg_c(message: types.Message, state: FSMContext):
    await state.update_data(car=message.text)
    await message.answer("Реквизиты:")
    await state.set_state(DriverRegistration.waiting_for_payment_info)

@dp.message(DriverRegistration.waiting_for_payment_info)
async def reg_r(message: types.Message, state: FSMContext):
    await state.update_data(pay=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Пропустить")]], resize_keyboard=True)
    await message.answer("Промокод (если есть):", reply_markup=kb); await state.set_state(DriverRegistration.waiting_for_referral)

@dp.message(DriverRegistration.waiting_for_referral)
async def reg_p(message: types.Message, state: FSMContext):
    ref_code = message.text.strip().upper() if message.text != "Пропустить" else None
    await state.update_data(ref=ref_code)
    await message.answer("Придумайте Ваш Код-пароль:", reply_markup=types.ReplyKeyboardRemove()); await state.set_state(DriverRegistration.waiting_for_code)

@dp.message(DriverRegistration.waiting_for_code)
async def reg_fin(message: types.Message, state: FSMContext):
    c = message.text.upper().strip(); d = await state.get_data(); conn = sqlite3.connect(DB_PATH)
    if conn.execute("SELECT 1 FROM drivers WHERE access_code=? AND user_id!=?", (c, message.from_user.id)).fetchone(): return await message.answer("❌ Занят!")
    
    # PROMO & REFERRAL LOGIC
    ref_id = None
    start_comm = DEFAULT_COMMISSION
    end_date = None
    
    if d.get('ref'):
        promo = conn.execute("SELECT commission, duration FROM promo_codes WHERE code=?", (d['ref'],)).fetchone()
        if promo:
            start_comm = promo[0]
            end_date = datetime.now() + timedelta(days=promo[1])
        else:
            inviter = conn.execute("SELECT user_id, commission FROM drivers WHERE access_code=?", (d['ref'],)).fetchone()
            if inviter:
                ref_id = inviter[0]
                start_comm = 5 # Referral Promo
                end_date = datetime.now() + timedelta(days=30)
                new_comm_inv = max(MIN_COMMISSION, inviter[1] - 1)
                conn.execute("UPDATE drivers SET commission = ? WHERE user_id = ?", (new_comm_inv, ref_id))
                await safe_send_message(ref_id, f"🎉 <b>РЕФЕРАЛ!</b> Друг зарегистрировался.\nВаша комиссия: <b>{new_comm_inv}%</b>")

    vip = generate_vip_code(d['fio'])
    conn.execute("INSERT OR REPLACE INTO drivers (user_id, username, fio, car_info, payment_info, access_code, vip_code, status, referred_by, commission, promo_end_date) VALUES (?,?,?,?,?,?,?, 'pending', ?, ?, ?)", 
                 (message.from_user.id, message.from_user.username, d['fio'], d['car'], d['pay'], c, vip, ref_id, start_comm, end_date))
    conn.commit(); conn.close(); init_driver_services_defaults(message.from_user.id)
    
    msg = f"✅ Заявка! VIP-промо: {vip}\nКомиссия: {start_comm}%"
    if end_date: msg += f" (до {end_date.strftime('%d.%m')})"
    await message.answer(msg); await state.clear()
    
    for a in get_all_admins_ids(): await safe_send_message(a, f"🚨 НОВЫЙ: {d['fio']}", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"adm_app_{message.from_user.id}")]]))

# --- KEY ---
@dp.message(UnlockMenu.waiting_for_key)
async def key_fin(message: types.Message, state: FSMContext):
    code = message.text.strip().upper(); conn = sqlite3.connect(DB_PATH)
    drv = conn.execute("SELECT user_id, fio FROM drivers WHERE access_code=? AND status='active'", (code,)).fetchone()
    if drv:
        set_linked_driver(message.from_user.id, drv[0]); await message.answer(f"🔓 Вход. Артист: {drv[1]}", reply_markup=main_kb)
    else:
        drv = conn.execute("SELECT user_id, fio FROM drivers WHERE vip_code=? AND status='active'", (code,)).fetchone()
        if drv:
            set_linked_driver(message.from_user.id, drv[0]); unlock_vip_for_client(message.from_user.id)
            await message.answer(f"💎 <b>VIP!</b> Артист: {drv[1]}", reply_markup=main_kb)
        else: await message.answer("❌ Неверно.")
    conn.close(); await state.clear()

# --- ADMIN ---
@dp.message(Command("admin"))
async def adm(message: types.Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id): return await message.answer("⛔")
    conn = sqlite3.connect(DB_PATH); drs = conn.execute("SELECT user_id, fio, balance, commission FROM drivers").fetchall(); conn.close()
    txt = "👑 <b>ПРОДЮСЕРСКИЙ ЦЕНТР</b>\n" + "\n".join([f"• {d[1]} | {d[2]}₽ | {d[3]}% | /edit_{d[0]}" for d in drs])
    kb = [[InlineKeyboardButton(text="📢 РАССЫЛКА", callback_data="admin_broadcast"), InlineKeyboardButton(text="🎟 Создать Промокод", callback_data="create_promo")]]
    await message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.message(F.text.startswith("/edit_"))
async def ed(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    did = int(message.text.split("_")[1]); await state.update_data(target_did=did)
    await message.answer("Действие:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Счет", callback_data=f"adm_bill_{did}"), InlineKeyboardButton(text="📉 Комиссия", callback_data=f"adm_comm_{did}")]]))

@dp.callback_query(F.data == "create_promo")
async def cr_promo(callback: types.CallbackQuery, state: FSMContext): await callback.message.answer("Введите КОД (например START2026):"); await state.set_state(AdminPromo.code)
@dp.message(AdminPromo.code)
async def promo_c(message: types.Message, state: FSMContext): await state.update_data(c=message.text.upper()); await message.answer("Процент комиссии (число):"); await state.set_state(AdminPromo.comm)
@dp.message(AdminPromo.comm)
async def promo_p(message: types.Message, state: FSMContext): await state.update_data(p=int(message.text)); await message.answer("Длительность (дней):"); await state.set_state(AdminPromo.dur)
@dp.message(AdminPromo.dur)
async def promo_d(message: types.Message, state: FSMContext):
    d = await state.get_data(); conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO promo_codes (code, commission, duration) VALUES (?, ?, ?)", (d['c'], d['p'], int(message.text)))
    conn.commit(); conn.close(); await message.answer(f"✅ Промокод <b>{d['c']}</b> создан!\n{d['p']}% на {message.text} дней."); await state.clear()

@dp.callback_query(F.data.startswith("adm_comm_"))
async def adm_comm(callback: types.CallbackQuery, state: FSMContext): await callback.message.answer("Новый процент (число):"); await state.set_state(AdminEditComm.waiting_for_new_comm)
@dp.message(AdminEditComm.waiting_for_new_comm)
async def save_comm(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    d = await state.get_data(); update_driver_field(d['target_did'], "commission", int(message.text)); await message.answer("✅"); await state.clear()

@dp.callback_query(F.data.startswith("adm_bill_"))
async def bl(callback: types.CallbackQuery, state: FSMContext): await state.update_data(target_did=int(callback.data.split("_")[2])); await callback.message.answer("Текст:"); await state.set_state(AdminBilling.waiting_for_custom_req)
@dp.message(AdminBilling.waiting_for_custom_req)
async def bl_s(message: types.Message, state: FSMContext):
    d = await state.get_data(); await bot.send_message(d['target_did'], f"⚠️ <b>СЧЕТ:</b>\n{message.text}"); await message.answer("✅"); await state.clear()

@dp.callback_query(F.data.startswith("adm_app_"))
async def adm_app(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    did = int(callback.data.split("_")[2]); update_driver_field(did, "status", "active")
    await callback.message.edit_text("✅ Принят"); await safe_send_message(did, "🎉 Вы в труппе! /cab")

@dp.callback_query(F.data == "admin_broadcast")
async def brd(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Текст рассылки:")
    await state.set_state(AdminBroadcast.waiting_for_text)

@dp.message(AdminBroadcast.waiting_for_text)
async def brd_s(message: types.Message, state: FSMContext):
    count = 0
    for d in get_active_drivers():
        if await safe_send_message(d, f"📢 <b>НОВОСТИ:</b>\n{message.text}"): count += 1
    await message.answer(f"✅ Доставлено: {count}"); await state.clear()

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
