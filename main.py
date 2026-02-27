import asyncio
import logging
import os
import sqlite3
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Получение токенов из переменных окружения
API_TOKEN = os.getenv("API_TOKEN")
BOSS_ID = os.getenv("DRIVER_ID") # Твой ID в Telegram

if not API_TOKEN or not BOSS_ID:
    logging.error("CRITICAL: API_TOKEN или DRIVER_ID не найдены в переменных окружения!")
    exit()

BOSS_ID = int(BOSS_ID)
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# Глобальные переменные оперативной памяти
active_orders = {} 
client_driver_link = {} # Связь: {id_клиента: id_водителя} (кто с кем едет)

# ==========================================
# 🗄️ БАЗА ДАННЫХ
# ==========================================
# Используем папку /data для сохранения при перезапуске (для Amvera/Docker)
DB_PATH = "/data/taxi_db.sqlite" if os.path.exists("/data") else "taxi_db.sqlite"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица водителей (с кодом доступа)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            car_info TEXT,
            payment_info TEXT,
            access_code TEXT UNIQUE, 
            status TEXT DEFAULT 'pending',
            balance INTEGER DEFAULT 0
        )
    """)
    
    # Таблица клиентов
    cursor.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY)")
    
    # История заказов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id INTEGER,
            service_name TEXT,
            price INTEGER
        )
    """)
    
    # АВТО-РЕГИСТРАЦИЯ БОССА (Если его нет)
    cursor.execute("SELECT 1 FROM drivers WHERE user_id = ?", (BOSS_ID,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO drivers (user_id, username, car_info, payment_info, access_code, status) VALUES (?, ?, ?, ?, ?, 'active')",
            (BOSS_ID, "BOSS_NETWORK", "BOSS (Black Car)", "Яндекс Банк +79012723729", "BOSS")
        )
        logging.info("Босс зарегистрирован как Супер-Водитель.")
        
    conn.commit()
    conn.close()

init_db()

# --- Вспомогательные функции БД ---

def get_active_drivers():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM drivers WHERE status='active'")
    drivers = cursor.fetchall()
    conn.close()
    return [d[0] for d in drivers]

def get_driver_by_code(code):
    """Поиск водителя по секретному ключу"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, car_info FROM drivers WHERE access_code=? AND status='active'", (code,))
    res = cursor.fetchone()
    conn.close()
    return res # (user_id, username, car_info)

def get_driver_info(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT username, car_info, payment_info, balance, status, access_code FROM drivers WHERE user_id=?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res

def update_driver_field(user_id, field, value):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    query = f"UPDATE drivers SET {field} = ? WHERE user_id = ?"
    cursor.execute(query, (value, user_id))
    conn.commit()
    conn.close()

def extract_price(text):
    """Вытаскивает число из текста цены"""
    nums = re.findall(r'\d+', str(text))
    return int("".join(nums)) if nums else 0

def log_order(driver_id, service_name, price):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO order_history (driver_id, service_name, price) VALUES (?, ?, ?)", (driver_id, service_name, price))
    conn.commit()
    conn.close()

def add_commission(driver_id, amount):
    if driver_id == BOSS_ID: return 
    commission = int(amount * 0.10)
    if commission <= 0: return 
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE drivers SET balance = balance + ? WHERE user_id=?", (commission, driver_id))
    conn.commit()
    conn.close()

def is_client_accepted(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM clients WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return bool(result)

# ==========================================
# 📜 БАЗА УСЛУГ (ПОДРОБНОЕ ОПИСАНИЕ)
# ==========================================
CRAZY_SERVICES = {
    "candy": {
        "name": "🍬 Конфетка", 
        "price": 0, 
        "desc": "Водитель с максимально серьезным лицом вручает вам элитную барбариску или мятный леденец. Это знак уважения."
    },
    "joke": {
        "name": "🎭 Анекдот", 
        "price": 50, 
        "desc": "Анекдот категории Б из золотой коллекции таксиста. Смеяться не обязательно, но желательно, чтобы не обидеть творческую натуру."
    },
    "poem": {
        "name": "📜 Стих с выражением", 
        "price": 100, 
        "desc": "Водитель (по возможности) встает на табуретку или просто поворачивается и читает стихотворение с чувством, как на школьной линейке."
    },
    "sleep": {
        "name": "🛌 Сон под шепот ям", 
        "price": 150, 
        "desc": "Режим 'Ниндзя'. Музыка выключается, водитель молчит как рыба, ямы объезжает шепотом. Вы спите, мы охраняем ваш покой."
    },
    "tale": {
        "name": "📖 Сказка на ночь", 
        "price": 300, 
        "desc": "Потрясающая (и на 90% выдуманная) история о том, как водитель однажды вез олигарха, инопланетянина и вашу бабушку."
    },
    "granny": {
        "name": "👵 Бабушка-ворчунья", 
        "price": 800, 
        "desc": "Ролевая игра. Всю дорогу буду бубнить: 'Куда прешь?', 'Наркоманы одни', 'Шапку надень!'. Полное погружение в детство."
    },
    "spy": {
        "name": "🕵️‍♂️ Шпионский эскорт", 
        "price": 2000, 
        "desc": "Водитель надевает черные очки и кепку. Нервно смотрит в зеркала. Говорит кодами: 'Объект на борту, хвоста нет'. Паранойя включена."
    },
    "karaoke": {
        "name": "🎤 Караоке-баттл", 
        "price": 5000, 
        "desc": "Врубаем хиты 90-х на полную. Поем вместе 'Рюмку водки' или 'Знаешь ли ты'. Водитель фальшивит громко и от души."
    },
    "dance": {
        "name": "🕺 Танцы на светофоре", 
        "price": 15000, 
        "desc": "На красном свете водитель выбегает из машины и танцует макарену или лезгинку перед капотом. Стыдно вам, весело всем вокруг!"
    },
    "kidnap": {
        "name": "🎭 Дружеское похищение", 
        "price": 30000, 
        "desc": "Вас (понарошку) грузят в авто, надевают мешок на голову (по желанию) и везут в лес... пить чай с баранками. Строго по сценарию!"
    },
    "tarzan": {
        "name": "🦍 Тарзан-шоу", 
        "price": 50000, 
        "desc": "Водитель бьет себя в грудь, издает гортанные звуки, рычит на прохожих и называет другие машины 'железными буйволами'. Максимальный кринж."
    },
    "burn": {
        "name": "🔥 Сжечь машину", 
        "price": 1000000, 
        "desc": "Мы едем на пустырь. Вы даете миллион, я даю канистру и спички. Эпичная музыка, машина горит, вы уходите в закат не оборачиваясь."
    }
}

# ==========================================
# 🛠 СОСТОЯНИЯ (FSM)
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

class DriverRegistration(StatesGroup):
    waiting_for_car = State()
    waiting_for_payment_info = State()
    waiting_for_code = State() # Ввод секретного кода

class UnlockMenu(StatesGroup):
    waiting_for_key = State()

class AdminEditDriver(StatesGroup):
    waiting_for_new_value = State()

# ==========================================
# ⌨️ КЛАВИАТУРЫ
# ==========================================
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚕 Заказать такси (Поиск)")],
        [KeyboardButton(text="🔐 Ввести КЛЮЧ услуги")],
        [KeyboardButton(text="📜 CRAZY ХАОС-МЕНЮ (В поездке)")],
        [KeyboardButton(text="💡 Свой вариант (Предложить идею)")],
        [KeyboardButton(text="⚖️ Вызвать адвоката / Правила")]
    ], resize_keyboard=True
)

tos_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ Я В МАШИНЕ, ОСОЗНАЮ ПОСЛЕДСТВИЯ", callback_data="accept_tos")],
    [InlineKeyboardButton(text="❌ Выпустите меня!", callback_data="decline_tos")]
])

# ==========================================
# 🛑 СТАРТ И КОНТРАКТ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    disclaimer_text = (
        "⚠️ <b>ОФИЦИАЛЬНОЕ ПРЕДУПРЕЖДЕНИЕ</b> ⚠️\n\n"
        "ВНИМАНИЕ! Вы пытаетесь воспользоваться услугами <b>Crazy Taxi</b>.\n"
        "Салон этого автомобиля является юридически неприкосновенной зоной <b>Арт-перформанса</b>.\n\n"
        "<b>Нажимая кнопку ниже, вы подтверждаете, что:</b>\n"
        "1. Любая дичь, происходящая внутри, классифицируется как 'современное искусство'.\n"
        "2. Вы заранее отказываетесь от любых судебных исков.\n"
        "3. Наш адвокат слишком хорош. Судиться с нами бесполезно.\n"
        "4. Вы находитесь в салоне добровольно.\n\n"
        "<i>Готов шагнуть в зону абсолютной юридической анархии?</i>"
    )
    await message.answer(disclaimer_text, reply_markup=tos_kb)

@dp.callback_query(F.data == "accept_tos")
async def tos_accepted(callback: types.CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (callback.from_user.id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("🔥 <b>ДОБРО ПОЖАЛОВАТЬ В CRAZY TAXI!</b> 🔥\nКонтракт подписан. Двери заблокированы.")
    await callback.message.answer("Выбирай действие в меню ниже 👇", reply_markup=main_kb)

@dp.callback_query(F.data == "decline_tos")
async def tos_declined(callback: types.CallbackQuery):
    await callback.message.edit_text("🚶‍♂️ Очень жаль! Удачной пешей прогулки!")

async def check_tos(message: types.Message) -> bool:
    if not is_client_accepted(message.from_user.id):
        await message.answer("🛑 <b>ОШИБКА ДОСТУПА!</b>\nСначала нужно подписать контракт. Нажми /start")
        return False
    return True

@dp.message(F.text == "⚖️ Вызвать адвоката / Правила")
async def lawyer_menu(message: types.Message):
    if not await check_tos(message): return
    lawyer_text = "⚖️ <b>НАШ НЕПОБЕДИМЫЙ АДВОКАТ</b> ⚖️\n\nЧитать права здесь будет только он, и то на латыни."
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚨 СВЯЗАТЬСЯ С АДВОКАТОМ 🚨", callback_data="call_lawyer")]])
    await message.answer(lawyer_text, reply_markup=kb)

@dp.callback_query(F.data == "call_lawyer")
async def alert_lawyer(callback: types.CallbackQuery):
    await callback.answer("🚨 Адвокат занят подачей иска на твою скуку.", show_alert=True)

# ==========================================
# 🚀 УМНАЯ РАССЫЛКА И МОНИТОРИНГ
# ==========================================
async def update_boss_monitor(client_id, taking_driver_id):
    order = active_orders.get(client_id)
    if not order or 'boss_msg_id' not in order: return
    
    drv_info = get_driver_info(taking_driver_id)
    drv_name = f"@{drv_info[0]}" if drv_info[0] else "Unknown"
    
    text_prefix = "🚫 <b>ЗАКАЗ ЗАБРАЛ:</b> "
    if taking_driver_id == BOSS_ID: text_prefix += "<b>ТЫ (БОСС)!</b>"
    else: text_prefix += f"Водитель {drv_name} ({drv_info[1]})"
        
    original_text = order.get('broadcasting_text', '')
    new_text = f"{text_prefix}\n\n{original_text}"
    
    try: await bot.edit_message_text(chat_id=BOSS_ID, message_id=order['boss_msg_id'], text=new_text, reply_markup=None)
    except TelegramBadRequest: pass

async def broadcast_order_to_drivers(client_id, order_text, driver_kb, boss_kb):
    # 1. Отправка Боссу
    boss_monitor_text = f"🚨 <b>МОНИТОРИНГ СЕТИ</b> 🚨\n\n{order_text}"
    boss_msg = await bot.send_message(chat_id=BOSS_ID, text=boss_monitor_text, reply_markup=boss_kb)
    
    if client_id in active_orders:
        active_orders[client_id]['boss_msg_id'] = boss_msg.message_id
        active_orders[client_id]['broadcasting_text'] = order_text

    # 2. Имитация поиска для клиента
    search_msg = await bot.send_message(client_id, "📡 <i>Радары включены. Ищем водителей...</i>")
    await asyncio.sleep(2.0) 
    
    drivers = get_active_drivers()
    drivers_to_broadcast = [d for d in drivers if d != BOSS_ID]
    
    if not drivers_to_broadcast:
        await search_msg.edit_text("😔 <b>Нет свободных машин.</b>\nБосс уведомлен.")
        return
        
    await search_msg.edit_text("⏳ <b>Сигнал передан водителям!</b>\nЖдем, кто успеет...")
    
    async def send_to_driver(d_id):
        try:
            await bot.send_message(chat_id=d_id, text=order_text, reply_markup=driver_kb)
            return True
        except: return False

    tasks = [send_to_driver(d_id) for d_id in drivers_to_broadcast]
    await asyncio.gather(*tasks)

# ==========================================
# 🔐 СИСТЕМА КЛЮЧЕЙ (ПРИВЯЗКА)
# ==========================================
@dp.message(F.text == "🔐 Ввести КЛЮЧ услуги")
async def ask_for_key(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    await message.answer("🕵️‍♂️ <b>Введи секретный код водителя</b> (спроси у него):\n\nЭто разблокирует Crazy-меню для этой машины.")
    await state.set_state(UnlockMenu.waiting_for_key)

@dp.message(UnlockMenu.waiting_for_key)
async def process_key(message: types.Message, state: FSMContext):
    code = message.text.strip()
    driver = get_driver_by_code(code)
    
    if driver:
        driver_id, driver_name, car_info = driver
        client_driver_link[message.from_user.id] = driver_id
        
        await message.answer(f"🔓 <b>ДОСТУП РАЗРЕШЕН!</b>\n\n🚘 Борт: <b>{car_info}</b>\n👤 Водитель: <b>@{driver_name}</b>\n\nТеперь раздел 'CRAZY МЕНЮ' работает для этого водителя.", reply_markup=main_kb)
        await state.clear()
        try: await bot.send_message(driver_id, f"🔗 Клиент @{message.from_user.username} активировал твой ключ!")
        except: pass
    else:
        await message.answer("❌ <b>Неверный ключ!</b> Попробуй снова.")

# ==========================================
# 📜 CRAZY МЕНЮ (ПО ПРИВЯЗКЕ)
# ==========================================
@dp.message(F.text == "📜 CRAZY ХАОС-МЕНЮ (В поездке)")
async def show_crazy_menu(message: types.Message):
    if not await check_tos(message): return
    
    # Проверка привязки
    if message.from_user.id not in client_driver_link:
        await message.answer("🔒 <b>МЕНЮ ЗАБЛОКИРОВАНО</b>\nНажми '🔐 Ввести КЛЮЧ услуги' и введи код водителя.", reply_markup=main_kb)
        return

    buttons = []
    keys = list(CRAZY_SERVICES.keys())
    for i in range(0, len(keys), 2):
        row = []
        for key in keys[i:i+2]:
            data = CRAZY_SERVICES[key]
            price_text = "🆓 0₽" if data['price'] == 0 else f"{data['price']}₽"
            row.append(InlineKeyboardButton(text=f"{data['name']} ({price_text})", callback_data=f"csel_{key}"))
        buttons.append(row)
    await message.answer("🔥 <b>CRAZY МЕНЮ (ПРЯМОЙ ЗАКАЗ)</b> 🔥", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("csel_"))
async def process_crazy_selection(callback: types.CallbackQuery):
    client_id = callback.from_user.id
    driver_id = client_driver_link.get(client_id)
    
    if not driver_id:
        await callback.answer("Связь потеряна. Введите ключ заново!", show_alert=True)
        return

    service_key = callback.data.split("_")[1]
    service = CRAZY_SERVICES[service_key]
    
    active_orders[client_id] = {"type": "crazy", "status": "direct_order", "price": str(service["price"]), "driver_id": driver_id, "service": service}
    price_text = "БЕСПЛАТНО" if service["price"] == 0 else f"{service['price']}₽"
    
    await callback.message.edit_text(f"🚀 <b>Отправлено водителю!</b>\n🎪 Услуга: {service['name']}\n📝 {service['desc']}\n💰 {price_text}")
    
    # Отправка водителю напрямую
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ И ВЫПОЛНИТЬ", callback_data=f"driver_direct_accept_{client_id}")]])
    await bot.send_message(driver_id, f"🔔 <b>ПЕРСОНАЛЬНЫЙ ЗАКАЗ</b>\n👤 Клиент здесь!\n🎭 <b>{service['name']}</b>", reply_markup=kb)
    
    if driver_id != BOSS_ID:
        await bot.send_message(BOSS_ID, f"👀 <b>КОНТРОЛЬ:</b> @{callback.from_user.username} -> {service['name']} (Водитель {driver_id})")

@dp.callback_query(F.data.startswith("driver_direct_accept_"))
async def driver_direct_accept(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[3])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return
    
    driver_info = get_driver_info(driver_id)
    price_val = extract_price(order['price'])
    
    if price_val == 0:
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ЖДУ!", callback_data=f"cpay_done_{client_id}")]])
        await bot.send_message(client_id, f"✅ Водитель принял!\n🎁 Услуга бесплатная. Жми кнопку!", reply_markup=pay_kb)
    else:
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Я ОПЛАТИЛ", callback_data=f"cpay_done_{client_id}")]])
        await bot.send_message(client_id, f"✅ Водитель готов!\n💳 Переведи <b>{order['price']}</b> на: <code>{driver_info[2]}</code>", reply_markup=pay_kb)
    
    await callback.message.edit_text("✅ Принято. Жди подтверждения клиента.")

# --- Оплата Crazy ---
@dp.callback_query(F.data.startswith("cpay_done_"))
async def client_paid_crazy(callback: types.CallbackQuery):
    client_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ВЫПОЛНИЛ", callback_data=f"confirm_pay_{client_id}")]])
    await callback.message.edit_text("⏳ Ожидание водителя...")
    await bot.send_message(order["driver_id"], f"💸 Клиент готов! Выполняй.", reply_markup=kb)

@dp.callback_query(F.data.startswith("confirm_pay_"))
async def driver_confirms_pay(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return
    
    price_int = extract_price(order['price'])
    add_commission(driver_id, price_int)
    log_order(driver_id, order['service']['name'], price_int)
    
    await callback.message.edit_text("✅ Выполнено.")
    await bot.send_message(client_id, "🎉 Услуга выполнена!")
    del active_orders[client_id]

# ==========================================
# 🚕 ТАКСИ + ПОИСК + ТОРГ
# ==========================================
@dp.message(F.text == "🚕 Заказать такси (Поиск)")
async def start_ride_order(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    await message.answer("📍 <b>Откуда?</b>", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(OrderRide.waiting_for_from)

@dp.message(OrderRide.waiting_for_from)
async def process_from(message: types.Message, state: FSMContext):
    await state.update_data(from_address=message.text)
    await message.answer("🏁 <b>Куда?</b>")
    await state.set_state(OrderRide.waiting_for_to)

@dp.message(OrderRide.waiting_for_to)
async def process_to(message: types.Message, state: FSMContext):
    await state.update_data(to_address=message.text)
    await message.answer("📞 <b>Телефон:</b>")
    await state.set_state(OrderRide.waiting_for_phone)

@dp.message(OrderRide.waiting_for_phone)
async def process_ph(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("💰 <b>Цена?</b>")
    await state.set_state(OrderRide.waiting_for_price)

@dp.message(OrderRide.waiting_for_price)
async def process_pr(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    client_id = message.from_user.id
    
    active_orders[client_id] = {
        "type": "taxi", "status": "pending", "price": message.text,
        "from": user_data['from_address'], "to": user_data['to_address'], "phone": user_data['phone'],
        "driver_offers": {}
    }
    await message.answer("✅ Ищем...", reply_markup=main_kb)
    await state.clear()
    
    dkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Забрать", callback_data=f"take_taxi_{client_id}")], [InlineKeyboardButton(text="💰 Своя цена", callback_data=f"counter_taxi_{client_id}")]])
    bkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ БОСС ЗАБРАТЬ", callback_data=f"boss_take_taxi_{client_id}")], [InlineKeyboardButton(text="💰 Своя цена", callback_data=f"counter_taxi_{client_id}")]])
    
    text = f"🚕 <b>ТАКСИ</b>\n📍 {user_data['from_address']} -> {user_data['to_address']}\n💰 {message.text}"
    await broadcast_order_to_drivers(client_id, text, dkb, bkb)

@dp.callback_query(F.data.startswith("take_taxi_") | F.data.startswith("boss_take_taxi_"))
async def take_taxi(callback: types.CallbackQuery):
    is_boss = callback.data.startswith("boss_take_")
    client_id = int(callback.data.split("_")[3 if is_boss else 2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)
    
    if not order or order["status"] != "pending":
        await callback.answer("Занято!", show_alert=True)
        if not is_boss: await callback.message.delete()
        return
    
    order["status"] = "accepted"
    order["driver_id"] = driver_id
    await update_boss_monitor(client_id, driver_id)
    
    # АВТОМАТИЧЕСКАЯ ПРИВЯЗКА!
    client_driver_link[client_id] = driver_id
    
    info = get_driver_info(driver_id)
    finish_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Завершить поездку", callback_data=f"finish_taxi_{client_id}")]])
    
    await callback.message.edit_text(f"✅ Взято. Клиент: {order['phone']}", reply_markup=finish_kb)
    await bot.send_message(client_id, f"🚕 Едет: {info[0]} ({info[1]})\n📞 {order['phone']}\n\n🔐 <b>Твой код Crazy-меню:</b> {info[5]}")

@dp.callback_query(F.data.startswith("finish_taxi_"))
async def finish_taxi(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return

    price_int = extract_price(order['price'])
    add_commission(driver_id, price_int)
    log_order(driver_id, "Обычное такси", price_int) 
    
    await callback.message.edit_text("✅ Завершено.")
    await bot.send_message(client_id, "🏁 Поездка завершена.")
    del active_orders[client_id]

# ==========================================
# 💡 СВОЙ ВАРИАНТ (АУКЦИОН)
# ==========================================
@dp.message(F.text == "💡 Свой вариант (Предложить идею)")
async def custom_idea_start(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    await message.answer("Опиши идею:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(CustomIdea.waiting_for_idea)

@dp.message(CustomIdea.waiting_for_idea)
async def process_custom_idea(message: types.Message, state: FSMContext):
    await state.update_data(idea=message.text)
    await message.answer("💰 <b>Бюджет?</b>", reply_markup=main_kb)
    await state.set_state(CustomIdea.waiting_for_price)

@dp.message(CustomIdea.waiting_for_price)
async def process_custom_price(message: types.Message, state: FSMContext):
    data = await state.get_data()
    idea, price = data['idea'], message.text
    client_id = message.from_user.id
    
    active_orders[client_id] = {
        "type": "crazy", "status": "pending", "price": price,
        "service": {"name": f"💡 Идея ({idea[:15]}...)", "desc": idea},
        "driver_offers": {}
    }
    await message.answer("✅ Отправлено!", reply_markup=main_kb)
    await state.clear()

    dkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ЗАБРАТЬ", callback_data=f"take_crazy_{client_id}")], [InlineKeyboardButton(text="💰 Своя цена", callback_data=f"counter_crazy_{client_id}")]])
    bkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ЗАБРАТЬ (БОСС)", callback_data=f"boss_take_crazy_{client_id}")], [InlineKeyboardButton(text="💰 Своя цена", callback_data=f"counter_crazy_{client_id}")]])
    
    text = f"💡 <b>ИДЕЯ</b>\n📝 {idea}\n💰 {price}"
    await broadcast_order_to_drivers(client_id, text, dkb, bkb)

# Универсальный обработчик для взятия Crazy/Идеи (без привязки, из общего потока)
@dp.callback_query(F.data.startswith("take_crazy_") | F.data.startswith("boss_take_crazy_"))
async def take_crazy_general(callback: types.CallbackQuery):
    is_boss = callback.data.startswith("boss_take_")
    client_id = int(callback.data.split("_")[3 if is_boss else 2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)
    
    if not order or order["status"] != "pending":
        await callback.answer("Занято!", show_alert=True)
        return
        
    order["status"] = "accepted"
    order["driver_id"] = driver_id
    client_driver_link[client_id] = driver_id # ПРИВЯЗКА
    
    await update_boss_monitor(client_id, driver_id)
    await callback.message.edit_text("✅ Взято.")
    
    info = get_driver_info(driver_id)
    
    pay_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 ОПЛАТИЛ", callback_data=f"cpay_done_{client_id}")]])
    await bot.send_message(client_id, f"✅ Исполнитель: {info[0]}\n💳 Реквизиты: <code>{info[2]}</code>\n🔐 Код: {info[5]}", reply_markup=pay_kb)

# ==========================================
# 🤝 ТОРГ (COUNTER-OFFER)
# ==========================================
@dp.callback_query(F.data.startswith("counter_"))
async def start_counter(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    order_type, client_id = parts[1], int(parts[2])
    await state.update_data(target_client_id=client_id, order_type=order_type)
    await callback.message.answer("✍️ Твоя цена и условия:")
    await state.set_state(DriverCounterOffer.waiting_for_offer)
    await callback.answer()

@dp.message(DriverCounterOffer.waiting_for_offer)
async def send_counter(message: types.Message, state: FSMContext):
    data = await state.get_data()
    client_id, order_type, text = data.get('target_client_id'), data.get('order_type'), message.text
    driver_id = message.from_user.id
    
    order = active_orders.get(client_id)
    if not order: 
        await message.answer("Поздно.")
        return
        
    if "driver_offers" not in order: order["driver_offers"] = {}
    order["driver_offers"][driver_id] = text
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Да", callback_data=f"acc_coff_{order_type}_{client_id}_{driver_id}")], [InlineKeyboardButton(text="❌ Нет", callback_data=f"rej_coff_{client_id}")]])
    
    label = "БОСС" if driver_id == BOSS_ID else "Водитель"
    await bot.send_message(client_id, f"⚡️ <b>{label} предлагает:</b>\n{text}", reply_markup=kb)
    await message.answer("✅ Отправлено.")
    await state.clear()

@dp.callback_query(F.data.startswith("acc_coff_"))
async def accept_offer(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    order_type, client_id, driver_id = parts[2], int(parts[3]), int(parts[4])
    
    order = active_orders.get(client_id)
    if not order or order["status"] != "pending": return
    
    order["status"] = "accepted"
    order["driver_id"] = driver_id
    order["price"] = order["driver_offers"].get(driver_id, order["price"])
    client_driver_link[client_id] = driver_id # ПРИВЯЗКА
    
    await update_boss_monitor(client_id, driver_id)
    
    info = get_driver_info(driver_id)
    
    if order_type == "crazy":
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 ОПЛАТИЛ", callback_data=f"cpay_done_{client_id}")]])
        await callback.message.edit_text(f"🤝 Договорились!\n💳 {info[2]}\n🔐 Код: {info[5]}", reply_markup=pay_kb)
        await bot.send_message(driver_id, "✅ Клиент согласен! Жди оплату.")
    else:
        finish_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Завершить", callback_data=f"finish_taxi_{client_id}")]])
        await bot.send_message(driver_id, f"✅ Клиент согласен!\n📞 {order['phone']}", reply_markup=finish_kb)
        await callback.message.edit_text(f"🚕 Едет: {info[0]}\n🔐 Код: {info[5]}")

@dp.callback_query(F.data.startswith("rej_coff_"))
async def reject_offer(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Отказ.")

# ==========================================
# 🚦 РЕГИСТРАЦИЯ И АДМИНКА
# ==========================================
@dp.message(Command("driver"))
async def cmd_driver_reg(message: types.Message, state: FSMContext):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT status FROM drivers WHERE user_id=?", (message.from_user.id,)).fetchone()
    conn.close()
    if res:
        await message.answer("Ты уже в базе (или забанен). /cab")
        return
    await message.answer("🚕 Авто, цвет, номер:")
    await state.set_state(DriverRegistration.waiting_for_car)

@dp.message(DriverRegistration.waiting_for_car)
async def reg_car(message: types.Message, state: FSMContext):
    await state.update_data(car=message.text)
    await message.answer("💳 Реквизиты:")
    await state.set_state(DriverRegistration.waiting_for_payment_info)

@dp.message(DriverRegistration.waiting_for_payment_info)
async def reg_pay(message: types.Message, state: FSMContext):
    await state.update_data(pay=message.text)
    await message.answer("🔑 <b>Придумай КОД-КЛЮЧ</b> (напр: 777, BOSS):\nЧтобы клиенты открывали твое меню.")
    await state.set_state(DriverRegistration.waiting_for_code)

@dp.message(DriverRegistration.waiting_for_code)
async def reg_code(message: types.Message, state: FSMContext):
    code = message.text.upper().strip()
    data = await state.get_data()
    
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO drivers (user_id, username, car_info, payment_info, access_code, status) VALUES (?, ?, ?, ?, ?, 'pending')", 
                     (message.from_user.id, message.from_user.username, data['car'], data['pay'], code))
        conn.commit()
        await message.answer("📝 Заявка у Босса.")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Одобрить", callback_data=f"adm_approve_{message.from_user.id}")]])
        await bot.send_message(BOSS_ID, f"🚨 <b>ЗАЯВКА</b>\n@{message.from_user.username}\nАвто: {data['car']}\nКод: {code}", reply_markup=kb)
    except sqlite3.IntegrityError:
        await message.answer("❌ Код занят!")
        return
    finally:
        conn.close()
    await state.clear()

@dp.message(Command("cab"))
async def cmd_cab(message: types.Message):
    info = get_driver_info(message.from_user.id)
    if not info or info[4] != 'active':
        await message.answer("❌ Нет доступа.")
        return
    
    # Статистика
    conn = sqlite3.connect(DB_PATH)
    hist = conn.execute("SELECT COUNT(*), SUM(price) FROM order_history WHERE driver_id=?", (message.from_user.id,)).fetchone()
    conn.close()
    
    # Активные заказы
    active_txt = ""
    for cid, o in active_orders.items():
        if o.get("driver_id") == message.from_user.id and o["status"] != "pending":
            name = o.get("service", {}).get("name", "Такси")
            active_txt += f"🔹 {name} | {o['price']}\n"
            
    await message.answer(f"🪪 <b>КАБИНЕТ</b>\n🔑 Твой код: <b>{info[5]}</b>\n💰 Долг: {info[3]}₽\n📊 Всего: {hist[1] or 0}₽\n\nВ работе:\n{active_txt}")

# Админ-панель
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != BOSS_ID: return
    conn = sqlite3.connect(DB_PATH)
    drivers = conn.execute("SELECT user_id, username, status, balance FROM drivers").fetchall()
    conn.close()
    text = "👑 <b>АДМИНКА</b>\n"
    for d in drivers:
        icon = "🟢" if d[2]=='active' else "🔴"
        text += f"{icon} {d[1]} (ID:{d[0]})\nДолг: {d[3]} | /edit_{d[0]}\n\n"
    await message.answer(text)

@dp.callback_query(F.data.startswith("adm_approve_"))
async def adm_app(c: types.CallbackQuery):
    if c.from_user.id != BOSS_ID: return
    d_id = int(c.data.split("_")[2])
    update_driver_field(d_id, "status", "active")
    await c.message.edit_text("✅ Одобрено")
    try: await bot.send_message(d_id, "🎉 Ты принят! /cab")
    except: pass

@dp.message(F.text.startswith("/edit_"))
async def edit_dr(m: types.Message):
    if m.from_user.id != BOSS_ID: return
    d_id = int(m.text.split("_")[1])
    info = get_driver_info(d_id)
    
    blk_txt = "Заблочить" if info[4]=='active' else "Разблочить"
    act = "block" if info[4]=='active' else "unblock"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Авто", callback_data=f"edt_car_{d_id}"), InlineKeyboardButton(text="Рекв", callback_data=f"edt_pay_{d_id}")],
        [InlineKeyboardButton(text="Баланс", callback_data=f"edt_bal_{d_id}"), InlineKeyboardButton(text="Код", callback_data=f"edt_acc_{d_id}")],
        [InlineKeyboardButton(text=blk_txt, callback_data=f"adm_act_{act}_{d_id}"), InlineKeyboardButton(text="Счет", callback_data=f"adm_act_bill_{d_id}")]
    ])
    await m.answer(f"РЕДАКТОР: {info[0]}\nКод: {info[5]}", reply_markup=kb)

@dp.callback_query(F.data.startswith("edt_"))
async def edt_cb(c: types.CallbackQuery, state: FSMContext):
    parts = c.data.split("_")
    fmap = {"car":"car_info", "pay":"payment_info", "bal":"balance", "acc":"access_code"}
    await state.update_data(did=int(parts[2]), fld=fmap[parts[1]])
    await c.message.answer("Новое значение:")
    await state.set_state(AdminEditDriver.waiting_for_new_value)
    await c.answer()

@dp.message(AdminEditDriver.waiting_for_new_value)
async def edt_save(m: types.Message, state: FSMContext):
    data = await state.get_data()
    update_driver_field(data['did'], data['fld'], m.text)
    await m.answer("✅ Сохранено.")
    await state.clear()

@dp.callback_query(F.data.startswith("adm_act_"))
async def adm_act(c: types.CallbackQuery):
    if c.from_user.id != BOSS_ID: return
    parts = c.data.split("_")
    act, d_id = parts[2], int(parts[3])
    
    if act == "block":
        update_driver_field(d_id, "status", "blocked")
        await c.message.edit_text("🔒 Блок.")
    elif act == "unblock":
        update_driver_field(d_id, "status", "active")
        await c.message.edit_text("🔓 Разблок.")
    elif act == "bill":
        info = get_driver_info(d_id)
        try: await bot.send_message(d_id, f"⚠️ ОПЛАТИ ДОЛГ: {info[3]}₽")
        except: pass
        await c.answer("Счет отправлен.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
