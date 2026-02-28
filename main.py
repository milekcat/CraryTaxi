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

# Хранилище активных заказов
active_orders = {} 

# ==========================================
# 🗄️ БАЗА ДАННЫХ
# ==========================================
DB_PATH = "/data/taxi_db.sqlite" if os.path.exists("/data") else "taxi_db.sqlite"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Водители
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
    # 2. Настройки услуг
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS driver_services (
            driver_id INTEGER,
            service_key TEXT,
            is_active BOOLEAN DEFAULT 1,
            PRIMARY KEY (driver_id, service_key)
        )
    """)
    # 3. Клиенты
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            user_id INTEGER PRIMARY KEY,
            linked_driver_id INTEGER DEFAULT NULL,
            total_spent INTEGER DEFAULT 0
        )
    """)
    # 4. История (ОБНОВЛЕНО: добавлен client_id)
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
                (admin_id, "BOSS", "Владелец", "VIP", "CASH", f"ADMIN_{admin_id}")
            )
            for key in CRAZY_SERVICES:
                cursor.execute("INSERT OR REPLACE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, 1)", (admin_id, key))
    
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 🛠 УТИЛИТЫ
# ==========================================

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
    if spent > 100000: return "👹 ИМПЕРАТОР ХАОСА"
    if spent > 50000: return "💀 ПСИХОПАТ"
    if spent > 10000: return "🤪 ЛЮБИТЕЛЬ"
    return "👶 НОВИЧОК"

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

def is_client_accepted(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT 1 FROM clients WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return bool(res)

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

def update_order_rating(rating, driver_id):
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

# ==========================================
# 📜 МЕНЮ УСЛУГ
# ==========================================
CRAZY_SERVICES = {
    "candy": {"cat": 1, "price": 0, "name": "🍬 Конфетка", "desc": "Водитель с серьезным лицом вручает вам элитную конфету."},
    "nose": {"cat": 1, "price": 300, "name": "👃 Палец в носу", "desc": "Всю поездку водитель едет с пальцем в носу. Вы платите за его страдания."},
    "butler": {"cat": 1, "price": 200, "name": "🤵 Дворецкий", "desc": "Водитель открывает дверь, кланяется и называет 'Сир'."},
    "joke": {"cat": 1, "price": 50, "name": "🤡 Тупой анекдот", "desc": "Анекдот категории 'Б'. Смеяться не обязательно."},
    "silence": {"cat": 1, "price": 150, "name": "🤐 Тишина", "desc": "Режим 'Ниндзя'. Музыка выкл, водитель молчит."},
    "granny": {"cat": 2, "price": 800, "name": "👵 Бабушка", "desc": "Водитель бубнит: 'Шапку надень!', 'Наркоманы!'."},
    "gopnik": {"cat": 2, "price": 500, "name": "🍺 Пацанчик", "desc": "Рэпчик, 'братишка', решение вопросиков."},
    "guide": {"cat": 2, "price": 600, "name": "🗣 Ужасный гид", "desc": "Экскурсия с выдуманными фактами."},
    "psych": {"cat": 2, "price": 1000, "name": "🧠 Психолог", "desc": "Вы жалуетесь на жизнь, водитель кивает."},
    "spy": {"cat": 3, "price": 2000, "name": "🕵️‍♂️ Шпион", "desc": "Очки, паранойя, проверка хвоста."},
    "karaoke": {"cat": 3, "price": 5000, "name": "🎤 Караоке", "desc": "Орем песни на полную! Фальшиво, но душевно."},
    "dance": {"cat": 3, "price": 15000, "name": "💃 Танцы", "desc": "Водитель танцует макарену на светофоре."},
    "kidnap": {"cat": 4, "price": 30000, "name": "🎭 Похищение", "desc": "Вас (понарошку) грузят в багажник и везут в лес."},
    "tarzan": {"cat": 4, "price": 50000, "name": "🦍 Тарзан", "desc": "Крики, удары в грудь, рычание."},
    "burn": {"cat": 4, "price": 1000000, "name": "🔥 Сжечь авто", "desc": "Едем на пустырь. Вы платите лям, я даю канистру."},
    "eyes": {"cat": 5, "price": 0, "name": "👁️ Глаз-алмаз", "desc": "Изысканный комплимент вашим глазам."},
    "smile": {"cat": 5, "price": 0, "name": "😁 Улыбка", "desc": "Комплимент вашей улыбке."},
    "style": {"cat": 5, "price": 0, "name": "👠 Икона стиля", "desc": "Восхищение вашим образом."},
    "improv": {"cat": 5, "price": 0, "name": "✨ Импровизация", "desc": "Фристайл-комплимент."},
    "propose": {"cat": 5, "price": 1000, "name": "💍 Предложение", "desc": "Предложение руки и сердца водителю. Риск!"}
}
CATEGORIES = {1: "🟢 ЛАЙТ", 2: "🟡 МЕДИУМ", 3: "🔴 ХАРД", 4: "☠️ VIP БЕЗУМИЕ", 5: "🌹 ДЛЯ ДАМ"}
LEGAL_TEXT = "<b>📜 ОФЕРТА:</b>\nМы — агрегатор. Водитель — независимый исполнитель. Оплата Crazy-услуг — добровольное шоу."

# ==========================================
# 🛠 STATES
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
    active = State() # Режим чата

# ==========================================
# ⌨️ UI
# ==========================================
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚕 Заказать такси (Поиск)")],
        [KeyboardButton(text="🔐 Ввести КЛЮЧ услуги")],
        [KeyboardButton(text="📜 CRAZY МЕНЮ (Категории)")],
        [KeyboardButton(text="👤 Мой Кабинет"), KeyboardButton(text="⚖️ Адвокат")]
    ], resize_keyboard=True
)

tos_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ ПОДПИСАТЬ КРОВЬЮ", callback_data="accept_tos")],
    [InlineKeyboardButton(text="❌ Я боюсь", callback_data="decline_tos")]
])

# ==========================================
# 🛑 СТАРТ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if is_client_accepted(message.from_user.id):
        await message.answer("⚠️ <b>CRAZY TAXI: С возвращением!</b>", reply_markup=main_kb)
    else:
        await message.answer("⚠️ <b>CRAZY TAXI</b>\nГотовы рискнуть?", reply_markup=tos_kb)

@dp.callback_query(F.data == "accept_tos")
async def tos_accepted(callback: types.CallbackQuery, state: FSMContext):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (callback.from_user.id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("🔥 <b>ДОГОВОР ПРИНЯТ!</b>")
    await callback.message.answer("Добро пожаловать в Элитный Сервис.", reply_markup=main_kb)

@dp.callback_query(F.data == "decline_tos")
async def tos_declined(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🚶‍♂️ Выход там.")

@dp.message(F.text == "⚖️ Адвокат")
async def lawyer_menu(message: types.Message, state: FSMContext):
    await message.answer("⚖️ <b>ЮРИСТ</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚨 ПЕРЕЙТИ", url=LAWYER_LINK)]]))

# ==========================================
# 👤 ЛИЧНЫЙ КАБИНЕТ КЛИЕНТА
# ==========================================
@dp.message(F.text == "👤 Мой Кабинет")
async def client_cab(message: types.Message, state: FSMContext):
    if not is_client_accepted(message.from_user.id): return await message.answer("Сначала /start")
    
    # Статистика
    spent = get_client_stats(message.from_user.id)
    status = get_status_name(spent)
    
    # История
    conn = sqlite3.connect(DB_PATH)
    hist = conn.execute("SELECT service_name, price, date FROM order_history WHERE client_id=? ORDER BY id DESC LIMIT 5", (message.from_user.id,)).fetchall()
    conn.close()
    
    h_text = "\n".join([f"▪ {h[0]} ({h[1]}₽) - {h[2][:10]}" for h in hist]) or "Пусто..."
    
    text = (
        f"👤 <b>КАБИНЕТ ПАССАЖИРА</b>\n"
        f"👑 Статус: <b>{status}</b>\n"
        f"💰 Потрачено: <b>{spent}₽</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📜 <b>ИСТОРИЯ ПОЕЗДОК:</b>\n{h_text}"
    )
    
    # Если есть активный заказ - кнопка чата
    kb = []
    if message.from_user.id in active_orders:
        kb.append([InlineKeyboardButton(text="💬 ВЕРНУТЬСЯ В ЧАТ", callback_data="enter_chat")])
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb) if kb else None)

# ==========================================
# 💬 LIVE ЧАТ
# ==========================================
@dp.callback_query(F.data == "enter_chat")
async def enter_chat_mode(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    # Определяем собеседника
    partner_id = None
    
    # Если это клиент
    if user_id in active_orders:
        order = active_orders[user_id]
        if order.get('driver_id'): partner_id = order['driver_id']
    
    # Если это водитель (ищем среди заказов)
    if not partner_id:
        for cid, order in active_orders.items():
            if order.get('driver_id') == user_id:
                partner_id = cid
                break
    
    if not partner_id:
        return await callback.answer("❌ Нет активного собеседника", show_alert=True)
        
    await state.update_data(chat_partner=partner_id)
    await state.set_state(ChatState.active)
    
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🚪 Выйти из чата")]], resize_keyboard=True)
    await callback.message.answer("💬 <b>ЧАТ ВКЛЮЧЕН!</b>\nПишите сообщение, отправляйте фото или голосовые. Собеседник увидит это мгновенно.", reply_markup=kb)
    await callback.answer()

@dp.message(ChatState.active)
async def chat_relay(message: types.Message, state: FSMContext):
    if message.text == "🚪 Выйти из чата":
        await state.clear()
        # Возвращаем клавиатуру в зависимости от роли
        if is_client_accepted(message.from_user.id) and not get_driver_info(message.from_user.id):
            return await message.answer("Вы вышли из чата.", reply_markup=main_kb)
        else:
            # Для водителя
            return await cab(message, state) # Возврат в кабинет

    data = await state.get_data()
    partner_id = data.get('chat_partner')
    
    if not partner_id:
        await state.clear()
        return await message.answer("❌ Собеседник отключился.")
        
    try:
        # Пересылка копии сообщения
        await message.copy_to(chat_id=partner_id)
    except:
        await message.answer("❌ Не удалось доставить сообщение (возможно, собеседник заблокировал бота).")

# ==========================================
# 🚕 ТАКСИ
# ==========================================
# ... (Update монитор тот же) ...
async def update_admins_monitor(client_id, taking_driver_id):
    order = active_orders.get(client_id)
    if not order or 'admin_msg_ids' not in order: return
    drv_info = get_driver_info(taking_driver_id)
    role = "АДМИН" if is_admin(taking_driver_id) else "ВОДИТЕЛЬ"
    text = f"🚫 <b>ЗАКАЗ ЗАБРАЛ: {role} {drv_info[0]}</b>\nФИО: {drv_info[7]}\nАвто: {drv_info[1]}\n\n{order.get('broadcasting_text','')}"
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
    
    await bot.send_message(client_id, "📡 <i>Ищем водителей...</i>")
    await asyncio.sleep(1.5)
    
    simple_drivers = [d for d in get_active_drivers() if d not in admins]
    tasks = [safe_send_message(d, f"⚡ <b>ЗАКАЗ!</b>\n{order_text}", driver_kb) for d in simple_drivers]
    if tasks: await asyncio.gather(*tasks)

@dp.message(F.text == "🚕 Заказать такси (Поиск)")
async def taxi_start(message: types.Message, state: FSMContext):
    await state.clear(); await message.answer("📍 <b>Откуда вас забрать?</b>", reply_markup=types.ReplyKeyboardRemove()); await state.set_state(OrderRide.waiting_for_from)

@dp.message(OrderRide.waiting_for_from)
async def taxi_fr(message: types.Message, state: FSMContext):
    await state.update_data(fr=message.text); await message.answer("🏁 <b>Куда поедем?</b>"); await state.set_state(OrderRide.waiting_for_to)

@dp.message(OrderRide.waiting_for_to)
async def taxi_to(message: types.Message, state: FSMContext):
    await state.update_data(to=message.text); await message.answer("📞 <b>Ваш телефон:</b>"); await state.set_state(OrderRide.waiting_for_phone)

@dp.message(OrderRide.waiting_for_phone)
async def taxi_ph(message: types.Message, state: FSMContext):
    await state.update_data(ph=message.text); await message.answer("💰 <b>Ваша цена?</b>"); await state.set_state(OrderRide.waiting_for_price)

@dp.message(OrderRide.waiting_for_price)
async def taxi_send(message: types.Message, state: FSMContext):
    data = await state.get_data(); cid = message.from_user.id
    active_orders[cid] = {"type": "taxi", "status": "pending", "price": message.text, "from": data['fr'], "to": data['to'], "phone": data['ph']}
    await message.answer("✅ <b>Заявка создана!</b>", reply_markup=main_kb); await state.clear()
    txt = f"🚕 <b>ЗАКАЗ ТАКСИ</b>\n📍 {data['fr']} -> {data['to']}\n💰 {message.text}"
    dkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ВЗЯТЬ", callback_data=f"take_taxi_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"cnt_taxi_{cid}")]])
    await broadcast_order_to_drivers(cid, txt, dkb, dkb)

@dp.callback_query(F.data.startswith("take_taxi_"))
async def take_taxi(c: types.CallbackQuery, state: FSMContext):
    cid = int(c.data.split("_")[-1]); did = c.from_user.id; order = active_orders.get(cid)
    if not order or order["status"] != "pending": return await c.answer("Занято!")
    order["status"] = "accepted"; order["driver_id"] = did; set_linked_driver(cid, did); await update_admins_monitor(cid, did)
    
    info = get_driver_info(did)
    # КНОПКИ ДЛЯ ВОДИТЕЛЯ
    drv_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 ЧАТ С КЛИЕНТОМ", callback_data="enter_chat")],
        [InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ", callback_data=f"ask_finish_{cid}")]
    ])
    await c.message.edit_text(f"✅ <b>Взято!</b>\n📞 {order['phone']}", reply_markup=drv_kb)
    
    # КНОПКИ ДЛЯ КЛИЕНТА (С ЧАТОМ и SOS)
    cli_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 ЧАТ С ВОДИТЕЛЕМ", callback_data="enter_chat")],
        [InlineKeyboardButton(text="💸 Я ОПЛАТИЛ", callback_data=f"cli_pay_{cid}"), InlineKeyboardButton(text="➕ ДОБАВИТЬ ТОЧКУ", callback_data="add_stop")],
        [InlineKeyboardButton(text="🆘 SOS", callback_data=f"sos_alert_{did}")]
    ])
    await bot.send_message(cid, f"🚕 <b>ВОДИТЕЛЬ ВЫЕХАЛ!</b>\n👤 {info[7]}\n🚘 {info[1]}\n📞 {order['phone']}\n💰 {order['price']}₽\n🔐 Код: <code>{info[5]}</code>", reply_markup=cli_kb)

@dp.callback_query(F.data.startswith("sos_alert_"))
async def sos_alert(c: types.CallbackQuery, state: FSMContext):
    did = int(c.data.split("_")[2])
    cid = c.from_user.id
    await c.answer("🚨 SOS ОТПРАВЛЕН АДМИНАМ!", show_alert=True)
    for adm in get_all_admins_ids():
        await bot.send_message(adm, f"🆘 <b>ТРЕВОГА!</b>\nКлиент: {cid}\nВодитель: {did}\nСвяжитесь срочно!")

# --- ОПЛАТА ---
@dp.callback_query(F.data.startswith("cli_pay_"))
async def cli_pay(c: types.CallbackQuery, state: FSMContext):
    cid = int(c.data.split("_")[2]); did = active_orders[cid]['driver_id']
    await bot.send_message(did, "💸 <b>Клиент оплатил!</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data=f"drv_confirm_{cid}")]]))
    await c.message.edit_text("⏳ Ждем подтверждения...")

@dp.callback_query(F.data.startswith("drv_confirm_"))
async def drv_con(c: types.CallbackQuery, state: FSMContext):
    cid = int(c.data.split("_")[2]); await bot.send_message(cid, "✅ <b>Оплата принята!</b>"); await c.message.edit_text("✅ Принято.")

@dp.callback_query(F.data == "add_stop")
async def add_stop_s(c: types.CallbackQuery, s: FSMContext): await c.message.answer("Адрес:"); await s.set_state(AddStop.waiting_for_address)
@dp.message(AddStop.waiting_for_address)
async def add_stop_p(m: types.Message, s: FSMContext): await s.update_data(a=m.text); await m.answer("Доплата:"); await s.set_state(AddStop.waiting_for_price)
@dp.message(AddStop.waiting_for_price)
async def add_stop_f(m: types.Message, s: FSMContext):
    d = await s.get_data(); cid = m.from_user.id; did = active_orders[cid]['driver_id']
    await bot.send_message(did, f"📍 <b>Точка:</b> {d['a']}\n💰 +{m.text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"stop_ok_{cid}_{m.text}")]]))
    await m.answer("⏳ Отправлено..."); await s.clear()

@dp.callback_query(F.data.startswith("stop_ok_"))
async def stop_ok(c: types.CallbackQuery, state: FSMContext):
    cid = int(c.data.split("_")[2]); extra = int(c.data.split("_")[3])
    order = active_orders.get(cid); order['price'] = str(extract_price(order['price']) + extra)
    await bot.send_message(cid, f"✅ <b>Принято!</b> Новая цена: {order['price']}")
    await c.message.edit_text("✅ Точка добавлена.")

@dp.callback_query(F.data.startswith("ask_finish_"))
async def ask_fin(c: types.CallbackQuery, state: FSMContext):
    cid = int(c.data.split("_")[2])
    await bot.send_message(cid, "🏁 <b>Оцените поездку:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⭐ 5", callback_data=f"rate_{cid}_5")]]))
    await c.message.edit_text("✅ Закрыто.")

@dp.callback_query(F.data.startswith("rate_"))
async def rate(c: types.CallbackQuery, state: FSMContext):
    cid = int(c.data.split("_")[1]); order = active_orders.get(cid)
    if order:
        did = order['driver_id']; pr = extract_price(order['price'])
        log_order(cid, did, "Такси", pr) # Лог в историю
        update_client_spent(cid, pr)     # Обновляем траты клиента
        update_order_rating(5, did); add_commission(did, pr)
        await bot.send_message(did, "🎉 <b>Оценка: 5⭐</b>"); del active_orders[cid]
    await c.message.edit_text("Спасибо!")

# --- ТОРГ ---
@dp.callback_query(F.data.startswith("cnt_"))
async def cnt_s(c: types.CallbackQuery, s: FSMContext): await s.update_data(cid=int(c.data.split("_")[2])); await c.message.answer("Цена:"); await s.set_state(DriverCounterOffer.waiting_for_offer)
@dp.message(DriverCounterOffer.waiting_for_offer)
async def cnt_snd(m: types.Message, s: FSMContext):
    d = await s.get_data(); cid = d['cid']; did = m.from_user.id
    await bot.send_message(cid, f"⚡ <b>Водитель предлагает:</b> {m.text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"take_taxi_{cid}"), InlineKeyboardButton(text="❌", callback_data="decline_tos")]]))
    await m.answer("Отправлено."); await s.clear()

# ==========================================
# 📜 CRAZY МЕНЮ
# ==========================================
@dp.message(F.text == "📜 CRAZY МЕНЮ (Категории)")
async def show_cats(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    did = get_linked_driver(message.from_user.id)
    if not did: return await message.answer("🔒 Введите ключ водителя!")
    active_srv = get_driver_active_services(did)
    btns = []
    for cat_id, cat_name in CATEGORIES.items():
        if any(srv['cat'] == cat_id and key in active_srv for key, srv in CRAZY_SERVICES.items()):
            btns.append([InlineKeyboardButton(text=cat_name, callback_data=f"cat_{cat_id}")])
    await message.answer("🔥 <b>ВЫБЕРИТЕ УРОВЕНЬ:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("cat_"))
async def open_cat(c: types.CallbackQuery, state: FSMContext):
    cat_id = int(c.data.split("_")[1]); cid = c.from_user.id; did = get_linked_driver(cid); active_srv = get_driver_active_services(did)
    btns = [[InlineKeyboardButton(text=f"{val['name']} — {val['price']}₽", callback_data=f"srv_{key}")] for key, val in CRAZY_SERVICES.items() if val['cat'] == cat_id and key in active_srv]
    btns.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_cats")])
    await c.message.edit_text(f"📂 <b>{CATEGORIES[cat_id]}</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "back_cats")
async def back_cats(c: types.CallbackQuery, state: FSMContext):
    await show_cats(c.message, state) # Reuse logic

@dp.callback_query(F.data.startswith("srv_"))
async def sel_srv(c: types.CallbackQuery, state: FSMContext):
    key = c.data.split("_")[1]; srv = CRAZY_SERVICES[key]
    await c.message.edit_text(f"🎭 <b>{srv['name']}</b>\n💰 {srv['price']}₽\n<i>{srv['desc']}</i>", 
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ЗАКАЗАТЬ", callback_data=f"do_{key}")], [InlineKeyboardButton(text="🔙", callback_data=f"cat_{srv['cat']}")]]))

@dp.callback_query(F.data.startswith("do_"))
async def do_ord(c: types.CallbackQuery, state: FSMContext):
    key = c.data.split("_")[1]; srv = CRAZY_SERVICES[key]; cid = c.from_user.id; did = get_linked_driver(cid)
    active_orders[cid] = {"type": "crazy", "price": str(srv["price"]), "driver_id": did}
    # ЧАТ С ВОДИТЕЛЕМ ДОСТУПЕН ПРИ ЗАКАЗЕ УСЛУГИ
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"c_acc_{cid}"), InlineKeyboardButton(text="💬 ЧАТ", callback_data="enter_chat")]])
    await bot.send_message(did, f"🔔 <b>УСЛУГА: {srv['name']}</b>\n💰 {srv['price']}", reply_markup=kb)
    await c.message.edit_text("⏳ Ждем...")

@dp.callback_query(F.data.startswith("c_acc_"))
async def c_acc(c: types.CallbackQuery, state: FSMContext):
    cid = int(c.data.split("_")[2]); i = get_driver_info(c.from_user.id)
    await bot.send_message(cid, f"✅ Принято! Реквизиты: <code>{i[2]}</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 ОПЛАТИЛ", callback_data=f"cli_pay_{cid}"), InlineKeyboardButton(text="💬 ЧАТ", callback_data="enter_chat")]]))
    await c.message.edit_text("✅ В работе.")

@dp.message(F.text == "💡 Свой вариант (Идея)")
async def idea_h(m: types.Message, s: FSMContext): await m.answer("Идея:"); await s.set_state(CustomIdea.waiting_for_idea)
@dp.message(CustomIdea.waiting_for_idea)
async def idea_p(m: types.Message, s: FSMContext): await s.update_data(i=m.text); await m.answer("Цена:"); await s.set_state(CustomIdea.waiting_for_price)
@dp.message(CustomIdea.waiting_for_price)
async def idea_s(m: types.Message, s: FSMContext):
    d = await s.get_data(); cid = m.from_user.id
    active_orders[cid] = {"type":"crazy", "price":m.text, "driver_id":0} 
    await broadcast_order_to_drivers(cid, f"💡 {d['i']}\n💰 {m.text}", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"take_taxi_{cid}")]]) , InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"take_taxi_{cid}")]]))
    await m.answer("✅"); await s.clear()

# ==========================================
# 🪪 КАБИНЕТ + РЕГИСТРАЦИЯ
# ==========================================
@dp.message(Command("cab"))
async def cab(message: types.Message, state: FSMContext):
    await state.clear()
    info = get_driver_info(message.from_user.id)
    if not info: return await message.answer("❌ Нет регистрации. /drive")
    
    role_map = {'owner':"👑 БОСС", 'admin':"👮‍♂️ АДМИН", 'driver':"🚕 ВОДИТЕЛЬ"}
    txt = (f"🪪 <b>КАБИНЕТ ПИЛОТА</b>\n🔰 Роль: {role_map.get(info[6])}\n👤 {info[7]}\n💰 Баланс: {info[3]}₽\n🔑 Код: <code>{info[5]}</code>")
    kb = [
        [InlineKeyboardButton(text="🎛 Настроить меню", callback_data="driver_menu_edit")],
        [InlineKeyboardButton(text="💸 Оплатить долг", callback_data="cab_pay")]
    ]
    await message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# (КОНСТРУКТОР МЕНЮ)
@dp.callback_query(F.data == "driver_menu_edit")
async def driver_menu_editor(callback: types.CallbackQuery, state: FSMContext):
    did = callback.from_user.id
    active_keys = get_driver_active_services(did)
    kb_builder = []
    for key, val in CRAZY_SERVICES.items():
        status = "✅" if key in active_keys else "❌"
        kb_builder.append([InlineKeyboardButton(text=f"{status} {val['name']}", callback_data=f"toggle_srv_{key}")])
    kb_builder.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_cab")])
    await callback.message.edit_text("🎛 <b>НАСТРОЙКА МЕНЮ</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_builder))

@dp.callback_query(F.data.startswith("toggle_srv_"))
async def toggle_srv_handler(callback: types.CallbackQuery, state: FSMContext):
    key = callback.data.split("toggle_srv_")[1]
    toggle_driver_service(callback.from_user.id, key)
    await driver_menu_editor(callback, state)

@dp.callback_query(F.data == "back_to_cab")
async def back_to_cab_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await cab(callback.message, state)

@dp.message(Command("vip"))
async def vip_reg(message: types.Message, state: FSMContext):
    await state.clear()
    try:
        key = message.text.split()[1]
        if key == VIP_DRIVER_KEY:
            await state.update_data(role="driver"); await message.answer("ФИО:"); await state.set_state(DriverVipRegistration.waiting_for_fio)
    except: await message.answer("Формат: /vip КОД")

@dp.message(DriverVipRegistration.waiting_for_fio)
async def vip_fio(m: types.Message, s: FSMContext): await s.update_data(fio=m.text); await m.answer("Авто:"); await s.set_state(DriverVipRegistration.waiting_for_car)
@dp.message(DriverVipRegistration.waiting_for_car)
async def vip_car(m: types.Message, s: FSMContext): await s.update_data(car=m.text); await m.answer("Реквизиты:"); await s.set_state(DriverVipRegistration.waiting_for_payment_info)
@dp.message(DriverVipRegistration.waiting_for_payment_info)
async def vip_pay(m: types.Message, s: FSMContext): await s.update_data(pay=m.text); await m.answer("Код:"); await s.set_state(DriverVipRegistration.waiting_for_code)
@dp.message(DriverVipRegistration.waiting_for_code)
async def vip_fin(m: types.Message, s: FSMContext):
    d = await s.get_data(); code = m.text.upper().strip()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, role, commission, balance, rating_sum, rating_count) VALUES (?, ?, ?, ?, ?, ?, 'active', 'driver', 10, 0, 0, 0)", 
                     (m.from_user.id, m.from_user.username or "NoUser", d['fio'], d['car'], d['pay'], code))
        conn.commit()
        init_driver_services_defaults(m.from_user.id)
        await m.answer("✅ Принят! /cab")
    except: await m.answer("❌ Код занят")
    conn.close(); await s.clear()

@dp.message(Command("driver", "drive"))
async def reg_start(m: types.Message, s: FSMContext): await s.clear(); await m.answer("ФИО:"); await s.set_state(DriverRegistration.waiting_for_fio)
@dp.message(DriverRegistration.waiting_for_fio)
async def r1(m: types.Message, s: FSMContext): await s.update_data(fio=m.text); await m.answer("Авто:"); await s.set_state(DriverRegistration.waiting_for_car)
@dp.message(DriverRegistration.waiting_for_car)
async def r2(m: types.Message, s: FSMContext): await s.update_data(car=m.text); await m.answer("Реквизиты:"); await s.set_state(DriverRegistration.waiting_for_payment_info)
@dp.message(DriverRegistration.waiting_for_payment_info)
async def r3(m: types.Message, s: FSMContext): await s.update_data(pay=m.text); await m.answer("Код:"); await s.set_state(DriverRegistration.waiting_for_code)
@dp.message(DriverRegistration.waiting_for_code)
async def r4(m: types.Message, s: FSMContext):
    d = await s.get_data(); code = m.text.upper().strip(); conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, commission, role, balance, rating_sum, rating_count) VALUES (?, ?, ?, ?, ?, ?, 'pending', 10, 'driver', 0, 0, 0)", 
                     (m.from_user.id, m.from_user.username or "NoUser", d['fio'], d['car'], d['pay'], code))
        conn.commit()
        init_driver_services_defaults(m.from_user.id)
        await m.answer("📝 Жди.")
        await notify_admins(f"🚨 НОВЫЙ: {d['fio']}", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"adm_app_{m.from_user.id}")]]))
    except: await m.answer("❌ Занят")
    conn.close(); await s.clear()

# ==========================================
# 👑 АДМИНКА
# ==========================================
@dp.message(Command("admin"))
async def adm(m: types.Message, s: FSMContext):
    await s.clear(); 
    if not is_admin(m.from_user.id): return await m.answer("⛔")
    conn = sqlite3.connect(DB_PATH); drs = conn.execute("SELECT user_id, fio, balance FROM drivers").fetchall(); conn.close()
    txt = "👑 <b>АДМИНКА</b>\n" + "\n".join([f"• {d[1]} | {d[2]}₽ | /edit_{d[0]}" for d in drs])
    await m.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢", callback_data="admin_broadcast")]]))

@dp.callback_query(F.data.startswith("adm_app_"))
async def adm_ap(c: types.CallbackQuery, s: FSMContext):
    if not is_admin(c.from_user.id): return
    did = int(c.data.split("_")[2]); update_driver_field(did, "status", "active"); await c.message.edit_text("✅")
    try: await bot.send_message(did, "🎉 Принят! /cab")
    except: pass

@dp.message(F.text.startswith("/edit_"))
async def ed(m: types.Message, s: FSMContext):
    if not is_admin(m.from_user.id): return
    did = int(m.text.split("_")[1]); await s.update_data(target_did=did)
    await m.answer("Меню:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Счет", callback_data=f"adm_bill_{did}")]]))

@dp.callback_query(F.data.startswith("adm_bill_"))
async def bl(c: types.CallbackQuery, s: FSMContext): await s.update_data(target_did=int(c.data.split("_")[2])); await c.message.answer("Текст:"); await s.set_state(AdminBilling.waiting_for_custom_req)
@dp.message(AdminBilling.waiting_for_custom_req)
async def bl_s(m: types.Message, s: FSMContext):
    d = await s.get_data(); await bot.send_message(d['target_did'], f"⚠️ <b>СЧЕТ:</b>\n{m.text}"); await m.answer("✅"); await s.clear()

@dp.callback_query(F.data == "admin_broadcast")
async def brd(c: types.CallbackQuery, s: FSMContext): await c.message.answer("Текст:"); await s.set_state(AdminBroadcast.waiting_for_text)
@dp.message(AdminBroadcast.waiting_for_text)
async def brd_s(m: types.Message, s: FSMContext):
    for d in get_active_drivers(): await safe_send_message(d, f"📢 {m.text}"); 
    await m.answer("✅"); await s.clear()

# ==========================================
# 🔐 ВВОД КЛЮЧА
# ==========================================
@dp.message(F.text == "🔐 Ввести КЛЮЧ услуги")
async def key_st(m: types.Message, s: FSMContext): await s.clear(); await m.answer("Код:"); await s.set_state(UnlockMenu.waiting_for_key)
@dp.message(UnlockMenu.waiting_for_key)
async def key_pr(m: types.Message, s: FSMContext):
    drv = get_driver_by_code(m.text.strip().upper())
    if drv: set_linked_driver(m.from_user.id, drv[0]); await m.answer(f"🔓 OK: {drv[3]}", reply_markup=main_kb); await s.clear()
    else: await m.answer("❌")

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
