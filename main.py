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

logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("API_TOKEN")
BOSS_ID = os.getenv("DRIVER_ID") # Твой ID

if not API_TOKEN or not BOSS_ID:
    logging.error("ВНИМАНИЕ: API_TOKEN или DRIVER_ID не найдены!")

BOSS_ID = int(BOSS_ID)
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

active_orders = {} 

# ==========================================
# 🗄️ БАЗА ДАННЫХ
# ==========================================
DB_PATH = "/data/taxi_db.sqlite" if os.path.exists("/data") else "taxi_db.sqlite"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            car_info TEXT,
            payment_info TEXT,
            status TEXT DEFAULT 'pending',
            balance INTEGER DEFAULT 0
        )
    """)
    cursor.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id INTEGER,
            service_name TEXT,
            price INTEGER
        )
    """)
    # АВТО-РЕГИСТРАЦИЯ БОССА
    cursor.execute("SELECT 1 FROM drivers WHERE user_id = ?", (BOSS_ID,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO drivers (user_id, username, car_info, payment_info, status) VALUES (?, ?, ?, ?, 'active')",
            (BOSS_ID, "BOSS_NETWORK", "BOSS (Black Car)", "Яндекс Банк +79012723729 (Босс)")
        )
    conn.commit()
    conn.close()

init_db()

def get_active_drivers():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM drivers WHERE status='active'")
    drivers = cursor.fetchall()
    conn.close()
    return [d[0] for d in drivers]

def get_driver_info(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT username, car_info, payment_info, balance, status FROM drivers WHERE user_id=?", (user_id,))
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

# --- БАЗА УСЛУГ (ПОДРОБНОЕ ОПИСАНИЕ) ---
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

class AdminEditDriver(StatesGroup):
    waiting_for_new_value = State()

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚕 Заказать такси (Торг)")],
        [KeyboardButton(text="📜 CRAZY ХАОС-МЕНЮ")],
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
# 🚀 МОНИТОРИНГ И РАССЫЛКА
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
    # 1. Босс
    boss_monitor_text = f"🚨 <b>МОНИТОРИНГ СЕТИ</b> 🚨\n\n{order_text}"
    boss_msg = await bot.send_message(chat_id=BOSS_ID, text=boss_monitor_text, reply_markup=boss_kb)
    
    if client_id in active_orders:
        active_orders[client_id]['boss_msg_id'] = boss_msg.message_id
        active_orders[client_id]['broadcasting_text'] = order_text

    # 2. Клиент
    search_msg = await bot.send_message(client_id, "📡 <i>Радары включены. Ищем безумцев...</i>")
    await asyncio.sleep(2.5) 
    
    drivers = get_active_drivers()
    drivers_to_broadcast = [d for d in drivers if d != BOSS_ID]
    
    if not drivers_to_broadcast:
        await search_msg.edit_text("😔 <b>Все водители заняты.</b>\nБосс уведомлен.")
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
# 📜 ЗАКАЗЫ И УСЛУГИ
# ==========================================
@dp.message(F.text == "📜 CRAZY ХАОС-МЕНЮ")
async def show_crazy_menu(message: types.Message):
    if not await check_tos(message): return
    buttons = []
    keys = list(CRAZY_SERVICES.keys())
    for i in range(0, len(keys), 2):
        row = []
        for key in keys[i:i+2]:
            data = CRAZY_SERVICES[key]
            price_text = "🆓 0₽" if data['price'] == 0 else f"{data['price']}₽"
            row.append(InlineKeyboardButton(text=f"{data['name']} ({price_text})", callback_data=f"csel_{key}"))
        buttons.append(row)
    await message.answer("🔥 <b>CRAZY DRIVER'S CHAOS MENU</b> 🔥", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("csel_"))
async def process_crazy_selection(callback: types.CallbackQuery):
    service_key = callback.data.split("_")[1]
    service = CRAZY_SERVICES[service_key]
    client_id = callback.from_user.id
    
    active_orders[client_id] = {"type": "crazy", "service": service, "status": "pending", "price": str(service["price"])}
    price_text = "БЕСПЛАТНО" if service["price"] == 0 else f"{service['price']}₽"
    
    await callback.message.edit_text(f"🎪 <b>ВЫБРАНА УСЛУГА:</b> {service['name']}\n📝 <b>Описание:</b> {service['desc']}\n💰 <b>Стоимость:</b> {price_text}")
    
    driver_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ЗАБРАТЬ", callback_data=f"take_crazy_{client_id}")]])
    boss_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ЗАБРАТЬ (БОСС)", callback_data=f"boss_take_crazy_{client_id}")]])
    
    text = f"🚨 <b>ХАОС-ЗАКАЗ!</b> 🚨\nКлиент: @{callback.from_user.username}\nУслуга: <b>{service['name']}</b> ({price_text})"
    await broadcast_order_to_drivers(client_id, text, driver_kb, boss_kb)

@dp.callback_query(F.data.startswith("take_crazy_") | F.data.startswith("boss_take_crazy_"))
async def driver_takes_crazy(callback: types.CallbackQuery):
    is_boss_taking = callback.data.startswith("boss_take_")
    client_id = int(callback.data.split("_")[3 if is_boss_taking else 2])
    driver_id = callback.from_user.id
    
    order = active_orders.get(client_id)
    if not order or order["status"] != "pending":
        await callback.answer("Упс! Заказ уже забрали.", show_alert=True)
        if not is_boss_taking: await callback.message.delete()
        return

    order["status"] = "accepted"
    order["driver_id"] = driver_id
    await update_boss_monitor(client_id, driver_id)
    
    await callback.message.edit_text(f"✅ Ты забрал заказ: {order['service']['name']}!")
    
    driver_info = get_driver_info(driver_id)
    price_val = extract_price(order['price'])
    drv_name = "Сам БОСС Crazy Taxi" if is_boss_taking else driver_info[0]
    
    if price_val == 0:
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ЖДУ СЮРПРИЗ!", callback_data=f"cpay_done_{client_id}")]])
        client_text = f"🚕 <b>ВОДИТЕЛЬ НАЙДЕН!</b>\nК тебе едет: {drv_name} ({driver_info[1]})\n🎁 <b>Бесплатно!</b>\nЖми кнопку!"
    else:
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Я ОПЛАТИЛ", callback_data=f"cpay_done_{client_id}")]])
        client_text = f"🚕 <b>ВОДИТЕЛЬ НАЙДЕН!</b>\nК тебе едет: {drv_name} ({driver_info[1]})\n💳 <b>Переведи ({order['price']}) на:</b>\n<code>{driver_info[2]}</code>\nЖми кнопку!"
        
    await bot.send_message(client_id, client_text, reply_markup=pay_kb)

@dp.callback_query(F.data.startswith("cpay_done_"))
async def client_paid_crazy(callback: types.CallbackQuery):
    client_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ВЫПОЛНИЛ", callback_data=f"confirm_pay_{client_id}")]])
    await callback.message.edit_text("⏳ Ожидание водителя...")
    await bot.send_message(order["driver_id"], f"🎁 Клиент @{callback.from_user.username} готов к: <b>{order['service']['name']}</b>!\nСделай и нажми.", reply_markup=kb)

@dp.callback_query(F.data.startswith("confirm_pay_"))
async def driver_confirms_pay(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return
    
    price_int = extract_price(order['price'])
    add_commission(driver_id, price_int)
    log_order(driver_id, order['service']['name'], price_int)
    
    await callback.message.edit_text("✅ Выполнено! Записано в историю.")
    await bot.send_message(client_id, "🎉 Водитель подтвердил выполнение!")
    del active_orders[client_id]

# ==========================================
# 💡 СВОЙ ВАРИАНТ
# ==========================================
@dp.message(F.text == "💡 Свой вариант (Предложить идею)")
async def custom_idea_start(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    await message.answer("Опиши идею:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(CustomIdea.waiting_for_idea)

@dp.message(CustomIdea.waiting_for_idea)
async def process_custom_idea(message: types.Message, state: FSMContext):
    await state.update_data(idea=message.text)
    await message.answer("💰 <b>Бюджет?</b> (сумма):")
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
    await message.answer("✅ <b>Зафиксировано!</b>", reply_markup=main_kb)
    await state.clear()

    driver_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ЗАБРАТЬ", callback_data=f"take_crazy_{client_id}")], [InlineKeyboardButton(text="💰 Своя цена", callback_data=f"counter_crazy_{client_id}")]])
    boss_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ЗАБРАТЬ (БОСС)", callback_data=f"boss_take_crazy_{client_id}")], [InlineKeyboardButton(text="💰 Своя цена", callback_data=f"counter_crazy_{client_id}")]])
    
    text = f"💡 <b>ИДЕЯ ОТ КЛИЕНТА</b> 💡\n👤 @{message.from_user.username}\n📝: {idea}\n💰 Бюджет: <b>{price}</b>"
    await broadcast_order_to_drivers(client_id, text, driver_kb, boss_kb)

# ==========================================
# 🚕 ТАКСИ + ТОРГ
# ==========================================
@dp.message(F.text == "🚕 Заказать такси (Торг)")
async def start_ride_order(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    await message.answer("📍 <b>Откуда?</b>", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(OrderRide.waiting_for_from)

@dp.message(OrderRide.waiting_for_from)
async def process_from_address(message: types.Message, state: FSMContext):
    await state.update_data(from_address=message.text)
    await message.answer("🏁 <b>Куда?</b>")
    await state.set_state(OrderRide.waiting_for_to)

@dp.message(OrderRide.waiting_for_to)
async def process_to_address(message: types.Message, state: FSMContext):
    await state.update_data(to_address=message.text)
    await message.answer("📞 <b>Твой телефон:</b>")
    await state.set_state(OrderRide.waiting_for_phone)

@dp.message(OrderRide.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("💰 <b>Цена?</b>")
    await state.set_state(OrderRide.waiting_for_price)

@dp.message(OrderRide.waiting_for_price)
async def process_price(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    client_id = message.from_user.id
    
    active_orders[client_id] = {
        "type": "taxi", "status": "pending", "price": message.text,
        "from": user_data['from_address'], "to": user_data['to_address'], "phone": user_data['phone'],
        "driver_offers": {}
    }
    await message.answer("✅ <b>Принято!</b>", reply_markup=main_kb)
    await state.clear()

    driver_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Забрать", callback_data=f"take_taxi_{client_id}")], [InlineKeyboardButton(text="💰 Своя цена", callback_data=f"counter_taxi_{client_id}")]])
    boss_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ЗАБРАТЬ (БОСС)", callback_data=f"boss_take_taxi_{client_id}")], [InlineKeyboardButton(text="💰 Своя цена", callback_data=f"counter_taxi_{client_id}")]])
    
    text = f"🚕 <b>ЗАКАЗ ТАКСИ</b> 🚕\n📍: {user_data['from_address']}\n🏁: {user_data['to_address']}\n💰: <b>{message.text}</b>"
    await broadcast_order_to_drivers(client_id, text, driver_kb, boss_kb)

@dp.callback_query(F.data.startswith("take_taxi_") | F.data.startswith("boss_take_taxi_"))
async def driver_takes_taxi(callback: types.CallbackQuery):
    is_boss_taking = callback.data.startswith("boss_take_")
    client_id = int(callback.data.split("_")[3 if is_boss_taking else 2])
    driver_id = callback.from_user.id
    
    order = active_orders.get(client_id)
    if not order or order["status"] != "pending":
        await callback.answer("Упс! Заказ забрали.", show_alert=True)
        if not is_boss_taking: await callback.message.delete()
        return

    order["status"] = "accepted"
    order["driver_id"] = driver_id
    await update_boss_monitor(client_id, driver_id)
    
    finish_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Завершить", callback_data=f"finish_taxi_{client_id}")]])
    
    if is_boss_taking: await callback.message.edit_text(f"✅ Ты забрал такси!\n📞: <b>{order['phone']}</b>", reply_markup=finish_kb)
    else: await callback.message.edit_text(f"✅ Ты забрал поездку!\n📞: <b>{order['phone']}</b>", reply_markup=finish_kb)
        
    driver_info = get_driver_info(driver_id)
    drv_name = "Сам БОСС Crazy Taxi" if is_boss_taking else driver_info[0]
    await bot.send_message(client_id, f"🚕 <b>ВОДИТЕЛЬ ЕДЕТ!</b>\n{drv_name} ({driver_info[1]})\nТел: {order['phone']}!")

@dp.callback_query(F.data.startswith("finish_taxi_"))
async def driver_finish_taxi(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return

    price_int = extract_price(order['price'])
    add_commission(driver_id, price_int)
    log_order(driver_id, "Обычное такси", price_int) 
    
    await callback.message.edit_text("✅ Поездка завершена!")
    await bot.send_message(client_id, "🏁 Поездка завершена. Спасибо!")
    del active_orders[client_id]

# ==========================================
# 🤝 ТОРГ (COUNTER-OFFER)
# ==========================================
@dp.callback_query(F.data.startswith("counter_"))
async def start_counter_offer(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    order_type, client_id = parts[1], int(parts[2])
    await state.update_data(target_client_id=client_id, order_type=order_type)
    await callback.message.answer("✍️ Напиши цену и условия (напр: '2500, через 5 мин'):")
    await state.set_state(DriverCounterOffer.waiting_for_offer)
    await callback.answer()

@dp.message(DriverCounterOffer.waiting_for_offer)
async def send_counter_offer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    client_id, order_type, offer_text = data.get('target_client_id'), data.get('order_type'), message.text
    driver_id = message.from_user.id
    
    order = active_orders.get(client_id)
    if not order or order["status"] != "pending":
        await message.answer("❌ Заказ не актуален.")
        await state.clear()
        return
        
    if "driver_offers" not in order: order["driver_offers"] = {}
    order["driver_offers"][driver_id] = offer_text
    
    acc_data = f"acc_coff_{order_type}_{client_id}_{driver_id}"
    rej_data = f"rej_coff_{client_id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Согласен", callback_data=acc_data)], [InlineKeyboardButton(text="❌ Отказ", callback_data=rej_data)]])
    
    drv_label = "БОСС" if driver_id == BOSS_ID else "Водитель"
    await bot.send_message(client_id, f"⚡️ <b>{drv_label} предлагает условия:</b>\n\n{offer_text}", reply_markup=kb)
    await message.answer("✅ Отправлено клиенту!")
    await state.clear()

@dp.callback_query(F.data.startswith("acc_coff_"))
async def client_accepts_offer(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    order_type, client_id, driver_id = parts[2], int(parts[3]), int(parts[4])
    
    order = active_orders.get(client_id)
    if not order or order["status"] != "pending":
        await callback.answer("Не актуально.", show_alert=True)
        return
        
    order["status"] = "accepted"
    order["driver_id"] = driver_id
    if "driver_offers" in order and driver_id in order["driver_offers"]:
        order["price"] = order["driver_offers"][driver_id] 
        
    await update_boss_monitor(client_id, driver_id)
        
    driver_info = get_driver_info(driver_id)
    drv_label = "БОСС" if driver_id == BOSS_ID else driver_info[0]
    
    if order_type == "crazy": 
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Я ОПЛАТИЛ", callback_data=f"cpay_done_{client_id}")]])
        await callback.message.edit_text(f"🚕 <b>ДОГОВОРИЛИСЬ!</b>\nИсполнитель: {drv_label}\n💳 <b>Переведи сумму на:</b>\n<code>{driver_info[2]}</code>", reply_markup=pay_kb)
        await bot.send_message(driver_id, "✅ Клиент согласился на условия! Жди оплату.")
    else: 
        finish_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Завершить", callback_data=f"finish_taxi_{client_id}")]])
        await bot.send_message(driver_id, f"✅ Клиент согласился на условия!\nТел: <b>{order['phone']}</b>", reply_markup=finish_kb)
        await callback.message.edit_text(f"🚕 <b>ВОДИТЕЛЬ ЕДЕТ!</b>\n{drv_label} свяжется по номеру {order['phone']}!")

@dp.callback_query(F.data.startswith("rej_coff_"))
async def client_rejects_offer(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Ты отказался. Ждем других.")

# ==========================================
# 🪪 КАБИНЕТ И АДМИНКА
# ==========================================
@dp.message(Command("cab"))
async def cmd_driver_cabinet(message: types.Message):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status, balance FROM drivers WHERE user_id=?", (message.from_user.id,))
    res = cursor.fetchone()
    conn.close()
    
    if not res or res[0] != 'active':
        await message.answer("❌ Доступно только одобренным водителям.")
        return
    
    balance_text = ""
    hist_text = ""
    if message.from_user.id != BOSS_ID:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(price) FROM order_history WHERE driver_id=?", (message.from_user.id,))
        hist = cursor.fetchone()
        conn.close()
        completed_count = hist[0] or 0
        total_earned = hist[1] or 0
        balance_text = f"Твой долг по комиссии: <b>{res[1]}₽</b>\n"
        hist_text = f"Успешно выполнено: <b>{completed_count}</b> заказов\nЗаработано всего: <b>{total_earned}₽</b>\n"

    my_active = []
    for cid, order in active_orders.items():
        if order.get("driver_id") == message.from_user.id and order.get("status") == "accepted":
            name = order.get("service", {}).get("name") if order["type"] == "crazy" else f"Такси ({order['to']})"
            my_active.append(f"🔹 {name} | 💰 {order['price']}")
    active_text = "\n".join(my_active) if my_active else "<i>Пусто.</i>"
    await message.answer(f"🪪 <b>КАБИНЕТ ВОДИТЕЛЯ</b>\n\n{hist_text}{balance_text}🔥 <b>Заказы в работе:</b>\n{active_text}")

@dp.message(Command("driver"))
async def cmd_driver_register(message: types.Message, state: FSMContext):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM drivers WHERE user_id=?", (message.from_user.id,))
    res = cursor.fetchone()
    conn.close()
    if res:
        if res[0] == 'active': await message.answer("✅ Кабинет: /cab")
        return
    await message.answer("🚕 <b>РЕГИСТРАЦИЯ ВОДИТЕЛЯ</b>\nНапиши машину, цвет, номер:")
    await state.set_state(DriverRegistration.waiting_for_car)

@dp.message(DriverRegistration.waiting_for_car)
async def process_car_info(message: types.Message, state: FSMContext):
    await state.update_data(car_info=message.text)
    await message.answer("💳 Напиши <b>реквизиты</b>:")
    await state.set_state(DriverRegistration.waiting_for_payment_info)

@dp.message(DriverRegistration.waiting_for_payment_info)
async def process_payment_info(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO drivers (user_id, username, car_info, payment_info, status) VALUES (?, ?, ?, ?, 'pending')", (message.from_user.id, message.from_user.username, user_data['car_info'], message.text))
    conn.commit()
    conn.close()
    await state.clear()
    await message.answer("📝 Заявка отправлена.")
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Одобрить", callback_data=f"adm_approve_{message.from_user.id}")]])
    await bot.send_message(BOSS_ID, f"🚨 <b>ЗАЯВКА</b>\n@{message.from_user.username}\n{user_data['car_info']}", reply_markup=admin_kb)

@dp.callback_query(F.data.startswith("adm_approve_"))
async def admin_approve_driver(callback: types.CallbackQuery):
    if callback.from_user.id != BOSS_ID: return
    d_id = int(callback.data.split("_")[2])
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE drivers SET status='active' WHERE user_id=?", (d_id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("✅ Одобрен.")
    try: await bot.send_message(d_id, "🎉 Одобрен! /cab")
    except: pass

@dp.callback_query(F.data.startswith("adm_reject_"))
async def admin_reject_driver(callback: types.CallbackQuery):
    if callback.from_user.id != BOSS_ID: return
    d_id = int(callback.data.split("_")[2])
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM drivers WHERE user_id=?", (d_id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("❌ Отклонен.")

# ====================
# 🛠 УПРАВЛЕНИЕ ВОДИТЕЛЯМИ (АДМИН)
# ====================
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != BOSS_ID: return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, status, balance FROM drivers")
    all_drivers = cursor.fetchall()
    conn.close()
    text = "👑 <b>УПРАВЛЕНИЕ</b> 👑\n\n"
    for d in all_drivers:
        status_emoji = "🟢" if d[2] == 'active' else "🔴"
        text += f"{status_emoji} <b>{d[1]}</b> (ID: {d[0]})\nДолг: {d[3]}₽\n👉 /edit_{d[0]}\n---\n"
    await message.answer(text)

@dp.message(F.text.startswith("/edit_"))
async def edit_driver_menu(message: types.Message):
    if message.from_user.id != BOSS_ID: return
    d_id = int(message.text.split("_")[1])
    info = get_driver_info(d_id)
    if not info:
        await message.answer("❌ Не найден")
        return
        
    status_icon = "🔓" if info[4] == 'active' else "🔒"
    block_action = "block" if info[4] == 'active' else "unblock"
    block_text = "🔒 Заблочить" if info[4] == 'active' else "🔓 Разблочить"
        
    text = f"✏️ <b>РЕДАКТОР: {info[0]}</b>\n\nСтатус: {status_icon} {info[4]}\n🚗 Авто: {info[1]}\n💳 Реквизиты: {info[2]}\n💰 Баланс: {info[3]}₽"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 Изм. Авто", callback_data=f"edt_car_{d_id}"), InlineKeyboardButton(text="💳 Изм. Рекв.", callback_data=f"edt_pay_{d_id}")],
        [InlineKeyboardButton(text="💰 Изм. Баланс", callback_data=f"edt_bal_{d_id}")],
        [InlineKeyboardButton(text=block_text, callback_data=f"adm_act_{block_action}_{d_id}")],
        [InlineKeyboardButton(text="💸 Отправить счет", callback_data=f"adm_act_sendbill_{d_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="edt_back")]
    ])
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("edt_"))
async def edit_driver_cb(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "edt_back":
        await callback.message.delete()
        return
    parts = callback.data.split("_")
    field_code, d_id = parts[1], int(parts[2])
    field_map = {"car": "car_info", "pay": "payment_info", "bal": "balance"}
    await state.update_data(edit_driver_id=d_id, edit_field=field_map[field_code])
    await callback.message.answer(f"✍️ Введи новое значение:")
    await state.set_state(AdminEditDriver.waiting_for_new_value)
    await callback.answer()

@dp.message(AdminEditDriver.waiting_for_new_value)
async def process_new_driver_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    d_id, field = data['edit_driver_id'], data['edit_field']
    new_val = message.text
    if field == "balance":
        try: new_val = int(new_val)
        except: 
            await message.answer("❌ Только число.")
            return
    update_driver_field(d_id, field, new_val)
    await message.answer(f"✅ Обновлено! /edit_{d_id}")
    await state.clear()

@dp.callback_query(F.data.startswith("adm_act_"))
async def admin_driver_actions(callback: types.CallbackQuery):
    if callback.from_user.id != BOSS_ID: return
    parts = callback.data.split("_")
    action, d_id = parts[2], int(parts[3])
    
    if action == "block":
        update_driver_field(d_id, "status", "blocked")
        await callback.message.edit_text(f"🔒 Водитель {d_id} заблокирован.")
        try: await bot.send_message(d_id, "❌ Твой аккаунт заблокирован Боссом.")
        except: pass
    elif action == "unblock":
        update_driver_field(d_id, "status", "active")
        await callback.message.edit_text(f"🔓 Водитель {d_id} разблокирован.")
        try: await bot.send_message(d_id, "✅ Твой аккаунт снова активен!")
        except: pass
    elif action == "sendbill":
        info = get_driver_info(d_id)
        if info[3] <= 0:
            await callback.answer("У него нет долгов!", show_alert=True)
            return
        await callback.answer("Счет отправлен!")
        try: await bot.send_message(d_id, f"⚠️ <b>ОПЛАТИ ДОЛГ!</b>\nСумма: <b>{info[3]}₽</b>\nРеквизиты Босса: Яндекс Банк +79012723729")
        except: pass

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
