import asyncio
import logging
import os
import sqlite3
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

# ==========================================
# ⚙️ НАСТРОЙКИ
# ==========================================
logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("API_TOKEN")
OWNER_ID_STR = os.getenv("DRIVER_ID") 

if not API_TOKEN or not OWNER_ID_STR:
    exit("⛔ CRITICAL ERROR: Token or ID missing")

OWNER_ID = int(OWNER_ID_STR)
SECOND_ADMIN_ID = 6004764782
SUPER_ADMINS = [OWNER_ID, SECOND_ADMIN_ID]

VIP_DRIVER_KEY = "CRAZY_START"
LAWYER_LINK = "https://t.me/Ai_advokatrobot"

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

active_orders = {} 

# ==========================================
# 📜 КОНСТАНТЫ И МЕНЮ (В САМОМ ВЕРХУ!)
# ==========================================
LEGAL_TEXT = (
    "<b>📜 ПУБЛИЧНАЯ ОФЕРТА (AGENCY AGREEMENT)</b>\n\n"
    "1. <b>Суть сервиса:</b> Бот является агрегатором развлекательных услуг (Event-агентство). Мы помогаем найти Артистов (аниматоров) для создания настроения.\n"
    "2. <b>Транспорт:</b> Сервис НЕ оказывает транспортные услуги. Автомобиль является «подвижной декорацией». Перемещение осуществляется Артистом в рамках его личной ответственности.\n"
    "3. <b>Оплата:</b> Вы платите за творческую программу и атмосферу.\n"
    "4. <b>Безопасность:</b> Артист вправе прекратить шоу, если Зритель угрожает безопасности.\n"
)

CRAZY_SERVICES = {
    "candy": {"cat": 1, "price": 0, "name": "🍬 Презент", "desc": "Артист с серьезным лицом вручает вам элитную конфету."},
    "nose": {"cat": 1, "price": 300, "name": "👃 Перформанс 'Скука'", "desc": "Артист едет с пальцем в носу всю дорогу. Вы платите за его вживание в роль."},
    "butler": {"cat": 1, "price": 200, "name": "🤵 Дворецкий", "desc": "Вам открывают дверь, кланяются и называют 'Сир'."},
    "joke": {"cat": 1, "price": 50, "name": "🤡 Стендап (Мини)", "desc": "Анекдот категории 'Б'. Смех не гарантирован, но атмосфера будет."},
    "silence": {"cat": 1, "price": 150, "name": "🤐 Режим 'Ниндзя'", "desc": "Артист молчит всю дорогу. Даже если вы спросите путь — он ответит жестами."},
    "granny": {"cat": 2, "price": 800, "name": "👵 Роль 'Бабуля'", "desc": "Иммерсивный театр. Всю дорогу будут ворчать: 'Куда прешь, наркоман!'."},
    "gopnik": {"cat": 2, "price": 500, "name": "🍺 Роль 'Пацанчик'", "desc": "Рэпчик, обращение 'братишка', решение вопросиков."},
    "guide": {"cat": 2, "price": 600, "name": "🗣 Горе-Гид", "desc": "Экскурсия с выдуманными фактами."},
    "psych": {"cat": 2, "price": 1000, "name": "🧠 Психолог", "desc": "Вы жалуетесь на жизнь, Артист кивает и дает советы."},
    "spy": {"cat": 3, "price": 2000, "name": "🕵️‍♂️ Квест '007'", "desc": "Очки, паранойя, проверка хвоста. Мы уходим от погони."},
    "karaoke": {"cat": 3, "price": 5000, "name": "🎤 Караоке-Баттл", "desc": "Орем песни на полную! Фальшиво, но душевно."},
    "dance": {"cat": 3, "price": 15000, "name": "💃 Танцы", "desc": "Артист выходит и танцует макарену на светофоре."},
    "kidnap": {"cat": 4, "price": 30000, "name": "🎭 Похищение", "desc": "Розыгрыш. Вас (понарошку) грузят и везут в лес пить чай."},
    "tarzan": {"cat": 4, "price": 50000, "name": "🦍 Шоу 'Тарзан'", "desc": "Крики, удары в грудь, рычание на прохожих."},
    "burn": {"cat": 4, "price": 1000000, "name": "🔥 Фаер-Шоу (Авто)", "desc": "Едем на пустырь. Вы платите лям, мы сжигаем реквизит (машину)."},
    "eyes": {"cat": 5, "price": 0, "name": "👁️ Глаз-алмаз", "desc": "Изысканный комплимент вашим глазам."},
    "smile": {"cat": 5, "price": 0, "name": "😁 Улыбка", "desc": "Комплимент вашей улыбке."},
    "style": {"cat": 5, "price": 0, "name": "👠 Икона стиля", "desc": "Восхищение вашим образом."},
    "improv": {"cat": 5, "price": 0, "name": "✨ Импровизация", "desc": "Артист сам найдет, что в вас похвалить."},
    "propose": {"cat": 5, "price": 1000, "name": "💍 Предложение", "desc": "Вы делаете предложение Артисту. Шанс 50/50. ⚠️ ПРИ ОТКАЗЕ ДЕНЬГИ НЕ ВОЗВРАЩАЮТСЯ!"}
}
CATEGORIES = {1: "🟢 ЛАЙТ", 2: "🟡 МЕДИУМ", 3: "🔴 ХАРД", 4: "☠️ VIP БЕЗУМИЕ", 5: "🌹 ДЛЯ ДАМ"}

# ==========================================
# 🗄️ БАЗА ДАННЫХ
# ==========================================
DB_PATH = "/data/taxi_db.sqlite" if os.path.exists("/data") else "taxi_db.sqlite"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблицы
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            fio TEXT,
            car_info TEXT,
            payment_info TEXT,
            access_code TEXT UNIQUE, 
            status TEXT DEFAULT 'pending',
            role TEXT DEFAULT 'driver',
            balance INTEGER DEFAULT 0,
            rating_sum INTEGER DEFAULT 0,
            rating_count INTEGER DEFAULT 0,
            commission INTEGER DEFAULT 10
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS driver_services (
            driver_id INTEGER,
            service_key TEXT,
            is_active BOOLEAN DEFAULT 1,
            PRIMARY KEY (driver_id, service_key)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            user_id INTEGER PRIMARY KEY,
            linked_driver_id INTEGER DEFAULT NULL,
            total_spent INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            driver_id INTEGER,
            service_name TEXT,
            price INTEGER,
            rating INTEGER DEFAULT 0,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Админы
    for admin_id in SUPER_ADMINS:
        cursor.execute("SELECT 1 FROM drivers WHERE user_id = ?", (admin_id,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, role, balance, rating_sum, rating_count, commission) VALUES (?, ?, ?, ?, ?, ?, 'active', 'owner', 0, 0, 0, 0)",
                (admin_id, "BOSS", "Генпродюсер", "VIP Stage", "CASH", f"ADMIN_{admin_id}")
            )
            for key in CRAZY_SERVICES:
                cursor.execute("INSERT OR REPLACE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, 1)", (admin_id, key))
        else:
            # Обновляем роль, если админ уже есть
            cursor.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (admin_id,))
            
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 🛠 УТИЛИТЫ (ФУНКЦИИ)
# ==========================================

def is_client_accepted(user_id):
    """Проверка регистрации клиента"""
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT 1 FROM clients WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return bool(res)

def get_client_stats(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT total_spent FROM clients WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return res[0] if res else 0

def update_client_spent(user_id, amount):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE clients SET total_spent = total_spent + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

def get_status_name(spent):
    if spent > 100000: return "👹 МЕЦЕНАТ ХАОСА"
    if spent > 50000: return "💀 ПРОДЮСЕР"
    if spent > 10000: return "🤪 ЦЕНИТЕЛЬ"
    return "👶 ЗРИТЕЛЬ"

def init_driver_services_defaults(driver_id):
    conn = sqlite3.connect(DB_PATH)
    for key in CRAZY_SERVICES:
        conn.execute("INSERT OR IGNORE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, 1)", (driver_id, key))
    conn.commit()
    conn.close()

def get_driver_active_services(driver_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT service_key FROM driver_services WHERE driver_id=? AND is_active=1", (driver_id,)).fetchall()
    conn.close()
    return [r[0] for r in res]

def toggle_driver_service(driver_id, service_key):
    conn = sqlite3.connect(DB_PATH)
    curr = conn.execute("SELECT is_active FROM driver_services WHERE driver_id=? AND service_key=?", (driver_id, service_key)).fetchone()
    new_status = 0 if (curr and curr[0] == 1) else 1
    conn.execute("INSERT OR REPLACE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, ?)", (driver_id, service_key, new_status))
    conn.commit()
    conn.close()

def get_linked_driver(client_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT linked_driver_id FROM clients WHERE user_id=?", (client_id,)).fetchone()
    conn.close()
    return res[0] if res and res[0] else None

def set_linked_driver(client_id, driver_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO clients (user_id, linked_driver_id) VALUES (?, ?)", (client_id, driver_id))
    conn.commit()
    conn.close()

def is_admin(user_id):
    if user_id in SUPER_ADMINS: return True
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT 1 FROM drivers WHERE user_id=? AND role IN ('owner', 'admin') AND status='active'", (user_id,)).fetchone()
    conn.close()
    return bool(res)

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

def get_driver_by_code(code):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT user_id, username, car_info, fio FROM drivers WHERE access_code=? AND status='active'", (code,)).fetchone()
    conn.close()
    return res

def get_driver_info(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT username, car_info, payment_info, balance, status, access_code, role, fio, rating_sum, rating_count, commission FROM drivers WHERE user_id=?", (user_id,)).fetchone()
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
    cursor = conn.cursor()
    cursor.execute("INSERT INTO order_history (client_id, driver_id, service_name, price) VALUES (?, ?, ?, ?)", (client_id, driver_id, service_name, price))
    last_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return last_id

def update_order_rating(order_id, rating, driver_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE drivers SET rating_sum = rating_sum + ?, rating_count = rating_count + 1 WHERE user_id = ?", (rating, driver_id))
    conn.commit()
    conn.close()

def add_commission(driver_id, amount):
    if is_admin(driver_id): return 
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT commission FROM drivers WHERE user_id=?", (driver_id,)).fetchone()
    percent = row[0] if row else 10
    val = int(amount * (percent / 100))
    conn.execute("UPDATE drivers SET balance = balance + ? WHERE user_id=?", (val, driver_id))
    conn.commit()
    conn.close()

async def safe_send_message(chat_id, text, reply_markup=None):
    try:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)
        return True
    except: return False

async def check_tos(message: types.Message) -> bool:
    if not is_client_accepted(message.from_user.id):
        await message.answer("🛑 <b>ДОСТУП ЗАПРЕЩЕН!</b>\nНажмите /start.")
        return False
    return True

# ==========================================
# 🛠 FSM STATES
# ==========================================
class OrderRide(StatesGroup):
    waiting_for_from = State(); waiting_for_to = State(); waiting_for_phone = State(); waiting_for_price = State()
class CustomIdea(StatesGroup):
    waiting_for_idea = State(); waiting_for_price = State()
class DriverCounterOffer(StatesGroup):
    waiting_for_offer = State()
class AddStop(StatesGroup):
    waiting_for_address = State(); waiting_for_price = State()
class DriverRegistration(StatesGroup):
    waiting_for_fio = State(); waiting_for_car = State(); waiting_for_payment_info = State(); waiting_for_code = State()
class DriverVipRegistration(StatesGroup):
    waiting_for_fio = State(); waiting_for_car = State(); waiting_for_payment_info = State(); waiting_for_code = State()
class DriverChangeCode(StatesGroup):
    waiting_for_new_code = State()
class UnlockMenu(StatesGroup):
    waiting_for_key = State()
class AdminEditDriver(StatesGroup):
    waiting_for_new_value = State()
class AdminBilling(StatesGroup):
    waiting_for_custom_req = State()
class AdminBroadcast(StatesGroup):
    waiting_for_text = State()
class ChatState(StatesGroup):
    active = State()

# ==========================================
# ⌨️ UI
# ==========================================
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎭 Найти Артиста (с авто)")],
        [KeyboardButton(text="📜 CRAZY МЕНЮ (Категории)")],
        [KeyboardButton(text="👤 Мой Кабинет"), KeyboardButton(text="📄 ОФЕРТА")]
    ], resize_keyboard=True
)

tos_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ ПРИНИМАЮ ПРАВИЛА ИГРЫ", callback_data="accept_tos")],
    [InlineKeyboardButton(text="❌ Я слишком скучный", callback_data="decline_tos")]
])

# ==========================================
# 🛑 СТАРТ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if is_client_accepted(message.from_user.id):
        await message.answer("⚠️ <b>CRAZY MOOD: С возвращением в клуб!</b>", reply_markup=main_kb)
    else:
        await message.answer(
            "⚠️ <b>ВНИМАНИЕ! ЭТО НЕ ТАКСИ.</b>\n\n"
            "Это сервис поиска попутчиков-аниматоров.\n"
            "Мы находим безумцев, готовых превратить вашу скучную дорогу в шоу.\n\n"
            "<b>Готовы к перформансу?</b>", 
            reply_markup=tos_kb
        )

@dp.callback_query(F.data == "accept_tos")
async def tos_accepted(callback: types.CallbackQuery, state: FSMContext):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (callback.from_user.id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("🔥 <b>ВЫ В ИГРЕ!</b>")
    await callback.message.answer("Добро пожаловать. Выбирайте шоу 👇", reply_markup=main_kb)

@dp.callback_query(F.data == "decline_tos")
async def tos_declined(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🚶‍♂️ Скучные такси в другом приложении.")

@dp.message(F.text == "📄 ОФЕРТА")
async def show_legal(message: types.Message, state: FSMContext):
    await message.answer(LEGAL_TEXT)

# ==========================================
# 👤 ЛИЧНЫЙ КАБИНЕТ
# ==========================================
@dp.message(F.text == "👤 Мой Кабинет")
async def client_cab(message: types.Message, state: FSMContext):
    if not is_client_accepted(message.from_user.id): return await message.answer("Сначала /start")
    spent = get_client_stats(message.from_user.id)
    status = get_status_name(spent)
    conn = sqlite3.connect(DB_PATH)
    hist = conn.execute("SELECT service_name, price, date FROM order_history WHERE client_id=? ORDER BY id DESC LIMIT 5", (message.from_user.id,)).fetchall()
    conn.close()
    h_text = "\n".join([f"▪ {h[0]} ({h[1]}₽)" for h in hist]) or "Нет истории шоу."
    
    kb = []
    if message.from_user.id in active_orders:
        kb.append([InlineKeyboardButton(text="💬 ЧАТ С АРТИСТОМ", callback_data="enter_chat")])
    
    await message.answer(f"👤 <b>КАБИНЕТ ЗРИТЕЛЯ</b>\n👑 Титул: <b>{status}</b>\n💰 Инвестировано в эмоции: <b>{spent}₽</b>\n\n📜 <b>ИСТОРИЯ ШОУ:</b>\n{h_text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb) if kb else None)

# ==========================================
# 💬 ЧАТ
# ==========================================
@dp.callback_query(F.data == "enter_chat")
async def enter_chat_mode(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    partner_id = None
    if user_id in active_orders: partner_id = active_orders[user_id].get('driver_id')
    if not partner_id:
        for cid, order in active_orders.items():
            if order.get('driver_id') == user_id: partner_id = cid; break
    if not partner_id: return await callback.answer("❌ Нет связи", show_alert=True)
    await state.update_data(chat_partner=partner_id); await state.set_state(ChatState.active)
    await callback.message.answer("💬 <b>КАНАЛ СВЯЗИ ОТКРЫТ!</b>\nПишите.", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🚪 Конец связи")]], resize_keyboard=True))
    await callback.answer()

@dp.message(ChatState.active)
async def chat_relay(message: types.Message, state: FSMContext):
    if message.text == "🚪 Конец связи":
        await state.clear()
        if get_driver_info(message.from_user.id): return await cab(message, state)
        else: return await message.answer("Связь завершена.", reply_markup=main_kb)
    data = await state.get_data(); partner_id = data.get('chat_partner')
    try: await message.copy_to(chat_id=partner_id)
    except: await message.answer("❌ Ошибка доставки.")

# ==========================================
# 🎭 ПОИСК АРТИСТА (ТАКСИ)
# ==========================================
async def update_admins_monitor(client_id, taking_driver_id):
    order = active_orders.get(client_id)
    if not order or 'admin_msg_ids' not in order: return
    drv_info = get_driver_info(taking_driver_id)
    role = "АДМИН" if is_admin(taking_driver_id) else "АРТИСТ"
    text = f"🚫 <b>ЗАКАЗ ПРИНЯЛ: {role} {drv_info[0]}</b>\nФИО: {drv_info[7]}\nАвто: {drv_info[1]}\n\n{order.get('broadcasting_text','')}"
    for admin_id, msg_id in order['admin_msg_ids'].items():
        try: await bot.edit_message_text(chat_id=admin_id, message_id=msg_id, text=text, reply_markup=None)
        except: pass

async def broadcast_order_to_drivers(client_id, order_text, driver_kb, admin_kb):
    admins = get_all_admins_ids()
    admin_msg_map = {}
    for admin_id in admins:
        try:
            msg = await bot.send_message(admin_id, f"🚨 <b>МОНИТОРИНГ</b>\n{order_text}", reply_markup=admin_kb)
            admin_msg_map[admin_id] = msg.message_id
        except: pass
    if client_id in active_orders:
        active_orders[client_id]['admin_msg_ids'] = admin_msg_map
        active_orders[client_id]['broadcasting_text'] = order_text
    
    await bot.send_message(client_id, "📡 <i>Ищем свободного Артиста...</i>")
    await asyncio.sleep(1.5)
    
    simple_drivers = [d for d in get_active_drivers() if d not in admins]
    tasks = [safe_send_message(d, f"⚡ <b>ЗАПРОС НА ШОУ!</b>\n{order_text}", driver_kb) for d in simple_drivers]
    if tasks: await asyncio.gather(*tasks)

@dp.message(F.text == "🎭 Найти Артиста (с авто)")
async def taxi_start(message: types.Message, state: FSMContext):
    await state.clear(); await message.answer("📍 <b>Где начинаем шоу?</b> (Адрес подачи)", reply_markup=types.ReplyKeyboardRemove()); await state.set_state(OrderRide.waiting_for_from)

@dp.message(OrderRide.waiting_for_from)
async def taxi_fr(message: types.Message, state: FSMContext):
    await state.update_data(fr=message.text); await message.answer("🏁 <b>Куда едем?</b>"); await state.set_state(OrderRide.waiting_for_to)

@dp.message(OrderRide.waiting_for_to)
async def taxi_to(message: types.Message, state: FSMContext):
    await state.update_data(to=message.text); await message.answer("📞 <b>Телефон для связи:</b>"); await state.set_state(OrderRide.waiting_for_phone)

@dp.message(OrderRide.waiting_for_phone)
async def taxi_ph(message: types.Message, state: FSMContext):
    await state.update_data(ph=message.text); await message.answer("💰 <b>Предложите гонорар (цена поездки):</b>"); await state.set_state(OrderRide.waiting_for_price)

@dp.message(OrderRide.waiting_for_price)
async def taxi_send(message: types.Message, state: FSMContext):
    data = await state.get_data(); cid = message.from_user.id
    active_orders[cid] = {"type": "taxi", "status": "pending", "price": message.text, "from": data['fr'], "to": data['to'], "phone": data['ph']}
    await message.answer("✅ <b>Заявка в эфире!</b>", reply_markup=main_kb); await state.clear()
    txt = f"🎭 <b>ЗАПРОС НА ПЕРФОРМАНС</b>\n📍 Старт: {data['fr']}\n🏁 Финиш: {data['to']}\n💰 Гонорар: {message.text}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ РОЛЬ", callback_data=f"t_ok_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"t_bid_{cid}")]])
    await broadcast_order_to_drivers(cid, txt, kb, kb)

@dp.callback_query(F.data.startswith("t_ok_"))
async def taxi_take(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2]); did = callback.from_user.id; order = active_orders.get(cid)
    if not order or order["status"] != "pending": return await callback.answer("Роль занята!")
    order["status"] = "accepted"; order["driver_id"] = did; set_linked_driver(cid, did); await update_admins_monitor(cid, did)
    info = get_driver_info(did)
    drv_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 ЧАТ", callback_data="enter_chat"), InlineKeyboardButton(text="🏁 ФИНАЛ", callback_data=f"ask_finish_{cid}")]])
    await callback.message.edit_text(f"✅ <b>Роль принята!</b>\nЗритель: {order['phone']}", reply_markup=drv_kb)
    cli_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 ЧАТ", callback_data="enter_chat"), InlineKeyboardButton(text="💸 ГОНОРАР ПЕРЕВЕДЕН", callback_data=f"cli_pay_{cid}"), InlineKeyboardButton(text="➕ ЗАЕЗД", callback_data="add_stop")]])
    await bot.send_message(cid, f"🎭 <b>АРТИСТ ВЫЕХАЛ!</b>\n👤 {info[7]}\n🚘 {info[1]}\n📞 {order['phone']}\n💰 {order['price']}₽\n🔐 Код: <code>{info[5]}</code>", reply_markup=cli_kb)

@dp.callback_query(F.data.startswith("cli_pay_"))
async def cli_pay(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2]); did = active_orders[cid]['driver_id']
    await bot.send_message(did, "💸 <b>Гонорар переведен!</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data=f"drv_confirm_{cid}")]]))
    await callback.message.edit_text("⏳ Ждем подтверждения...")

@dp.callback_query(F.data.startswith("drv_confirm_"))
async def drv_con(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2]); await bot.send_message(cid, "✅ <b>Оплата принята!</b>"); await callback.message.edit_text("✅ Принято.")

@dp.callback_query(F.data == "add_stop")
async def add_stop_s(callback: types.CallbackQuery, state: FSMContext): await callback.message.answer("Адрес:"); await state.set_state(AddStop.waiting_for_address)
@dp.message(AddStop.waiting_for_address)
async def add_stop_p(message: types.Message, state: FSMContext): await state.update_data(a=message.text); await message.answer("Доплата:"); await state.set_state(AddStop.waiting_for_price)
@dp.message(AddStop.waiting_for_price)
async def add_stop_f(message: types.Message, state: FSMContext):
    d = await state.get_data(); cid = message.from_user.id; did = active_orders[cid]['driver_id']
    await bot.send_message(did, f"📍 <b>Заезд:</b> {d['a']}\n💰 +{message.text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"stop_ok_{cid}_{message.text}")]]))
    await message.answer("⏳ Отправлено..."); await state.clear()

@dp.callback_query(F.data.startswith("stop_ok_"))
async def stop_ok(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2]); extra = int(callback.data.split("_")[3])
    order = active_orders.get(cid); order['price'] = str(extract_price(order['price']) + extra)
    await bot.send_message(cid, f"✅ <b>Принято!</b> Новая цена: {order['price']}")
    await callback.message.edit_text("✅ Точка добавлена.")

@dp.callback_query(F.data.startswith("ask_finish_"))
async def ask_fin(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2])
    await bot.send_message(cid, "🏁 <b>Шоу окончено! Оценка Артисту:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⭐ 5", callback_data=f"rate_{cid}_5")]]))
    await callback.message.edit_text("✅ Закрыто.")

@dp.callback_query(F.data.startswith("rate_"))
async def rate(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[1]); order = active_orders.get(cid)
    if order:
        did = order['driver_id']; pr = extract_price(order['price'])
        log_order(cid, did, "Шоу", pr); update_client_spent(cid, pr); update_order_rating(5, did); add_commission(did, pr)
        await bot.send_message(did, "🎉 <b>Аплодисменты (5⭐)</b>"); del active_orders[cid]
    await callback.message.edit_text("Спасибо за участие!")

# --- ТОРГ ---
@dp.callback_query(F.data.startswith("t_bid_"))
async def cnt_s(callback: types.CallbackQuery, state: FSMContext): await state.update_data(cid=int(callback.data.split("_")[2])); await callback.message.answer("Ваша цена:"); await state.set_state(DriverCounterOffer.waiting_for_offer)
@dp.message(DriverCounterOffer.waiting_for_offer)
async def cnt_snd(message: types.Message, state: FSMContext):
    d = await state.get_data(); cid = d['cid']
    await bot.send_message(cid, f"⚡ <b>Артист предлагает:</b> {message.text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"t_ok_{cid}"), InlineKeyboardButton(text="❌", callback_data="decline_tos")]]))
    await message.answer("Отправлено."); await state.clear()

# ==========================================
# 📜 CRAZY МЕНЮ (СМЕНА РЕЖИМА НА SHOWCASE)
# ==========================================
@dp.message(F.text == "📜 CRAZY МЕНЮ (Категории)")
async def show_cats(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    did = get_linked_driver(message.from_user.id)
    
    # 🌟 РЕЖИМ ВИТРИНЫ
    if not did:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я В МАШИНЕ (ВВЕСТИ КОД)", callback_data="enter_code_dialog")],
            [InlineKeyboardButton(text="👀 ПРОСТО СМОТРЮ", callback_data="start_showcase")]
        ])
        await message.answer("🚖 <b>Вы уже в машине у нашего Артиста?</b>", reply_markup=kb)
        return

    active_srv = get_driver_active_services(did)
    btns = []
    for cat_id, cat_name in CATEGORIES.items():
        if any(srv['cat'] == cat_id and key in active_srv for key, srv in CRAZY_SERVICES.items()):
            btns.append([InlineKeyboardButton(text=cat_name, callback_data=f"cat_{cat_id}")])
    await message.answer("🔥 <b>ВЫБЕРИТЕ ЖАНР:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "enter_code_dialog")
async def enter_code_dialog(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите код Артиста:"); await state.set_state(UnlockMenu.waiting_for_key)

@dp.callback_query(F.data == "start_showcase")
async def start_showcase(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(showcase=True)
    btns = [[InlineKeyboardButton(text=cat_name, callback_data=f"cat_{cat_id}")] for cat_id, cat_name in CATEGORIES.items()]
    await callback.message.edit_text("👀 <b>РЕЖИМ ВИТРИНЫ</b> (Только просмотр):", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("cat_"))
async def open_cat(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data(); is_showcase = data.get('showcase', False)
    cat_id = int(callback.data.split("_")[1])
    
    if is_showcase:
        btns = [[InlineKeyboardButton(text=f"{val['name']} — {val['price']}₽", callback_data=f"srv_{key}")] for key, val in CRAZY_SERVICES.items() if val['cat'] == cat_id]
    else:
        cid = callback.from_user.id; did = get_linked_driver(cid); active_srv = get_driver_active_services(did)
        btns = [[InlineKeyboardButton(text=f"{val['name']} — {val['price']}₽", callback_data=f"srv_{key}")] for key, val in CRAZY_SERVICES.items() if val['cat'] == cat_id and key in active_srv]
    
    btns.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_cats")])
    await callback.message.edit_text(f"📂 <b>{CATEGORIES[cat_id]}</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "back_cats")
async def back_cats(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get('showcase'): await start_showcase(callback, state)
    else: 
        did = get_linked_driver(callback.from_user.id); active_srv = get_driver_active_services(did)
        btns = [[InlineKeyboardButton(text=n, callback_data=f"cat_{i}")] for i, n in CATEGORIES.items() if any(s['cat']==i and k in active_srv for k, s in CRAZY_SERVICES.items())]
        await callback.message.edit_text("🔥 <b>ВЫБЕРИТЕ ЖАНР:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("srv_"))
async def sel_srv(callback: types.CallbackQuery, state: FSMContext):
    key = callback.data.split("_")[1]; srv = CRAZY_SERVICES[key]
    data = await state.get_data(); is_showcase = data.get('showcase', False)
    
    btn_text = "🔒 ДОСТУПНО В ПОЕЗДКЕ" if is_showcase else "✅ ЗАКАЗАТЬ ШОУ"
    cb_data = "alert_showcase" if is_showcase else f"do_{key}"
    
    await callback.message.edit_text(f"🎭 <b>{srv['name']}</b>\n💰 {srv['price']}₽\n<i>{srv['desc']}</i>", 
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn_text, callback_data=cb_data)], [InlineKeyboardButton(text="🔙", callback_data=f"cat_{srv['cat']}")]]))

@dp.callback_query(F.data == "alert_showcase")
async def alert_showcase(callback: types.CallbackQuery):
    await callback.answer("🚫 Это демо-режим! Сядьте в машину к Артисту.", show_alert=True)

@dp.callback_query(F.data.startswith("do_"))
async def do_ord(callback: types.CallbackQuery, state: FSMContext):
    key = callback.data.split("_")[1]; srv = CRAZY_SERVICES[key]; cid = callback.from_user.id; did = get_linked_driver(cid)
    active_orders[cid] = {"type": "crazy", "price": str(srv["price"]), "driver_id": did}
    await bot.send_message(did, f"🔔 <b>ЗАКАЗ ШОУ: {srv['name']}</b>\n💰 {srv['price']}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"c_acc_{cid}")]]))
    await callback.message.edit_text("⏳ Ждем Артиста...")

@dp.callback_query(F.data.startswith("c_acc_"))
async def c_acc(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2]); i = get_driver_info(callback.from_user.id)
    await bot.send_message(cid, f"✅ Артист готов! Реквизиты: <code>{i[2]}</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 ГОНОРАР ПЕРЕВЕДЕН", callback_data=f"cli_pay_{cid}"), InlineKeyboardButton(text="💬 ЧАТ", callback_data="enter_chat")]]))
    await callback.message.edit_text("✅ В работе.")

# ==========================================
# 🪪 КАБИНЕТ + РЕГИСТРАЦИЯ
# ==========================================
@dp.message(Command("cab"))
async def cab(message: types.Message, state: FSMContext):
    await state.clear(); info = get_driver_info(message.from_user.id)
    if not info: return await message.answer("❌ Нет регистрации. /drive")
    role_map = {'owner':"👑 БОСС", 'admin':"👮‍♂️ АДМИН", 'driver':"🎩 АРТИСТ"}
    txt = (f"🪪 <b>ГРИМЕРКА (Кабинет)</b>\n🔰 Роль: {role_map.get(info[6])}\n👤 {info[7]}\n💰 Баланс: {info[3]}₽\n🔑 Код: <code>{info[5]}</code>")
    kb = [[InlineKeyboardButton(text="🎛 Настроить программу", callback_data="driver_menu_edit")], [InlineKeyboardButton(text="💸 Оплатить комиссию", callback_data="cab_pay")]]
    await message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "driver_menu_edit")
async def driver_menu_editor(callback: types.CallbackQuery, state: FSMContext):
    did = callback.from_user.id; active_keys = get_driver_active_services(did)
    kb_builder = []
    for key, val in CRAZY_SERVICES.items():
        status = "✅" if key in active_keys else "❌"
        kb_builder.append([InlineKeyboardButton(text=f"{status} {val['name']}", callback_data=f"toggle_srv_{key}")])
    kb_builder.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_cab")])
    await callback.message.edit_text("🎛 <b>РЕПЕРТУАР:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_builder))

@dp.callback_query(F.data.startswith("toggle_srv_"))
async def toggle_srv_handler(callback: types.CallbackQuery, state: FSMContext):
    key = callback.data.split("toggle_srv_")[1]; toggle_driver_service(callback.from_user.id, key); await driver_menu_editor(callback, state)

@dp.callback_query(F.data == "back_to_cab")
async def back_to_cab_handler(callback: types.CallbackQuery, state: FSMContext): await callback.message.delete(); await cab(callback.message, state)

@dp.callback_query(F.data == "cab_pay")
async def cab_pay(callback: types.CallbackQuery, state: FSMContext):
    info = get_driver_info(callback.from_user.id); boss = get_driver_info(OWNER_ID)
    await callback.message.answer(f"💸 Комиссия: <b>{info[3]}₽</b>\nПеревод Продюсеру: <b>{boss[2]}</b>"); await callback.answer()

@dp.message(Command("vip"))
async def vip_reg(message: types.Message, state: FSMContext):
    await state.clear()
    try:
        key = message.text.split()[1]
        if key == VIP_DRIVER_KEY: await state.update_data(role="driver"); await message.answer("ФИО:"); await state.set_state(DriverVipRegistration.waiting_for_fio)
    except: await message.answer("Формат: /vip КОД")

@dp.message(DriverVipRegistration.waiting_for_fio)
async def vip_fio(message: types.Message, state: FSMContext): await state.update_data(fio=message.text); await message.answer("Авто (Сцена):"); await state.set_state(DriverVipRegistration.waiting_for_car)
@dp.message(DriverVipRegistration.waiting_for_car)
async def vip_car(message: types.Message, state: FSMContext): await state.update_data(car=message.text); await message.answer("Реквизиты:"); await state.set_state(DriverVipRegistration.waiting_for_payment_info)
@dp.message(DriverVipRegistration.waiting_for_payment_info)
async def vip_pay(message: types.Message, state: FSMContext): await state.update_data(pay=message.text); await message.answer("Придумайте Код:"); await state.set_state(DriverVipRegistration.waiting_for_code)
@dp.message(DriverVipRegistration.waiting_for_code)
async def vip_fin(message: types.Message, state: FSMContext):
    d = await state.get_data(); code = message.text.upper().strip(); conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, role, commission, balance, rating_sum, rating_count) VALUES (?, ?, ?, ?, ?, ?, 'active', 'driver', 10, 0, 0, 0)", 
                     (message.from_user.id, message.from_user.username or "NoUser", d['fio'], d['car'], d['pay'], code))
        conn.commit(); init_driver_services_defaults(message.from_user.id); await message.answer("✅ В труппе! /cab")
        await safe_send_message(OWNER_ID, f"⭐ <b>VIP АРТИСТ:</b> {d['fio']}")
    except: await message.answer("❌ Код занят")
    conn.close(); await state.clear()

@dp.message(Command("driver", "drive"))
async def reg_start(message: types.Message, state: FSMContext): await state.clear(); await message.answer("ФИО:"); await state.set_state(DriverRegistration.waiting_for_fio)
@dp.message(DriverRegistration.waiting_for_fio)
async def reg_fio(message: types.Message, state: FSMContext): await state.update_data(fio=message.text); await message.answer("Авто:"); await state.set_state(DriverRegistration.waiting_for_car)
@dp.message(DriverRegistration.waiting_for_car)
async def reg_car(message: types.Message, state: FSMContext): await state.update_data(car=message.text); await message.answer("Реквизиты:"); await state.set_state(DriverRegistration.waiting_for_payment_info)
@dp.message(DriverRegistration.waiting_for_payment_info)
async def reg_pay(message: types.Message, state: FSMContext): await state.update_data(pay=message.text); await message.answer("Код:"); await state.set_state(DriverRegistration.waiting_for_code)
@dp.message(DriverRegistration.waiting_for_code)
async def reg_fin(message: types.Message, state: FSMContext):
    d = await state.get_data(); code = message.text.upper().strip(); conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, commission, role, balance, rating_sum, rating_count) VALUES (?, ?, ?, ?, ?, ?, 'pending', 10, 'driver', 0, 0, 0)", 
                     (message.from_user.id, message.from_user.username or "NoUser", d['fio'], d['car'], d['pay'], code))
        conn.commit(); init_driver_services_defaults(message.from_user.id); await message.answer("📝 Заявка на кастинг отправлена.")
        await safe_send_message(OWNER_ID, f"🚨 НОВЫЙ АРТИСТ: {d['fio']}", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"adm_app_{message.from_user.id}")]]))
    except: await message.answer("❌ Код занят")
    conn.close(); await state.clear()

# ==========================================
# 👑 АДМИНКА
# ==========================================
@dp.message(Command("admin"))
async def adm(message: types.Message, state: FSMContext):
    await state.clear(); 
    if not is_admin(message.from_user.id): return await message.answer("⛔")
    conn = sqlite3.connect(DB_PATH); drs = conn.execute("SELECT user_id, fio, balance FROM drivers").fetchall(); conn.close()
    txt = "👑 <b>ПРОДЮСЕРСКИЙ ЦЕНТР</b>\n" + "\n".join([f"• {d[1]} | {d[2]}₽ | /edit_{d[0]}" for d in drs])
    await message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 РАССЫЛКА", callback_data="admin_broadcast")]]))

@dp.callback_query(F.data.startswith("adm_app_"))
async def adm_ap(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    did = int(callback.data.split("_")[2]); update_driver_field(did, "status", "active"); await callback.message.edit_text("✅ Одобрено.")
    try: await bot.send_message(did, "🎉 Вы в команде! /cab")
    except: pass

@dp.message(F.text.startswith("/edit_"))
async def ed(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    did = int(message.text.split("_")[1]); await state.update_data(target_did=did)
    await message.answer("Действие:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Выставить счет", callback_data=f"adm_bill_{did}")]]))

@dp.callback_query(F.data.startswith("adm_bill_"))
async def bl(callback: types.CallbackQuery, state: FSMContext): await state.update_data(target_did=int(callback.data.split("_")[2])); await callback.message.answer("Сумма/Текст:"); await state.set_state(AdminBilling.waiting_for_custom_req)
@dp.message(AdminBilling.waiting_for_custom_req)
async def bl_s(message: types.Message, state: FSMContext):
    d = await state.get_data(); await bot.send_message(d['target_did'], f"⚠️ <b>СЧЕТ ОТ ПРОДЮСЕРА:</b>\n{message.text}"); await message.answer("✅"); await state.clear()

@dp.callback_query(F.data == "admin_broadcast")
async def brd(callback: types.CallbackQuery, state: FSMContext): await callback.message.answer("Текст:"); await state.set_state(AdminBroadcast.waiting_for_text)
@dp.message(AdminBroadcast.waiting_for_text)
async def brd_s(message: types.Message, state: FSMContext):
    for d in get_active_drivers(): await safe_send_message(d, f"📢 <b>НОВОСТИ КЛУБА:</b>\n{message.text}"); 
    await message.answer("✅"); await state.clear()

# ==========================================
# 🔐 ВВОД КЛЮЧА
# ==========================================
@dp.message(UnlockMenu.waiting_for_key)
async def key_pr(message: types.Message, state: FSMContext):
    drv = get_driver_by_code(message.text.strip().upper())
    if drv: set_linked_driver(message.from_user.id, drv[0]); await message.answer(f"🔓 <b>ДОСТУП ОТКРЫТ!</b>\nАртист: {drv[3]}\nАвто: {drv[2]}", reply_markup=main_kb); await state.clear()
    else: await message.answer("❌ Неверный код.")

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
