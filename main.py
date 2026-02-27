import asyncio
import logging
import os
import sqlite3
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties

# ==========================================
# ⚙️ НАСТРОЙКИ СИСТЕМЫ
# ==========================================
logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("API_TOKEN")
OWNER_ID = os.getenv("DRIVER_ID") 

# 🔑 СЕКРЕТНЫЕ КЛЮЧИ (МОЖНО МЕНЯТЬ ТУТ)
KEY_VIP_DRIVER = "CRAZY_START"   # Пароль для водителя
KEY_VIP_ADMIN = "BIG_BOSS_777"   # Пароль для админа

LAWYER_LINK = "https://t.me/Ai_advokatrobot"

if not API_TOKEN or not OWNER_ID:
    logging.error("⛔ КРИТИЧЕСКАЯ ОШИБКА: Токены не найдены!")
    exit()

OWNER_ID = int(OWNER_ID)
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Глобальные переменные
active_orders = {} 
client_driver_link = {} 

# ==========================================
# 🗄️ БАЗА ДАННЫХ
# ==========================================
DB_PATH = "/data/taxi_db.sqlite" if os.path.exists("/data") else "taxi_db.sqlite"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица водителей
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
            rating_count INTEGER DEFAULT 0
        )
    """)
    cursor.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY)")
    
    # История заказов
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
    
    # Авто-регистрация ВЛАДЕЛЬЦА
    cursor.execute("SELECT 1 FROM drivers WHERE user_id = ?", (OWNER_ID,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, role) VALUES (?, ?, ?, ?, ?, ?, 'active', 'owner')",
            (OWNER_ID, "BOSS_NETWORK", "Владелец Сети", "⚫ ЧЕРНАЯ ВОЛГА (БОСС)", "Сбер: +70000000000", "BOSS")
        )
    else:
        cursor.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (OWNER_ID,))
        
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 🛠 ФУНКЦИИ
# ==========================================

def get_all_admins():
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT user_id FROM drivers WHERE role IN ('owner', 'admin') AND status='active'").fetchall()
    conn.close()
    return [r[0] for r in res]

def is_admin(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT 1 FROM drivers WHERE user_id=? AND role IN ('owner', 'admin') AND status='active'", (user_id,)).fetchone()
    conn.close()
    return bool(res) or user_id == OWNER_ID

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
    # 0:username, 1:car, 2:payment, 3:balance, 4:status, 5:code, 6:role, 7:fio, 8:r_sum, 9:r_count
    res = conn.execute("SELECT username, car_info, payment_info, balance, status, access_code, role, fio, rating_sum, rating_count FROM drivers WHERE user_id=?", (user_id,)).fetchone()
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
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return order_id

def update_order_rating(order_id, rating, driver_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE drivers SET rating_sum = rating_sum + ?, rating_count = rating_count + 1 WHERE user_id = ?", (rating, driver_id))
    conn.execute("UPDATE order_history SET rating = ? WHERE id = ?", (rating, order_id))
    conn.commit()
    conn.close()

def add_commission(driver_id, amount):
    if is_admin(driver_id): return 
    commission = int(amount * 0.10)
    if commission <= 0: return 
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE drivers SET balance = balance + ? WHERE user_id=?", (commission, driver_id))
    conn.commit()
    conn.close()

def is_client_accepted(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT 1 FROM clients WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return bool(res)

async def notify_admins(text, markup=None):
    admins = get_all_admins()
    for admin_id in admins:
        try: await bot.send_message(admin_id, text, reply_markup=markup)
        except: pass

# ==========================================
# 📜 МЕНЮ УСЛУГ
# ==========================================
CRAZY_SERVICES = {
    # LEVEL 1
    "candy": {"cat": 1, "price": 0, "name": "🍬 Конфетка", "desc": "Водитель с максимально серьезным лицом вручает вам элитную барбариску. Это знак глубочайшего уважения."},
    "nose": {"cat": 1, "price": 300, "name": "👃 Палец в носу", "desc": "Водитель едет с пальцем в носу всю поездку. Вы платите за его моральные страдания и ваш смех."},
    "butler": {"cat": 1, "price": 200, "name": "🤵 Дворецкий", "desc": "Водитель выходит, открывает вам дверь, кланяется в пояс и называет вас 'Сир' или 'Миледи'."},
    "joke": {"cat": 1, "price": 50, "name": "🤡 Тупой анекдот", "desc": "Анекдот категории 'Б'. Смеяться не обязательно, но желательно, чтобы не обидеть водителя."},
    "silence": {"cat": 1, "price": 150, "name": "🤐 Полная тишина", "desc": "Водитель выключает музыку и молчит как рыба. Даже если вы спросите дорогу — он ответит жестами."},
    
    # LEVEL 2
    "granny": {"cat": 2, "price": 800, "name": "👵 Бабушка", "desc": "Ролевая игра. Всю дорогу буду бубнить: 'Куда прешь, наркоман?', 'Шапку надень!', 'Вот в наше время...'."},
    "gopnik": {"cat": 2, "price": 500, "name": "🍺 Четкий пацанчик", "desc": "Едем под пацанский рэп, водитель сидит на корточках (шутка), называет вас 'Братишка' и решает вопросики."},
    "guide": {"cat": 2, "price": 600, "name": "🗣 Ужасный гид", "desc": "Водитель проводит экскурсию, выдумывая факты на ходу. 'Вот этот ларек построил Иван Грозный'."},
    "psych": {"cat": 2, "price": 1000, "name": "🧠 Психолог", "desc": "Вы жалуетесь на жизнь, бывших и начальника. Водитель кивает, говорит 'Угу' и дает советы."},
    
    # LEVEL 3
    "spy": {"cat": 3, "price": 2000, "name": "🕵️‍♂️ Шпион 007", "desc": "Черные очки, паранойя. Водитель проверяет 'хвост', говорит по рации кодами ('Орел в гнезде')."},
    "karaoke": {"cat": 3, "price": 5000, "name": "🎤 Адское Караоке", "desc": "Врубаем 'Рюмку водки' на полную! Водитель орет песни вместе с вами. Фальшиво, громко, душевно."},
    "dance": {"cat": 3, "price": 15000, "name": "💃 Танцы на капоте", "desc": "На красном свете водитель выбегает и танцует макарену перед капотом. Прохожие снимают, вам стыдно."},
    
    # LEVEL 4
    "kidnap": {"cat": 4, "price": 30000, "name": "🎭 Похищение", "desc": "Вас (понарошку) грузят в багажник, надевают мешок на голову и везут в лес... пить элитный чай."},
    "tarzan": {"cat": 4, "price": 50000, "name": "🦍 Тарзан-Шоу", "desc": "Водитель бьет себя в грудь, рычит на прохожих, называет другие машины 'железными буйволами'."},
    "burn": {"cat": 4, "price": 1000000, "name": "🔥 Сжечь машину", "desc": "Едем на пустырь. Вы платите лям, я даю канистру. Гори оно всё синим пламенем. (Машина реальная)."},
    
    # LEVEL 5: ДЛЯ ДАМ
    "eyes": {"cat": 5, "price": 0, "name": "👁️ Глаз-алмаз", "desc": "Водитель сделает изысканный комплимент вашим глазам. Сравнит их с звездами или фарами ксенона."},
    "smile": {"cat": 5, "price": 0, "name": "😁 Улыбка", "desc": "Водитель скажет, что ваша улыбка освещает этот грязный салон лучше, чем аварийка в ночи."},
    "style": {"cat": 5, "price": 0, "name": "👠 Икона стиля", "desc": "Восхищение вашим образом. Водитель спросит, не едете ли вы с показа мод в Милане."},
    "improv": {"cat": 5, "price": 0, "name": "✨ Импровизация", "desc": "Водитель сам найдет, что в вас похвалить. Рискованно, но приятно. Полный фристайл."},
    "propose": {"cat": 5, "price": 1000, "name": "💍 Предложение", "desc": "Вы делаете предложение руки, сердца или ипотеки водителю. Шанс 50/50. ⚠️ ПРИ ОТКАЗЕ ДЕНЬГИ НЕ ВОЗВРАЩАЮТСЯ!"}
}

CATEGORIES = {1: "🟢 ЛАЙТ (До 300₽)", 2: "🟡 МЕДИУМ (Ролевые)", 3: "🔴 ХАРД (Треш)", 4: "☠️ VIP БЕЗУМИЕ", 5: "🌹 ДЛЯ ДАМ"}

# ==========================================
# 🛠 FSM STATES
# ==========================================
class OrderRide(StatesGroup):
    waiting_for_from = State()
    waiting_for_to = State()
    waiting_for_phone = State() 
    waiting_for_price = State()

class CustomIdea(StatesGroup):
    waiting_for_idea = State()
    waiting_for_price = State()

class DriverCounterOffer(StatesGroup):
    waiting_for_offer = State()

class AddStop(StatesGroup):
    waiting_for_address = State()
    waiting_for_price = State()

class DriverRegistration(StatesGroup):
    waiting_for_fio = State()
    waiting_for_car = State()
    waiting_for_payment_info = State()
    waiting_for_code = State()

class DriverVipRegistration(StatesGroup):
    waiting_for_fio = State()
    waiting_for_car = State()
    waiting_for_payment_info = State()
    waiting_for_code = State()
    waiting_for_role = State()

class DriverChangeCode(StatesGroup):
    waiting_for_new_code = State()

class UnlockMenu(StatesGroup):
    waiting_for_key = State()

class AdminEditDriver(StatesGroup):
    waiting_for_new_value = State()

# ==========================================
# ⌨️ UI
# ==========================================
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚕 Заказать такси (Поиск)")],
        [KeyboardButton(text="🔐 Ввести КЛЮЧ услуги")],
        [KeyboardButton(text="📜 CRAZY МЕНЮ (Категории)")],
        [KeyboardButton(text="💡 Свой вариант (Идея)")],
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
async def cmd_start(message: types.Message):
    await message.answer(
        "⚠️ <b>CRAZY TAXI: ЗОНА ПОВЫШЕННОГО РИСКА</b>\n\n"
        "Мы не возим скучных людей. Мы делаем шоу.\n\n"
        "<b>Правила клуба:</b>\n"
        "1. Что происходит в такси — остается в такси.\n"
        "2. Водитель — художник, салон — его холст.\n"
        "3. Наш юрист уже выиграл суд у здравого смысла.\n\n"
        "Готовы рискнуть?", reply_markup=tos_kb
    )

@dp.callback_query(F.data == "accept_tos")
async def tos_accepted(callback: types.CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (callback.from_user.id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("🔥 <b>КОНТРАКТ ПОДПИСАН!</b>")
    await callback.message.answer("Добро пожаловать в семью. Выбирай ниже 👇", reply_markup=main_kb)

@dp.callback_query(F.data == "decline_tos")
async def tos_declined(callback: types.CallbackQuery):
    await callback.message.edit_text("🚶‍♂️ Выход там.")

async def check_tos(message: types.Message) -> bool:
    if not is_client_accepted(message.from_user.id):
        await message.answer("🛑 Сначала нажми /start.")
        return False
    return True

@dp.message(F.text == "⚖️ Вызвать адвоката")
async def lawyer_menu(message: types.Message):
    await message.answer(
        "⚖️ <b>ЮРИДИЧЕСКИЙ ОТДЕЛ</b>\n\n"
        "Наш партнер — лучший цифровой юрист:\n"
        "<i>Жми кнопку, чтобы перейти в приемную.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚨 ПЕРЕЙТИ К АДВОКАТУ", url=LAWYER_LINK)]])
    )

# ==========================================
# 🚀 МОНИТОРИНГ
# ==========================================
async def update_admins_monitor(client_id, taking_driver_id):
    order = active_orders.get(client_id)
    if not order or 'admin_msg_ids' not in order: return
    
    drv_info = get_driver_info(taking_driver_id)
    drv_name = f"@{drv_info[0]}" if drv_info[0] else "Unknown"
    fio = drv_info[7] if drv_info[7] else "Без ФИО"
    
    taker_role = "👑 БОСС" if taking_driver_id == OWNER_ID else ("👮‍♂️ АДМИН" if is_admin(taking_driver_id) else "🚕 ВОДИТЕЛЬ")
    
    text = f"🚫 <b>ЗАКАЗ ЗАБРАЛ: {taker_role} {drv_name}</b>\nФИО: {fio}\nАвто: {drv_info[1]}\n\n{order.get('broadcasting_text','')}"
    
    for admin_id, msg_id in order['admin_msg_ids'].items():
        try: await bot.edit_message_text(chat_id=admin_id, message_id=msg_id, text=text, reply_markup=None)
        except: pass

async def broadcast_order_to_drivers(client_id, order_text, driver_kb, admin_kb):
    admins = get_all_admins()
    admin_msg_map = {}
    admin_text = f"🚨 <b>МОНИТОРИНГ (ВСЕ АДМИНЫ)</b>\n\n{order_text}"
    
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
    
    if not simple_drivers and not admins:
        await search_msg.edit_text("😔 <b>Нет свободных машин.</b> Администрация уведомлена.")
        return

    tasks = []
    for d_id in simple_drivers:
        tasks.append(bot.send_message(d_id, f"⚡ <b>ЗАКАЗ!</b>\n{order_text}", reply_markup=driver_kb))
    
    if tasks: await asyncio.gather(*tasks, return_exceptions=True)
    await search_msg.edit_text("⏳ <b>Запрос отправлен всем пилотам!</b> Ждем реакции...")

# ==========================================
# 🚕 ТАКСИ
# ==========================================
@dp.message(F.text == "🚕 Заказать такси (Поиск)")
async def taxi_start(message: types.Message, state: FSMContext):
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
    await message.answer("💰 <b>Ваша цена за поездку (в рублях)?</b>")
    await state.set_state(OrderRide.waiting_for_price)

@dp.message(OrderRide.waiting_for_price)
async def taxi_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cid = message.from_user.id
    active_orders[cid] = {"type": "taxi", "status": "pending", "price": message.text, "from": data['fr'], "to": data['to'], "phone": data['ph'], "driver_offers": {}}
    await message.answer("✅ <b>Заявка сформирована! Ищем машину...</b>", reply_markup=main_kb)
    await state.clear()
    
    text = f"🚕 <b>НОВЫЙ ЗАКАЗ ТАКСИ</b>\n\n📍 Откуда: <b>{data['fr']}</b>\n🏁 Куда: <b>{data['to']}</b>\n💰 Клиент предлагает: <b>{message.text}</b>"
    dkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ЗАБРАТЬ", callback_data=f"take_taxi_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"cnt_taxi_{cid}")]])
    akb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ АДМИН ПЕРЕХВАТ", callback_data=f"adm_take_taxi_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"cnt_taxi_{cid}")]])
    await broadcast_order_to_drivers(cid, text, dkb, akb)

@dp.callback_query(F.data.startswith("take_taxi_") | F.data.startswith("adm_take_taxi_"))
async def take_taxi(callback: types.CallbackQuery):
    cid = int(callback.data.split("_")[-1])
    did = callback.from_user.id
    order = active_orders.get(cid)
    
    if not order or order["status"] != "pending":
        await callback.answer("Упс! Заказ уже забрали.", show_alert=True)
        return
        
    order["status"] = "accepted"
    order["driver_id"] = did
    client_driver_link[cid] = did
    await update_admins_monitor(cid, did)
    
    info = get_driver_info(did)
    # Кнопка для водителя
    drv_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ ПОЕЗДКУ", callback_data=f"ask_finish_{cid}")]])
    await callback.message.edit_text(f"✅ <b>Заказ принят!</b>\n📞 Телефон клиента: <b>{order['phone']}</b>\n💰 Цена: <b>{order['price']}</b>", reply_markup=drv_kb)
    
    # Кнопка для клиента (добавить точку)
    cli_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ ДОБАВИТЬ ОСТАНОВКУ", callback_data="add_stop")]])
    await bot.send_message(
        cid, 
        f"🚕 <b>ВОДИТЕЛЬ ВЫЕХАЛ!</b>\n\n👤 <b>{info[7]}</b>\n🚘 {info[1]}\n📞 {order['phone']}\n💰 {order['price']}₽\n\n🔐 <b>КОД CRAZY-МЕНЮ:</b> <code>{info[5]}</code>",
        reply_markup=cli_kb
    )

# --- ДОБАВЛЕНИЕ ТОЧКИ ---
@dp.callback_query(F.data == "add_stop")
async def add_stop_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📍 <b>Куда нужно заехать?</b> (Введите адрес):")
    await state.set_state(AddStop.waiting_for_address)
    await callback.answer()

@dp.message(AddStop.waiting_for_address)
async def add_stop_price(message: types.Message, state: FSMContext):
    await state.update_data(addr=message.text)
    await message.answer("💰 <b>Сколько вы готовы доплатить?</b> (в рублях):")
    await state.set_state(AddStop.waiting_for_price)

@dp.message(AddStop.waiting_for_price)
async def add_stop_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cid = message.from_user.id
    order = active_orders.get(cid)
    
    if not order or 'driver_id' not in order:
        await message.answer("❌ Ошибка: поездка не найдена.")
        await state.clear()
        return
        
    did = order['driver_id']
    extra_price = message.text
    address = data['addr']
    await state.clear()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ СОГЛАСЕН", callback_data=f"stop_ok_{cid}_{extra_price}")],
        [InlineKeyboardButton(text="❌ ОТКАЗ", callback_data=f"stop_no_{cid}")]
    ])
    await bot.send_message(did, f"🔔 <b>КЛИЕНТ ХОЧЕТ ЗАЕХАТЬ!</b>\n\n📍 Адрес: <b>{address}</b>\n💰 Доплата: <b>+{extra_price}₽</b>\n\nБерем?", reply_markup=kb)
    await message.answer("⏳ Запрос отправлен водителю...")

@dp.callback_query(F.data.startswith("stop_ok_"))
async def stop_ok(c: types.CallbackQuery):
    parts = c.data.split("_")
    cid = int(parts[2])
    extra = int(parts[3])
    
    order = active_orders.get(cid)
    if order:
        old_price = extract_price(order['price'])
        new_price = old_price + extra
        order['price'] = str(new_price)
        await bot.send_message(cid, f"✅ <b>Водитель согласился!</b>\nНовая цена поездки: <b>{new_price}₽</b>")
        drv_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ ПОЕЗДКУ", callback_data=f"ask_finish_{cid}")]])
        await c.message.edit_text(f"✅ <b>Точка добавлена!</b>\n💰 Итоговая цена: <b>{new_price}₽</b>", reply_markup=drv_kb)

@dp.callback_query(F.data.startswith("stop_no_"))
async def stop_no(c: types.CallbackQuery):
    cid = int(c.data.split("_")[2])
    await bot.send_message(cid, "❌ <b>Водитель отказался добавлять остановку.</b>")
    await c.message.edit_text("❌ Вы отказали в остановке.")

# --- ЗАВЕРШЕНИЕ ПОЕЗДКИ И РЕЙТИНГ ---
@dp.callback_query(F.data.startswith("ask_finish_"))
async def ask_finish(c: types.CallbackQuery):
    cid = int(c.data.split("_")[2])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 1", callback_data=f"rate_{cid}_1"), InlineKeyboardButton(text="⭐ 2", callback_data=f"rate_{cid}_2"), InlineKeyboardButton(text="⭐ 3", callback_data=f"rate_{cid}_3")],
        [InlineKeyboardButton(text="⭐ 4", callback_data=f"rate_{cid}_4"), InlineKeyboardButton(text="⭐ 5", callback_data=f"rate_{cid}_5")],
        [InlineKeyboardButton(text="⏩ ПРОПУСТИТЬ", callback_data=f"rate_{cid}_0")]
    ])
    await bot.send_message(cid, "🏁 <b>Поездка завершена!</b>\nПожалуйста, оцените водителя:", reply_markup=kb)
    await c.message.edit_text("✅ <b>Поездка закрыта.</b> Ждем оценку клиента...")

@dp.callback_query(F.data.startswith("rate_"))
async def rate_ride(c: types.CallbackQuery):
    parts = c.data.split("_")
    cid = int(parts[1])
    rating = int(parts[2])
    
    order = active_orders.get(cid)
    if not order: 
        await c.message.delete()
        return

    did = order['driver_id']
    pr = extract_price(order['price'])
    srv_name = order.get('service', {}).get('name', 'Такси')
    
    last_id = log_order(did, srv_name, pr)
    if rating > 0:
        update_order_rating(last_id, rating, did)
    
    add_commission(did, pr)
    await c.message.edit_text("🙏 <b>Спасибо за оценку!</b>")
    await bot.send_message(did, f"🎉 <b>Клиент поставил вам {rating}⭐!</b>\nБаланс обновлен.")
    if cid in active_orders: del active_orders[cid]

# ==========================================
# 📜 CRAZY МЕНЮ
# ==========================================
@dp.message(F.text == "📜 CRAZY МЕНЮ (Категории)")
async def show_cats(message: types.Message):
    if not await check_tos(message): return
    if message.from_user.id not in client_driver_link:
        await message.answer("🔒 <b>НЕТ ДОСТУПА!</b>\nСядьте в машину и введите ключ.", reply_markup=main_kb)
        return
    btns = [[InlineKeyboardButton(text=n, callback_data=f"cat_{i}")] for i, n in CATEGORIES.items()]
    await message.answer("🔥 <b>КАТЕГОРИИ:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("cat_"))
async def open_cat(c: types.CallbackQuery):
    cat_id = int(c.data.split("_")[1])
    btns = []
    for k, v in CRAZY_SERVICES.items():
        if v["cat"] == cat_id:
            btns.append([InlineKeyboardButton(text=f"{v['name']} — {v['price']}₽", callback_data=f"csel_{k}")])
    btns.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_cats")])
    await c.message.edit_text(f"📂 <b>{CATEGORIES[cat_id]}</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "back_cats")
async def back_cats(c: types.CallbackQuery):
    btns = [[InlineKeyboardButton(text=n, callback_data=f"cat_{i}")] for i, n in CATEGORIES.items()]
    await c.message.edit_text("🔥 <b>УРОВНИ:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("csel_"))
async def sel_srv(c: types.CallbackQuery):
    key = c.data.split("_")[1]
    srv = CRAZY_SERVICES[key]
    text = f"🎭 <b>{srv['name']}</b>\n💰 <b>{srv['price']}₽</b>\n\n📝 <i>{srv['desc']}</i>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ЗАКАЗАТЬ", callback_data=f"do_order_{key}")], [InlineKeyboardButton(text="🔙 Назад", callback_data=f"cat_{srv['cat']}")]])
    await c.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("do_order_"))
async def do_order(c: types.CallbackQuery):
    key = c.data.split("_")[-1] # FIX
    srv = CRAZY_SERVICES[key]
    cid, did = c.from_user.id, client_driver_link.get(c.from_user.id)
    
    active_orders[cid] = {"type": "crazy", "status": "direct", "price": str(srv["price"]), "driver_id": did, "service": srv}
    await c.message.edit_text("⏳ <b>Отправляем заказ...</b>")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"drv_acc_{cid}")]])
    await bot.send_message(did, f"🔔 <b>ЗАКАЗ</b>\n🎭 {srv['name']}\n💰 {srv['price']}₽\n📝 {srv['desc']}", reply_markup=kb)

@dp.callback_query(F.data.startswith("drv_acc_"))
async def drv_acc_crazy(c: types.CallbackQuery):
    cid = int(c.data.split("_")[2])
    order = active_orders.get(cid)
    if not order: return
    info = get_driver_info(c.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ВЫПОЛНЕНО / ОПЛАТИЛ", callback_data=f"ask_finish_{cid}")]])
    await bot.send_message(cid, f"✅ <b>Водитель принял!</b>\n💳 Перевод: <code>{info[2]}</code>\nНажмите кнопку, когда услуга будет оказана.", reply_markup=kb)
    await c.message.edit_text("✅ В работе.")

# ==========================================
# 🪪 КАБИНЕТ
# ==========================================
@dp.message(Command("cab"))
async def cab(m: types.Message):
    info = get_driver_info(m.from_user.id)
    if not info:
        await m.answer("❌ Нет регистрации. /drive")
        return
        
    conn = sqlite3.connect(DB_PATH)
    history = conn.execute("SELECT service_name, price, rating, date FROM order_history WHERE driver_id=? ORDER BY id DESC LIMIT 5", (m.from_user.id,)).fetchall()
    conn.close()
    
    active_txt = "Нет активных"
    for o in active_orders.values():
        if o.get('driver_id') == m.from_user.id and o['status'] == 'accepted':
            active_txt = f"🚖 {o.get('service', {}).get('name', 'Такси')} | {o['price']}₽"
    
    rating_val = round(info[8] / info[9], 1) if info[9] > 0 else 0.0
    
    hist_txt = ""
    for h in history:
        r_star = "⭐" * h[2] if h[2] else "-"
        hist_txt += f"▪ {h[0]} ({h[1]}₽) [{r_star}]\n"
        
    role_map = {'owner':"👑 БОСС", 'admin':"👮‍♂️ АДМИН", 'driver':"🚕 ВОДИТЕЛЬ"}
    
    text = (
        f"🪪 <b>КАБИНЕТ ПИЛОТА</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔰 Роль: <b>{role_map.get(info[6])}</b>\n"
        f"👤 {info[7]} (@{info[0]})\n"
        f"⭐ Рейтинг: <b>{rating_val}</b> ({info[9]} оценок)\n"
        f"💰 Баланс: <b>{info[3]}₽</b>\n"
        f"🔑 Код: <code>{info[5]}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔥 <b>АКТИВНЫЙ ЗАКАЗ:</b>\n{active_txt}\n\n"
        f"📜 <b>ИСТОРИЯ (Последние 5):</b>\n{hist_txt}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Оплатить долг", callback_data="cab_pay")]])
    await m.answer(text, reply_markup=kb)

# ==========================================
# 🔥 VIP РЕГИСТРАЦИЯ
# ==========================================
@dp.message(Command("vip"))
async def vip_reg(m: types.Message, s: FSMContext):
    try:
        key = m.text.split()[1]
        role = "driver"
        
        if key == KEY_VIP_ADMIN:
            role = "admin"
            await m.answer("🔑 <b>КЛЮЧ АДМИНА ПРИНЯТ!</b>\n\nВведите ФИО:")
        elif key == KEY_VIP_DRIVER:
            await m.answer("🔑 <b>КЛЮЧ ВОДИТЕЛЯ ПРИНЯТ!</b>\n\nВведите ФИО:")
        else:
            await m.answer("❌ Неверный ключ.")
            return
            
        await s.update_data(role=role)
        await s.set_state(DriverVipRegistration.waiting_for_fio)
    except: await m.answer("Формат: /vip КОД")

@dp.message(DriverVipRegistration.waiting_for_fio)
async def vip_fio(m: types.Message, s: FSMContext):
    await s.update_data(fio=m.text)
    await m.answer("🚘 Авто (Марка, Номер):")
    await s.set_state(DriverVipRegistration.waiting_for_car)

@dp.message(DriverVipRegistration.waiting_for_car)
async def vip_car(m: types.Message, s: FSMContext):
    await s.update_data(car=m.text)
    await m.answer("💳 Реквизиты:")
    await s.set_state(DriverVipRegistration.waiting_for_payment_info)

@dp.message(DriverVipRegistration.waiting_for_payment_info)
async def vip_pay(m: types.Message, s: FSMContext):
    await s.update_data(pay=m.text)
    await m.answer("🔑 Код-пароль:")
    await s.set_state(DriverVipRegistration.waiting_for_code)

@dp.message(DriverVipRegistration.waiting_for_code)
async def vip_fin(m: types.Message, s: FSMContext):
    code = m.text.upper().strip()
    data = await s.get_data()
    role = data['role']
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, role) VALUES (?, ?, ?, ?, ?, ?, 'active', ?)", 
                     (m.from_user.id, m.from_user.username, data['fio'], data['car'], data['pay'], code, role))
        conn.commit()
        await m.answer(f"🚀 <b>ВЫ ПРИНЯТЫ КАК {role.upper()}!</b>\nСтатус: ACTIVE. Жмите /cab")
        await notify_admins(f"⭐ <b>VIP РЕГИСТРАЦИЯ ({role.upper()})</b>\n@{m.from_user.username}")
    except: await m.answer("❌ Код занят.")
    finally: conn.close()
    await s.clear()

# ==========================================
# 🛑 ОБЫЧНАЯ РЕГИСТРАЦИЯ
# ==========================================
@dp.message(Command("driver", "drive"))
async def reg_start(m: types.Message, s: FSMContext):
    info = get_driver_info(m.from_user.id)
    if info:
        await m.answer("Уже есть. /cab" if info[4]=='active' else "Жди одобрения.")
        return
    await m.answer("📝 ФИО:")
    await s.set_state(DriverRegistration.waiting_for_fio)

@dp.message(DriverRegistration.waiting_for_fio)
async def reg_fio(m: types.Message, s: FSMContext):
    await s.update_data(fio=m.text)
    await m.answer("🚘 Авто:")
    await s.set_state(DriverRegistration.waiting_for_car)

@dp.message(DriverRegistration.waiting_for_car)
async def reg_car(m: types.Message, s: FSMContext):
    await s.update_data(car=m.text)
    await m.answer("💳 Реквизиты:")
    await s.set_state(DriverRegistration.waiting_for_payment_info)

@dp.message(DriverRegistration.waiting_for_payment_info)
async def reg_pay(m: types.Message, s: FSMContext):
    await s.update_data(pay=m.text)
    await m.answer("🔑 Код:")
    await s.set_state(DriverRegistration.waiting_for_code)

@dp.message(DriverRegistration.waiting_for_code)
async def reg_fin(m: types.Message, s: FSMContext):
    code = m.text.upper().strip()
    data = await s.get_data()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')", 
                     (m.from_user.id, m.from_user.username, data['fio'], data['car'], data['pay'], code))
        conn.commit()
        await m.answer("📝 Заявка отправлена.")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ОДОБРИТЬ", callback_data=f"adm_app_{m.from_user.id}")]])
        await notify_admins(f"🚨 <b>НОВЫЙ ВОДИТЕЛЬ</b>\n{data['fio']}", kb)
    except: await m.answer("❌ Код занят.")
    finally: conn.close()
    await s.clear()

# ==========================================
# 🚕 ТОРГ
# ==========================================
@dp.callback_query(F.data.startswith("cnt_"))
async def cnt_start(c: types.CallbackQuery, s: FSMContext):
    parts = c.data.split("_")
    await s.update_data(cid=int(parts[2]), type=parts[1])
    await c.message.answer("Твоя цена:")
    await s.set_state(DriverCounterOffer.waiting_for_offer)
    await c.answer()

@dp.message(DriverCounterOffer.waiting_for_offer)
async def cnt_send(m: types.Message, s: FSMContext):
    data = await s.get_data()
    cid, did = data['cid'], m.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ДА", callback_data=f"ok_off_{data['type']}_{cid}_{did}"), InlineKeyboardButton(text="❌ НЕТ", callback_data=f"no_off_{cid}")]])
    await bot.send_message(cid, f"⚡ <b>Водитель предлагает:</b> {m.text}", reply_markup=kb)
    await m.answer("Отправлено.")
    await s.clear()

@dp.callback_query(F.data.startswith("ok_off_"))
async def ok_off(c: types.CallbackQuery):
    parts = c.data.split("_")
    cid, did = int(parts[3]), int(parts[4])
    active_orders[cid]['driver_id'] = did
    active_orders[cid]['status'] = 'accepted'
    client_driver_link[cid] = did
    
    info = get_driver_info(did)
    drv_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ", callback_data=f"ask_finish_{cid}")]])
    await bot.send_message(did, f"✅ Клиент согласен!\n📞 {active_orders[cid]['phone']}", reply_markup=drv_kb)
    
    cli_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ ДОБАВИТЬ ТОЧКУ", callback_data="add_stop")]])
    await c.message.edit_text(f"🚕 <b>Едет: {info[7]}</b>\n🔐 {info[5]}", reply_markup=cli_kb)

@dp.message(F.text == "💡 Свой вариант (Идея)")
async def idea_h(m: types.Message, s: FSMContext):
    await m.answer("Идея:")
    await s.set_state(CustomIdea.waiting_for_idea)

@dp.message(CustomIdea.waiting_for_idea)
async def idea_p(m: types.Message, s: FSMContext):
    await s.update_data(idea=m.text)
    await m.answer("Бюджет:")
    await s.set_state(CustomIdea.waiting_for_price)

@dp.message(CustomIdea.waiting_for_price)
async def idea_s(m: types.Message, s: FSMContext):
    data = await s.get_data()
    cid = m.from_user.id
    active_orders[cid] = {"type": "crazy", "status": "pending", "price": m.text, "service": {"name": "Идея", "desc": data['idea']}, "driver_offers": {}}
    await m.answer("✅ Отправлено!", reply_markup=main_kb)
    await s.clear()
    dkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ЗАБРАТЬ", callback_data=f"take_crazy_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"cnt_crazy_{cid}")]])
    await broadcast_order_to_drivers(cid, f"💡 <b>ИДЕЯ:</b> {data['idea']}\n💰 {m.text}", dkb, dkb)

# ADMIN
@dp.callback_query(F.data.startswith("adm_app_"))
async def admin_approve(c: types.CallbackQuery):
    if not is_admin(c.from_user.id): return
    did = int(c.data.split("_")[2])
    update_driver_field(did, "status", "active")
    await c.message.edit_text("✅ Одобрено.")
    try: await bot.send_message(did, "🎉 Принят! /cab")
    except: pass

@dp.callback_query(F.data == "cab_pay")
async def cab_pay(c: types.CallbackQuery):
    info = get_driver_info(c.from_user.id)
    boss = get_driver_info(OWNER_ID)
    await c.message.answer(f"💸 Долг: <b>{info[3]}₽</b>\nПереведи Боссу: <b>{boss[2]}</b>")
    await c.answer()

@dp.message(F.text == "🔐 Ввести КЛЮЧ услуги")
async def key_start(message: types.Message, state: FSMContext): # FIX: RENAMED TO message, state
    await message.answer("Код:")
    await state.set_state(UnlockMenu.waiting_for_key)

@dp.message(UnlockMenu.waiting_for_key)
async def key_proc(message: types.Message, state: FSMContext): # FIX
    drv = get_driver_by_code(message.text.strip().upper())
    if drv:
        client_driver_link[message.from_user.id] = drv[0]
        await message.answer(f"🔓 <b>ОК!</b>\n👤 {drv[3]}\n🚘 {drv[2]}", reply_markup=main_kb)
        await state.clear()
    else: await message.answer("❌ Нет.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
