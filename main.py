import asyncio
import logging
import os
import sqlite3
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
    logging.error("⛔ КРИТИЧЕСКАЯ ОШИБКА: Токены не найдены!")
    exit()

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
# ⚖️ ЮРИДИЧЕСКАЯ БАЗА
# ==========================================
LEGAL_TEXT = (
    "<b>📜 ПУБЛИЧНАЯ ОФЕРТА И ПРАВИЛА СЕРВИСА</b>\n\n"
    "1. <b>Статус Сервиса:</b> Бот является информационным агрегатором, предоставляющим доступ к базе данных сценариев развлекательного досуга.\n"
    "2. <b>Отказ от ответственности:</b> Сервис НЕ является перевозчиком. Услуги перевозки оказываются независимыми Водителями, имеющими лицензии.\n"
    "3. <b>Безопасность:</b> Клиент обязуется не требовать действий, нарушающих ПДД. Водитель вправе отказать в услуге, если это угрожает безопасности.\n"
    "4. <b>Финансы:</b> Оплата поездки производится Водителю. Оплата за Crazy-услуги — это добровольное вознаграждение артиста.\n"
    "5. <b>Согласие:</b> Нажимая «Старт», вы подтверждаете отсутствие медицинских противопоказаний к эмоциональным нагрузкам."
)

# ==========================================
# 🗄️ БАЗА ДАННЫХ
# ==========================================
DB_PATH = "/data/taxi_db.sqlite" if os.path.exists("/data") else "taxi_db.sqlite"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Водители
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
    # Клиенты
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            user_id INTEGER PRIMARY KEY,
            linked_driver_id INTEGER DEFAULT NULL
        )
    """)
    # История
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                (admin_id, "BOSS", "Владелец Сервиса", "VIP Auto", "CASH", f"ADMIN_{admin_id}")
            )
        else:
            cursor.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (admin_id,))
    
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 🛠 ВАЖНЫЕ ФУНКЦИИ (В САМОМ ВЕРХУ!)
# ==========================================

def is_client_accepted(user_id):
    """Проверка: принял ли клиент оферту"""
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

def log_order(driver_id, service_name, price):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO order_history (driver_id, service_name, price) VALUES (?, ?, ?)", (driver_id, service_name, price))
    last_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return last_id

def update_order_rating(order_id, rating, driver_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE drivers SET rating_sum = rating_sum + ?, rating_count = rating_count + 1 WHERE user_id = ?", (rating, driver_id))
    conn.execute("UPDATE order_history SET rating = ? WHERE id = ?", (rating, order_id))
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
    "candy": {"cat": 1, "price": 0, "name": "🍬 Конфетка", "desc": "Водитель с максимально серьезным лицом вручает вам элитную конфету."},
    "nose": {"cat": 1, "price": 300, "name": "👃 Палец в носу", "desc": "Всю поездку водитель едет с пальцем в носу. Вы платите за его страдания."},
    "butler": {"cat": 1, "price": 200, "name": "🤵 Дворецкий", "desc": "Водитель выходит, открывает вам дверь, кланяется и называет 'Сир'."},
    "joke": {"cat": 1, "price": 50, "name": "🤡 Тупой анекдот", "desc": "Анекдот категории 'Б'. Смеяться не обязательно."},
    "silence": {"cat": 1, "price": 150, "name": "🤐 Полная тишина", "desc": "Режим 'Ниндзя'. Музыка выкл, водитель молчит как рыба."},
    "granny": {"cat": 2, "price": 800, "name": "👵 Бабушка-ворчунья", "desc": "Ролевая игра. Всю дорогу буду бубнить: 'Куда прешь, наркоман!'."},
    "gopnik": {"cat": 2, "price": 500, "name": "🍺 Четкий пацанчик", "desc": "Пацанский рэп, 'братишка', решение вопросиков по телефону."},
    "guide": {"cat": 2, "price": 600, "name": "🗣 Ужасный гид", "desc": "Экскурсия с выдуманными фактами."},
    "psych": {"cat": 2, "price": 1000, "name": "🧠 Психолог", "desc": "Вы жалуетесь на жизнь, водитель кивает и дает советы."},
    "spy": {"cat": 3, "price": 2000, "name": "🕵️‍♂️ Шпион 007", "desc": "Черные очки, паранойя, проверка хвоста."},
    "karaoke": {"cat": 3, "price": 5000, "name": "🎤 Адское Караоке", "desc": "Орем песни на полную! Фальшиво, но душевно."},
    "dance": {"cat": 3, "price": 15000, "name": "💃 Танцы на капоте", "desc": "Водитель танцует макарену перед капотом на светофоре."},
    "kidnap": {"cat": 4, "price": 30000, "name": "🎭 Дружеское похищение", "desc": "Вас (понарошку) грузят в багажник и везут в лес."},
    "tarzan": {"cat": 4, "price": 50000, "name": "🦍 Тарзан-Шоу", "desc": "Крики, удары в грудь, рычание на прохожих."},
    "burn": {"cat": 4, "price": 1000000, "name": "🔥 Сжечь машину", "desc": "Едем на пустырь. Вы платите лям, я даю канистру."},
    "eyes": {"cat": 5, "price": 0, "name": "👁️ Глаз-алмаз", "desc": "Изысканный комплимент вашим глазам."},
    "smile": {"cat": 5, "price": 0, "name": "😁 Улыбка", "desc": "Водитель скажет, что ваша улыбка освещает салон."},
    "style": {"cat": 5, "price": 0, "name": "👠 Икона стиля", "desc": "Восхищение вашим образом."},
    "improv": {"cat": 5, "price": 0, "name": "✨ Импровизация", "desc": "Водитель сам найдет, что в вас похвалить."},
    "propose": {"cat": 5, "price": 1000, "name": "💍 Сделать предложение", "desc": "Вы делаете предложение водителю. ⚠️ ПРИ ОТКАЗЕ ДЕНЬГИ НЕ ВОЗВРАЩАЮТСЯ!"}
}

CATEGORIES = {1: "🟢 ЛАЙТ", 2: "🟡 МЕДИУМ", 3: "🔴 ХАРД", 4: "☠️ VIP БЕЗУМИЕ", 5: "🌹 ДЛЯ ДАМ"}

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

# ==========================================
# ⌨️ UI
# ==========================================
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚕 Заказать такси (Поиск)")],
        [KeyboardButton(text="🔐 Ввести КЛЮЧ услуги")],
        [KeyboardButton(text="📜 CRAZY МЕНЮ (Категории)")],
        [KeyboardButton(text="📄 ПРАВИЛА / ОФЕРТА")],
        [KeyboardButton(text="⚖️ Вызвать адвоката")]
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
        await message.answer(
            "⚠️ <b>CRAZY TAXI: ЗОНА ПОВЫШЕННОГО РИСКА</b>\n\n"
            "Мы не возим скучных людей. Мы продаем эмоции.\n\n"
            "<b>📜 Главное правило:</b>\n"
            "Водитель — независимый художник. Вы — ценитель искусства.\n\n"
            "Готовы рискнуть?", 
            reply_markup=tos_kb
        )

@dp.callback_query(F.data == "accept_tos")
async def tos_accepted(callback: types.CallbackQuery, state: FSMContext):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (callback.from_user.id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("🔥 <b>КОНТРАКТ ПОДПИСАН!</b>")
    await callback.message.answer("Добро пожаловать в Элитный Сервис. Выбирай 👇", reply_markup=main_kb)

@dp.callback_query(F.data == "decline_tos")
async def tos_declined(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🚶‍♂️ Выход там.")

async def check_tos(message: types.Message) -> bool:
    if not is_client_accepted(message.from_user.id):
        await message.answer("🛑 <b>ДОСТУП ЗАПРЕЩЕН!</b>\nНажмите /start.")
        return False
    return True

@dp.message(F.text == "📄 ПРАВИЛА / ОФЕРТА")
async def show_legal(message: types.Message, state: FSMContext):
    await message.answer(LEGAL_TEXT)

@dp.message(F.text == "⚖️ Вызвать адвоката")
async def lawyer_menu(message: types.Message, state: FSMContext):
    await message.answer("⚖️ <b>ЮРИДИЧЕСКИЙ ОТДЕЛ</b>\nНаш партнер:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚨 ПЕРЕЙТИ К АДВОКАТУ", url=LAWYER_LINK)]]))

# ==========================================
# 🚀 МОНИТОРИНГ
# ==========================================
async def update_admins_monitor(client_id, taking_driver_id):
    order = active_orders.get(client_id)
    if not order or 'admin_msg_ids' not in order: return
    
    drv_info = get_driver_info(taking_driver_id)
    drv_name = f"@{drv_info[0]}" if drv_info[0] else "Unknown"
    fio = drv_info[7] if drv_info[7] else "Не указано"
    role = "АДМИН" if is_admin(taking_driver_id) else "ВОДИТЕЛЬ"
    
    text = f"🚫 <b>ЗАКАЗ ЗАБРАЛ: {role} {drv_name}</b>\nФИО: {fio}\nАвто: {drv_info[1]}\n\n{order.get('broadcasting_text','')}"
    
    for admin_id, msg_id in order['admin_msg_ids'].items():
        try: await bot.edit_message_text(chat_id=admin_id, message_id=msg_id, text=text, reply_markup=None)
        except: pass

async def broadcast_order_to_drivers(client_id, order_text, driver_kb, admin_kb):
    admins = get_all_admins_ids()
    admin_msg_map = {}
    admin_text = f"🚨 <b>МОНИТОРИНГ</b>\n\n{order_text}"
    
    for admin_id in admins:
        try:
            msg = await bot.send_message(admin_id, admin_text, reply_markup=admin_kb)
            admin_msg_map[admin_id] = msg.message_id
        except: pass
        
    if client_id in active_orders:
        active_orders[client_id]['admin_msg_ids'] = admin_msg_map
        active_orders[client_id]['broadcasting_text'] = order_text

    search_msg = await bot.send_message(client_id, "📡 <i>Ищем водителей...</i>")
    await asyncio.sleep(1.5)
    
    all_active = get_active_drivers()
    simple_drivers = [d for d in all_active if d not in admins]
    
    tasks = []
    for d_id in simple_drivers:
        tasks.append(safe_send_message(d_id, f"⚡ <b>ЗАКАЗ!</b>\n{order_text}", driver_kb))
    
    if tasks: await asyncio.gather(*tasks)
    await search_msg.edit_text("⏳ <b>Запрос отправлен!</b>")

# ==========================================
# 🚕 ТАКСИ + ТОРГ
# ==========================================
@dp.message(F.text == "🚕 Заказать такси (Поиск)")
async def taxi_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("📍 <b>Откуда вас забрать?</b>", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(OrderRide.waiting_for_from)

@dp.message(OrderRide.waiting_for_from)
async def taxi_fr(message: types.Message, state: FSMContext):
    await state.update_data(fr=message.text)
    await message.answer("🏁 <b>Куда поедем?</b>")
    await state.set_state(OrderRide.waiting_for_to)

@dp.message(OrderRide.waiting_for_to)
async def taxi_to(message: types.Message, state: FSMContext):
    await state.update_data(to=message.text)
    await message.answer("📞 <b>Ваш номер телефона:</b>")
    await state.set_state(OrderRide.waiting_for_phone)

@dp.message(OrderRide.waiting_for_phone)
async def taxi_ph(message: types.Message, state: FSMContext):
    await state.update_data(ph=message.text)
    await message.answer("💰 <b>Ваша цена?</b>")
    await state.set_state(OrderRide.waiting_for_price)

@dp.message(OrderRide.waiting_for_price)
async def taxi_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cid = message.from_user.id
    active_orders[cid] = {"type": "taxi", "status": "pending", "price": message.text, "from": data['fr'], "to": data['to'], "phone": data['ph'], "driver_offers": {}}
    await message.answer("✅ <b>Заявка создана!</b>", reply_markup=main_kb)
    await state.clear()
    
    text = f"🚕 <b>ЗАКАЗ ТАКСИ</b>\n📍 {data['fr']} -> {data['to']}\n💰 {message.text}"
    dkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ЗАБРАТЬ", callback_data=f"take_taxi_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"cnt_taxi_{cid}")]])
    akb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ АДМИН ПЕРЕХВАТ", callback_data=f"adm_take_taxi_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"cnt_taxi_{cid}")]])
    await broadcast_order_to_drivers(cid, text, dkb, akb)

@dp.callback_query(F.data.startswith("take_taxi_") | F.data.startswith("adm_take_taxi_"))
async def take_taxi(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[-1])
    did = callback.from_user.id
    order = active_orders.get(cid)
    
    if not order or order["status"] != "pending":
        await callback.answer("Упс! Заказ уже забрали.", show_alert=True)
        return
        
    order["status"] = "accepted"
    order["driver_id"] = did
    set_linked_driver(cid, did)
    await update_admins_monitor(cid, did)
    
    info = get_driver_info(did)
    drv_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ ПОЕЗДКУ", callback_data=f"ask_finish_{cid}")]])
    await callback.message.edit_text(f"✅ <b>Заказ принят!</b>\n📞 Телефон: {order['phone']}", reply_markup=drv_kb)
    
    cli_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Я ОПЛАТИЛ", callback_data=f"cli_pay_{cid}"), InlineKeyboardButton(text="➕ ДОБАВИТЬ ОСТАНОВКУ", callback_data="add_stop")]])
    await bot.send_message(cid, f"🚕 <b>ВОДИТЕЛЬ ВЫЕХАЛ!</b>\n👤 {info[7]}\n🚘 {info[1]}\n📞 {order['phone']}\n💰 {order['price']}₽\n🔐 Код: <code>{info[5]}</code>", reply_markup=cli_kb)

# --- ТОРГ ---
@dp.callback_query(F.data.startswith("cnt_"))
async def cnt_start(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    parts = callback.data.split("_")
    await state.update_data(cid=int(parts[2]), type=parts[1])
    await callback.message.answer("Введите вашу цену:")
    await state.set_state(DriverCounterOffer.waiting_for_offer)
    await callback.answer()

@dp.message(DriverCounterOffer.waiting_for_offer)
async def cnt_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cid, did = data['cid'], message.from_user.id
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ДА", callback_data=f"ok_off_{data['type']}_{cid}_{did}"), 
         InlineKeyboardButton(text="❌ НЕТ", callback_data=f"no_off_{cid}")]
    ])
    await bot.send_message(cid, f"⚡ <b>Водитель предлагает:</b> {message.text}", reply_markup=kb)
    await message.answer("Отправлено.")
    await state.clear()

@dp.callback_query(F.data.startswith("ok_off_"))
async def ok_off(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    cid, did = int(parts[3]), int(parts[4])
    active_orders[cid]['driver_id'] = did
    active_orders[cid]['status'] = 'accepted'
    set_linked_driver(cid, did)
    await update_admins_monitor(cid, did)
    
    info = get_driver_info(did)
    drv_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ", callback_data=f"ask_finish_{cid}")]])
    await bot.send_message(did, f"✅ Клиент согласен!\n📞 {active_orders[cid]['phone']}", reply_markup=drv_kb)
    
    cli_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Я ОПЛАТИЛ", callback_data=f"cli_pay_{cid}")]])
    await callback.message.edit_text(f"🚕 <b>Едет: {info[7]}</b>\n🔐 {info[5]}", reply_markup=cli_kb)

@dp.callback_query(F.data.startswith("no_off_"))
async def no_off(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Вы отказались.")

# --- ОПЛАТА ---
@dp.callback_query(F.data.startswith("cli_pay_"))
async def cli_pay(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2])
    order = active_orders.get(cid)
    if not order: return
    did = order['driver_id']
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ДЕНЬГИ ПРИШЛИ", callback_data=f"drv_confirm_{cid}")]])
    await bot.send_message(did, "💸 <b>Клиент нажал 'Оплачено'!</b> Проверьте поступление.", reply_markup=kb)
    await callback.message.edit_text("⏳ Ждем подтверждения водителя...")

@dp.callback_query(F.data.startswith("drv_confirm_"))
async def drv_confirm(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2])
    await bot.send_message(cid, "✅ <b>Оплата подтверждена!</b>")
    await callback.message.edit_text("✅ Оплата принята.")

# --- ДОП. ТОЧКИ ---
@dp.callback_query(F.data == "add_stop")
async def add_stop_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📍 <b>Куда заехать?</b> (Адрес):")
    await state.set_state(AddStop.waiting_for_address)
    await callback.answer()

@dp.message(AddStop.waiting_for_address)
async def add_stop_price(message: types.Message, state: FSMContext):
    await state.update_data(addr=message.text)
    await message.answer("💰 <b>Доплата (руб):</b>")
    await state.set_state(AddStop.waiting_for_price)

@dp.message(AddStop.waiting_for_price)
async def add_stop_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cid = message.from_user.id
    order = active_orders.get(cid)
    
    if not order or 'driver_id' not in order:
        await message.answer("❌ Ошибка.")
        await state.clear()
        return
        
    did = order['driver_id']
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ БЕРЕМ", callback_data=f"stop_ok_{cid}_{message.text}")],
        [InlineKeyboardButton(text="❌ ОТКАЗ", callback_data=f"stop_no_{cid}")]
    ])
    await bot.send_message(did, f"🔔 <b>НОВАЯ ТОЧКА!</b>\n\n📍 {data['addr']}\n💰 +{message.text}₽\nБерем?", reply_markup=kb)
    await message.answer("⏳ Отправлено водителю...")
    await state.clear()

@dp.callback_query(F.data.startswith("stop_ok_"))
async def stop_ok(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    cid = int(parts[2])
    extra = int(parts[3])
    
    order = active_orders.get(cid)
    if order:
        new_price = extract_price(order['price']) + extra
        order['price'] = str(new_price)
        await bot.send_message(cid, f"✅ <b>Водитель согласен!</b>\nНовая цена: {new_price}₽")
        drv_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ ПОЕЗДКУ", callback_data=f"ask_finish_{cid}")]])
        await callback.message.edit_text(f"✅ <b>Точка добавлена!</b>\nИтого: {new_price}₽", reply_markup=drv_kb)

@dp.callback_query(F.data.startswith("stop_no_"))
async def stop_no(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2])
    await bot.send_message(cid, "❌ <b>Водитель отказался.</b>")
    await callback.message.edit_text("❌ Отказ.")

# --- ЗАВЕРШЕНИЕ ---
@dp.callback_query(F.data.startswith("ask_finish_"))
async def ask_finish(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 1", callback_data=f"rate_{cid}_1"), InlineKeyboardButton(text="⭐ 5", callback_data=f"rate_{cid}_5")]
    ])
    await bot.send_message(cid, "🏁 <b>Приехали! Оцените:</b>", reply_markup=kb)
    await callback.message.edit_text("✅ <b>Поездка закрыта.</b>")

@dp.callback_query(F.data.startswith("rate_"))
async def rate_ride(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    cid = int(parts[1])
    rating = int(parts[2])
    order = active_orders.get(cid)
    if not order: 
        await callback.message.delete()
        return
    did = order['driver_id']
    pr = extract_price(order['price'])
    srv_name = order.get('service', {}).get('name', 'Такси')
    
    log_order(did, srv_name, pr)
    if rating > 0: update_order_rating(0, rating, did)
    add_commission(did, pr)
    
    await callback.message.edit_text("🙏 <b>Спасибо!</b>")
    await bot.send_message(did, f"🎉 <b>Оценка: {rating}⭐</b>\nБаланс обновлен.")
    if cid in active_orders: del active_orders[cid]

# ==========================================
# 📜 CRAZY МЕНЮ
# ==========================================
@dp.message(F.text == "📜 CRAZY МЕНЮ (Категории)")
async def show_cats(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    did = get_linked_driver(message.from_user.id)
    if not did:
        await message.answer("🔒 <b>НЕТ ДОСТУПА!</b>\nСядьте в машину и введите ключ.", reply_markup=main_kb)
        return
    btns = [[InlineKeyboardButton(text=n, callback_data=f"cat_{i}")] for i, n in CATEGORIES.items()]
    await message.answer("🔥 <b>ВЫБЕРИТЕ УРОВЕНЬ ЖЕСТКОСТИ:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("cat_"))
async def open_cat(callback: types.CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[1])
    btns = []
    for k, v in CRAZY_SERVICES.items():
        if v["cat"] == cat_id:
            btns.append([InlineKeyboardButton(text=f"{v['name']} — {v['price']}₽", callback_data=f"csel_{k}")])
    btns.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_cats")])
    await callback.message.edit_text(f"📂 <b>{CATEGORIES[cat_id]}</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "back_cats")
async def back_cats(callback: types.CallbackQuery, state: FSMContext):
    btns = [[InlineKeyboardButton(text=n, callback_data=f"cat_{i}")] for i, n in CATEGORIES.items()]
    await callback.message.edit_text("🔥 <b>УРОВНИ:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("csel_"))
async def sel_srv(callback: types.CallbackQuery, state: FSMContext):
    key = callback.data.split("_")[1]
    srv = CRAZY_SERVICES[key]
    text = f"🎭 <b>{srv['name']}</b>\n💰 <b>{srv['price']}₽</b>\n\n📝 <i>{srv['desc']}</i>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ЗАКАЗАТЬ", callback_data=f"do_order_{key}")], [InlineKeyboardButton(text="🔙 Назад", callback_data=f"cat_{srv['cat']}")]])
    await callback.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("do_order_"))
async def do_order(callback: types.CallbackQuery, state: FSMContext):
    key = callback.data.split("_")[-1] 
    srv = CRAZY_SERVICES[key]
    cid = callback.from_user.id
    did = get_linked_driver(cid)
    
    active_orders[cid] = {"type": "crazy", "status": "direct", "price": str(srv["price"]), "driver_id": did, "service": srv}
    await callback.message.edit_text("⏳ <b>Отправляем...</b>")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"drv_acc_{cid}")]])
    await bot.send_message(did, f"🔔 <b>ЗАКАЗ</b>\n🎭 {srv['name']}\n💰 {srv['price']}₽\n📝 {srv['desc']}", reply_markup=kb)

@dp.callback_query(F.data.startswith("drv_acc_"))
async def drv_acc_crazy(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2])
    order = active_orders.get(cid)
    if not order: return
    info = get_driver_info(callback.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ГОТОВО / ОПЛАТИЛ", callback_data=f"ask_finish_{cid}")]])
    await bot.send_message(cid, f"✅ <b>Водитель принял!</b>\n💳 Перевод: <code>{info[2]}</code>", reply_markup=kb)
    await callback.message.edit_text("✅ В работе.")

@dp.message(F.text == "💡 Свой вариант (Идея)")
async def idea_h(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Идея:")
    await state.set_state(CustomIdea.waiting_for_idea)

@dp.message(CustomIdea.waiting_for_idea)
async def idea_p(message: types.Message, state: FSMContext):
    await state.update_data(idea=message.text)
    await message.answer("Бюджет:")
    await state.set_state(CustomIdea.waiting_for_price)

@dp.message(CustomIdea.waiting_for_price)
async def idea_s(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cid = message.from_user.id
    active_orders[cid] = {"type": "crazy", "status": "pending", "price": message.text, "service": {"name": "Идея", "desc": data['idea']}, "driver_offers": {}}
    await message.answer("✅ Отправлено!", reply_markup=main_kb)
    await state.clear()
    dkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ЗАБРАТЬ", callback_data=f"take_crazy_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"cnt_crazy_{cid}")]])
    await broadcast_order_to_drivers(cid, f"💡 <b>ИДЕЯ:</b> {data['idea']}\n💰 {message.text}", dkb, dkb)

# ==========================================
# 🪪 КАБИНЕТ + РЕГИСТРАЦИЯ
# ==========================================
@dp.message(Command("cab"))
async def cab(message: types.Message, state: FSMContext):
    await state.clear()
    info = get_driver_info(message.from_user.id)
    if not info:
        await message.answer("❌ Нет регистрации. /drive")
        return
    role_map = {'owner':"👑 БОСС", 'admin':"👮‍♂️ АДМИН", 'driver':"🚕 ВОДИТЕЛЬ"}
    txt = (f"🪪 <b>КАБИНЕТ ПИЛОТА</b>\n🔰 Роль: <b>{role_map.get(info[6])}</b>\n👤 {info[7]}\n💰 Баланс: <b>{info[3]}₽</b>\n🔑 Код: <code>{info[5]}</code>")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Оплатить долг", callback_data="cab_pay")]])
    await message.answer(txt, reply_markup=kb)

@dp.callback_query(F.data == "cab_pay")
async def cab_pay(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    info = get_driver_info(callback.from_user.id)
    boss = get_driver_info(OWNER_ID)
    await callback.message.answer(f"💸 Долг: <b>{info[3]}₽</b>\nПереведи Боссу: <b>{boss[2]}</b>")
    await callback.answer()

@dp.message(Command("vip"))
async def vip_reg(message: types.Message, state: FSMContext):
    await state.clear()
    try:
        key = message.text.split()[1]
        if key == VIP_DRIVER_KEY:
            await state.update_data(role="driver")
            await message.answer(f"🔑 <b>КЛЮЧ ВОДИТЕЛЯ ПРИНЯТ!</b>\n\nВведите ФИО:")
            await state.set_state(DriverVipRegistration.waiting_for_fio)
        else:
            await message.answer("❌ Неверный ключ.")
    except: await message.answer("Формат: /vip КОД")

@dp.message(DriverVipRegistration.waiting_for_fio)
async def vip_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await message.answer("🚘 Авто:")
    await state.set_state(DriverVipRegistration.waiting_for_car)

@dp.message(DriverVipRegistration.waiting_for_car)
async def vip_car(message: types.Message, state: FSMContext):
    await state.update_data(car=message.text)
    await message.answer("💳 Реквизиты:")
    await state.set_state(DriverVipRegistration.waiting_for_payment_info)

@dp.message(DriverVipRegistration.waiting_for_payment_info)
async def vip_pay(message: types.Message, state: FSMContext):
    await state.update_data(pay=message.text)
    await message.answer("🔑 Код-пароль:")
    await state.set_state(DriverVipRegistration.waiting_for_code)

@dp.message(DriverVipRegistration.waiting_for_code)
async def vip_fin(message: types.Message, state: FSMContext):
    code = message.text.upper().strip()
    data = await state.get_data()
    role = data.get('role', 'driver')
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, role, commission, balance, rating_sum, rating_count) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, 10, 0, 0, 0)", 
                     (message.from_user.id, message.from_user.username, data['fio'], data['car'], data['pay'], code, role))
        conn.commit()
        await message.answer("🚀 <b>ВЫ ПРИНЯТЫ!</b> Жмите /cab")
        await notify_admins(f"⭐ <b>VIP ({role}):</b> {data['fio']}")
    except: await message.answer("❌ Код занят.")
    finally: conn.close()
    await state.clear()

@dp.message(Command("driver", "drive"))
async def reg_start(message: types.Message, state: FSMContext):
    await state.clear()
    info = get_driver_info(message.from_user.id)
    if info:
        await message.answer("Уже есть. /cab" if info[4]=='active' else "Жди одобрения.")
        return
    await message.answer("📝 ФИО:")
    await state.set_state(DriverRegistration.waiting_for_fio)

@dp.message(DriverRegistration.waiting_for_fio)
async def reg_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await message.answer("🚘 Авто:")
    await state.set_state(DriverRegistration.waiting_for_car)

@dp.message(DriverRegistration.waiting_for_car)
async def reg_car(message: types.Message, state: FSMContext):
    await state.update_data(car=message.text)
    await message.answer("💳 Реквизиты:")
    await state.set_state(DriverRegistration.waiting_for_payment_info)

@dp.message(DriverRegistration.waiting_for_payment_info)
async def reg_pay(message: types.Message, state: FSMContext):
    await state.update_data(pay=message.text)
    await message.answer("🔑 Код:")
    await state.set_state(DriverRegistration.waiting_for_code)

@dp.message(DriverRegistration.waiting_for_code)
async def reg_fin(message: types.Message, state: FSMContext):
    code = message.text.upper().strip()
    data = await state.get_data()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, commission, role, balance, rating_sum, rating_count) VALUES (?, ?, ?, ?, ?, ?, 'pending', 10, 'driver', 0, 0, 0)", 
                     (message.from_user.id, message.from_user.username, data['fio'], data['car'], data['pay'], code))
        conn.commit()
        await message.answer("📝 Заявка отправлена.")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ОДОБРИТЬ", callback_data=f"adm_app_{message.from_user.id}")]])
        await notify_admins(f"🚨 <b>НОВЫЙ:</b> {data['fio']}", kb)
    except Exception as e:
        logging.error(e)
        await message.answer("❌ Код занят.")
    finally: conn.close()
    await state.clear()

# ==========================================
# 👑 АДМИНКА
# ==========================================
@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id): return await message.answer("⛔ Доступ запрещен.")
    conn = sqlite3.connect(DB_PATH); drs = conn.execute("SELECT user_id, username, balance, role, status, fio, commission FROM drivers").fetchall(); conn.close()
    txt = "👑 <b>АДМИНКА</b>\n"
    for d in drs: txt += f"• {d[5]} | {d[2]}₽ | /edit_{d[0]}\n"
    await message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 РАССЫЛКА", callback_data="admin_broadcast")]]))

@dp.callback_query(F.data.startswith("adm_app_"))
async def admin_approve(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    did = int(callback.data.split("_")[2])
    update_driver_field(did, "status", "active")
    await callback.message.edit_text("✅ Одобрено.")
    try: await bot.send_message(did, "🎉 Принят! /cab")
    except: pass

@dp.message(F.text.startswith("/edit_"))
async def edit_driver_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    did = int(message.text.split("_")[1])
    await state.update_data(target_did=did)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Счет", callback_data=f"adm_bill_{did}")]])
    await message.answer("Меню водителя:", reply_markup=kb)

# БИЛЛИНГ (ВЫСТАВЛЕНИЕ СЧЕТА)
@dp.callback_query(F.data.startswith("adm_bill_"))
async def bill_start(callback: types.CallbackQuery, state: FSMContext):
    did = int(callback.data.split("_")[2])
    await state.update_data(target_did=did)
    await callback.message.answer("Введите сумму или текст счета:")
    await state.set_state(AdminBilling.waiting_for_custom_req)

@dp.message(AdminBilling.waiting_for_custom_req)
async def bill_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    did = data['target_did']
    try: await bot.send_message(did, f"⚠️ <b>СЧЕТ ОТ БОССА:</b>\n{message.text}")
    except: pass
    await message.answer("✅ Отправлено.")
    await state.clear()

# РАССЫЛКА
@dp.callback_query(F.data == "admin_broadcast")
async def broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Текст рассылки:")
    await state.set_state(AdminBroadcast.waiting_for_text)
    await callback.answer()

@dp.message(AdminBroadcast.waiting_for_text)
async def broadcast_send(message: types.Message, state: FSMContext):
    drivers = get_active_drivers()
    count = 0
    for did in drivers:
        if await safe_send_message(did, f"📢 <b>ОБЪЯВЛЕНИЕ:</b>\n{message.text}"): count += 1
    await message.answer(f"✅ Отправлено {count} водителям.")
    await state.clear()

# ==========================================
# 🔐 ВВОД КЛЮЧА
# ==========================================
@dp.message(F.text == "🔐 Ввести КЛЮЧ услуги")
async def key_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Код:")
    await state.set_state(UnlockMenu.waiting_for_key)

@dp.message(UnlockMenu.waiting_for_key)
async def key_proc(message: types.Message, state: FSMContext):
    drv = get_driver_by_code(message.text.strip().upper())
    if drv:
        set_linked_driver(message.from_user.id, drv[0])
        await message.answer(f"🔓 <b>ОК!</b>\n👤 {drv[3]}\n🚘 {drv[2]}", reply_markup=main_kb)
        await state.clear()
    else: await message.answer("❌ Нет.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
