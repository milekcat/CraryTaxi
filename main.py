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

logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("API_TOKEN")
BOSS_ID = os.getenv("DRIVER_ID") # Твой ID как владельца сети

if not API_TOKEN or not BOSS_ID:
    logging.error("ВНИМАНИЕ: API_TOKEN или DRIVER_ID не найдены!")

BOSS_ID = int(BOSS_ID)
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

active_orders = {} # Память для текущих заказов клиентов

# ==========================================
# 🗄️ БАЗА ДАННЫХ И ИСТОРИЯ ЗАКАЗОВ
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
    # Таблица для истории заказов (для личного кабинета)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id INTEGER,
            service_name TEXT,
            price INTEGER
        )
    """)
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
    cursor.execute("SELECT username, car_info, payment_info, balance FROM drivers WHERE user_id=?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res

def extract_price(text):
    """Вытаскивает только числа из строки (например из '500 руб' сделает 500)"""
    nums = re.findall(r'\d+', str(text))
    return int("".join(nums)) if nums else 0

def log_order(driver_id, service_name, price):
    """Записывает выполненный заказ в историю"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO order_history (driver_id, service_name, price) VALUES (?, ?, ?)", (driver_id, service_name, price))
    conn.commit()
    conn.close()

def add_commission(driver_id, amount):
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

# --- БАЗА УСЛУГ (РАСШИРЕННАЯ) ---
CRAZY_SERVICES = {
    "candy": {"name": "🍬 Конфетка", "price": 0, "desc": "Водитель торжественно вручит вам вкусную конфетку."},
    "napkin": {"name": "🧻 Салфетка", "price": 0, "desc": "Влажная салфетка, чтобы вытереть слезы счастья."},
    "joke": {"name": "🎭 Анекдот", "price": 50, "desc": "Анекдот из золотой коллекции."},
    "poem": {"name": "📜 Стих", "price": 100, "desc": "Прочту стихотворение с выражением."},
    "sleep": {"name": "🛌 Сон под шепот ям", "price": 150, "desc": "Аккуратная езда, водитель молчит."},
    "tale": {"name": "📖 Сказка на ночь", "price": 300, "desc": "Захватывающая история из жизни таксиста."},
    "granny": {"name": "👵 Бабушка-ворчунья", "price": 800, "desc": "Всю дорогу буду бубнить."},
    "spy": {"name": "🕵️‍♂️ Шпион", "price": 2000, "desc": "Едем за 'той машиной'. Водитель в черных очках."},
    "karaoke": {"name": "🎤 Караоке-баттл", "price": 5000, "desc": "Поем во весь голос хиты 90-х."},
    "dance": {"name": "🕺 Танцы на светофоре", "price": 15000, "desc": "Красный свет? Я выхожу и танцую!"},
    "kidnap": {"name": "🎭 Похищение", "price": 30000, "desc": "Везут пить чай на природу (по сценарию)."},
    "tarzan": {"name": "🦍 Тарзан-шоу", "price": 50000, "desc": "Кричу и бью себя в грудь. Максимальный кринж!"},
    "burn": {"name": "🔥 Сжечь машину", "price": 1000000, "desc": "Ты даешь лям, я даю канистру."}
}

class OrderRide(StatesGroup):
    waiting_for_from = State()
    waiting_for_to = State()
    waiting_for_phone = State() # <-- НОВЫЙ ШАГ (ТЕЛЕФОН)
    waiting_for_price = State()

class CustomIdea(StatesGroup):
    waiting_for_idea = State()

class DriverRegistration(StatesGroup):
    waiting_for_car = State()
    waiting_for_payment_info = State()

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
# 🛑 СТАРТ И ЖЕСТКИЙ КОНТРАКТ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    disclaimer_text = (
        "⚠️ <b>ОФИЦИАЛЬНОЕ ПРЕДУПРЕЖДЕНИЕ</b> ⚠️\n\n"
        "ВНИМАНИЕ! Вы пытаетесь воспользоваться услугами <b>Crazy Taxi</b>.\n"
        "Салон этого автомобиля является юридически неприкосновенной зоной <b>Арт-перформанса</b>.\n\n"
        "<b>Нажимая кнопку ниже, вы подтверждаете, что:</b>\n"
        "1. Любая дичь, происходящая внутри, классифицируется как 'современное искусство'.\n"
        "2. Вы заранее отказываетесь от любых судебных исков и претензий.\n"
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
    await callback.message.edit_text("🔥 <b>ДОБРО ПОЖАЛОВАТЬ В CRAZY TAXI!</b> 🔥\nКонтракт подписан цифровой подписью. Двери заблокированы.")
    await callback.message.answer("Выбирай действие в меню ниже 👇", reply_markup=main_kb)

@dp.callback_query(F.data == "decline_tos")
async def tos_declined(callback: types.CallbackQuery):
    await callback.message.edit_text("🚶‍♂️ Очень жаль! Водитель разблокировал двери. Удачной пешей прогулки!")

async def check_tos(message: types.Message) -> bool:
    if not is_client_accepted(message.from_user.id):
        await message.answer("🛑 <b>ОШИБКА ДОСТУПА!</b>\nСначала нужно подписать контракт о снятии ответственности. Нажми /start")
        return False
    return True

@dp.message(F.text == "⚖️ Вызвать адвоката / Правила")
async def lawyer_menu(message: types.Message):
    if not await check_tos(message): return
    lawyer_text = "⚖️ <b>НАШ НЕПОБЕДИМЫЙ АДВОКАТ</b> ⚖️\n\nЧитать права здесь будет только он, и то на латыни.\n<i>Все еще хочешь с ним связаться?</i>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚨 СВЯЗАТЬСЯ С АДВОКАТОМ 🚨", callback_data="call_lawyer")]])
    await message.answer(lawyer_text, reply_markup=kb)

@dp.callback_query(F.data == "call_lawyer")
async def alert_lawyer(callback: types.CallbackQuery):
    await callback.answer("🚨 Адвокат занят подачей иска на твою скуку. Договаривайся с водителем!", show_alert=True)
    drivers = get_active_drivers()
    for d_id in drivers:
        try: await bot.send_message(d_id, f"⚖️ Клиент @{callback.from_user.username} пытается вызвать адвоката!")
        except: pass

async def broadcast_order_to_drivers(client_id, order_text, reply_markup):
    search_msg = await bot.send_message(client_id, "📡 <i>Радары включены. Сканируем улицы в поисках безумцев...</i>")
    await asyncio.sleep(2.5) 
    drivers = get_active_drivers()
    if not drivers:
        await search_msg.edit_text("😔 <b>Все машины сейчас заняты.</b>\nПопробуй повторить вызов через пару минут!")
        if client_id in active_orders: del active_orders[client_id]
        return
        
    await search_msg.edit_text("⏳ <b>Сигнал передан всем водителям на линии!</b>\nЖдем, кто из них успеет забрать заказ первым...")
    
    async def send_to_driver(d_id):
        try:
            await bot.send_message(chat_id=d_id, text=order_text, reply_markup=reply_markup)
            return True
        except: return False

    tasks = [send_to_driver(d_id) for d_id in drivers]
    await asyncio.gather(*tasks)

# ==========================================
# 📜 CRAZY ХАОС-МЕНЮ
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
    await message.answer("🔥 <b>CRAZY DRIVER'S CHAOS MENU</b> 🔥\n\nВыбирай приключение:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("csel_"))
async def process_crazy_selection(callback: types.CallbackQuery):
    service_key = callback.data.split("_")[1]
    service = CRAZY_SERVICES[service_key]
    client_id = callback.from_user.id
    
    active_orders[client_id] = {"type": "crazy", "service": service, "status": "pending", "price": service["price"]}
    price_text = "БЕСПЛАТНО" if service["price"] == 0 else f"{service['price']}₽"
    
    await callback.message.edit_text(f"🎪 <b>ВЫБРАНА УСЛУГА:</b> {service['name']}\n📝 <b>Описание:</b> {service['desc']}\n💰 <b>Стоимость:</b> {price_text}")
    driver_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ЗАБРАТЬ ЗАКАЗ", callback_data=f"take_crazy_{client_id}")]])
    text = f"🚨 <b>ХАОС-ЗАКАЗ!</b> 🚨\nКлиент: @{callback.from_user.username}\nУслуга: <b>{service['name']}</b> ({price_text})\nКто первый?!"
    await broadcast_order_to_drivers(client_id, text, driver_kb)

@dp.callback_query(F.data.startswith("take_crazy_"))
async def driver_takes_crazy(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)

    if not order or order["status"] != "pending":
        await callback.answer("Упс! Этот заказ уже забрал другой водитель 🏎💨", show_alert=True)
        await callback.message.delete()
        return

    order["status"] = "accepted"
    order["driver_id"] = driver_id
    driver_info = get_driver_info(driver_id)
    
    await callback.message.edit_text(f"✅ Ты забрал заказ: {order['service']['name']}!")
    
    if order['price'] == 0:
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ЖДУ СЮРПРИЗ!", callback_data=f"cpay_done_{client_id}")]])
        client_text = f"🚕 <b>ВОДИТЕЛЬ НАЙДЕН!</b>\nК тебе приедет: {driver_info[0]} ({driver_info[1]})\n\n🎁 <b>Эта услуга бесплатна!</b>\nЖми кнопку ниже, чтобы начать!"
    else:
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Я ОПЛАТИЛ", callback_data=f"cpay_done_{client_id}")]])
        client_text = f"🚕 <b>ВОДИТЕЛЬ НАЙДЕН!</b>\nК тебе приедет: {driver_info[0]} ({driver_info[1]})\n\n💳 <b>Переведи {order['price']}₽ на реквизиты:</b>\n<code>{driver_info[2]}</code>\nЖми кнопку ниже после перевода!"
        
    await bot.send_message(client_id, client_text, reply_markup=pay_kb)

@dp.callback_query(F.data.startswith("cpay_done_"))
async def client_paid_crazy(callback: types.CallbackQuery):
    client_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ВЫПОЛНИЛ (Завершить)", callback_data=f"confirm_pay_{client_id}")]])
    if order['price'] == 0:
        await callback.message.edit_text("⏳ Водитель готовится к перформансу...")
        await bot.send_message(order["driver_id"], f"🎁 Клиент @{callback.from_user.username} ждет: <b>{order['service']['name']}</b>!\nСделай это и нажми кнопку.", reply_markup=kb)
    else:
        await callback.message.edit_text("⏳ Проверяем поступление средств...")
        await bot.send_message(order["driver_id"], f"💸 Клиент @{callback.from_user.username} нажал 'Оплатил' за {order['service']['name']}.\nПроверь баланс {order['price']}₽ и заверши заказ!", reply_markup=kb)

@dp.callback_query(F.data.startswith("confirm_pay_"))
async def driver_confirms_pay(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return
    
    add_commission(driver_id, order['price'])
    log_order(driver_id, order['service']['name'], order['price']) # Пишем в историю
    
    await callback.message.edit_text("✅ Заказ успешно выполнен и занесен в твою историю (/cab)!")
    await bot.send_message(client_id, "🎉 Водитель подтвердил выполнение! Надеюсь, тебе понравилось!")
    del active_orders[client_id]

# ==========================================
# 🚕 ОБЫЧНОЕ ТАКСИ (ТОРГ И ТЕЛЕФОН)
# ==========================================
@dp.message(F.text == "🚕 Заказать такси (Торг)")
async def start_ride_order(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    await message.answer("📍 <b>Откуда тебя забрать?</b> Напиши адрес:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(OrderRide.waiting_for_from)

@dp.message(OrderRide.waiting_for_from)
async def process_from_address(message: types.Message, state: FSMContext):
    await state.update_data(from_address=message.text)
    await message.answer("🏁 <b>Куда мчим?</b> Напиши адрес:")
    await state.set_state(OrderRide.waiting_for_to)

@dp.message(OrderRide.waiting_for_to)
async def process_to_address(message: types.Message, state: FSMContext):
    await state.update_data(to_address=message.text)
    await message.answer("📞 <b>Напиши свой номер телефона</b> для связи с водителем:")
    await state.set_state(OrderRide.waiting_for_phone)

@dp.message(OrderRide.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("💰 <b>Сколько готов заплатить?</b> (Сумма в рублях):")
    await state.set_state(OrderRide.waiting_for_price)

@dp.message(OrderRide.waiting_for_price)
async def process_price(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    client_id = message.from_user.id
    
    active_orders[client_id] = {
        "type": "taxi", "status": "pending", "price": message.text,
        "from": user_data['from_address'], "to": user_data['to_address'], "phone": user_data['phone']
    }

    await message.answer("✅ <b>Параметры поездки приняты!</b>", reply_markup=main_kb)
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Забрать поездку", callback_data=f"take_taxi_{client_id}")]])
    # Водителю пока не показываем телефон, пока он не примет заказ
    text = f"🚕 <b>ЗАКАЗ ТАКСИ</b> 🚕\n\n📍 Откуда: {user_data['from_address']}\n🏁 Куда: {user_data['to_address']}\n💰 Предлагает: <b>{message.text}₽</b>"
    await broadcast_order_to_drivers(client_id, text, kb)

@dp.callback_query(F.data.startswith("take_taxi_"))
async def driver_takes_taxi(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)

    if not order or order["status"] != "pending":
        await callback.answer("Упс! Заказ уже забрали 🏎💨", show_alert=True)
        await callback.message.delete()
        return

    order["status"] = "accepted"
    order["driver_id"] = driver_id
    driver_info = get_driver_info(driver_id)
    
    finish_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Завершить поездку", callback_data=f"finish_taxi_{client_id}")]])
    
    # Теперь водитель видит телефон
    await callback.message.edit_text(f"✅ Ты забрал поездку!\nМаршрут: {order['from']} -> {order['to']}\n📞 Тел. клиента: <b>{order['phone']}</b>", reply_markup=finish_kb)
    await bot.send_message(client_id, f"🚕 <b>ВОДИТЕЛЬ НАЙДЕН!</b>\nК тебе едет: {driver_info[0]} ({driver_info[1]})\nВодитель свяжется с тобой по номеру {order['phone']}!")

@dp.callback_query(F.data.startswith("finish_taxi_"))
async def driver_finish_taxi(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return

    price_int = extract_price(order['price'])
    add_commission(driver_id, price_int)
    log_order(driver_id, "Обычное такси", price_int) # Пишем в историю
    
    await callback.message.edit_text("✅ Поездка успешно завершена! Данные добавлены в твой кабинет.")
    await bot.send_message(client_id, "🏁 Поездка завершена. Спасибо, что выбираете Crazy Taxi!")
    del active_orders[client_id]

# ==========================================
# 🪪 ЛИЧНЫЙ КАБИНЕТ ВОДИТЕЛЯ (/cab)
# ==========================================
@dp.message(Command("cab"))
async def cmd_driver_cabinet(message: types.Message):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status, balance FROM drivers WHERE user_id=?", (message.from_user.id,))
    res = cursor.fetchone()
    
    if not res or res[0] != 'active':
        await message.answer("❌ Этот раздел доступен только для одобренных Боссом водителей.")
        conn.close()
        return
        
    status, balance = res
    cursor.execute("SELECT COUNT(*), SUM(price) FROM order_history WHERE driver_id=?", (message.from_user.id,))
    hist = cursor.fetchone()
    conn.close()

    completed_count = hist[0] or 0
    total_earned = hist[1] or 0

    # Собираем активные заказы из оперативной памяти
    my_active = []
    for cid, order in active_orders.items():
        if order.get("driver_id") == message.from_user.id and order.get("status") == "accepted":
            name = order.get("service", {}).get("name") if order["type"] == "crazy" else f"Такси ({order['from']} -> {order['to']})"
            price = order['price'] if order["type"] == "crazy" else order['price']
            my_active.append(f"🔹 {name} | 💰 {price}₽")

    active_text = "\n".join(my_active) if my_active else "<i>Пусто. Жди заказов!</i>"

    text = (
        f"🪪 <b>ЛИЧНЫЙ КАБИНЕТ ВОДИТЕЛЯ</b>\n\n"
        f"📊 <b>Твоя статистика:</b>\n"
        f"Успешно выполнено: <b>{completed_count}</b> заказов\n"
        f"Заработано всего: <b>{total_earned}₽</b>\n"
        f"Твой долг по комиссии: <b>{balance}₽</b>\n\n"
        f"🔥 <b>Активные заказы в работе:</b>\n{active_text}"
    )
    await message.answer(text)

# ==========================================
# 💡 СВОЙ ВАРИАНТ
# ==========================================
@dp.message(F.text == "💡 Свой вариант (Предложить идею)")
async def custom_idea_start(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    await message.answer("У тебя есть безумная идея? Опиши её здесь, а водители предложат свою цену!", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(CustomIdea.waiting_for_idea)

@dp.message(CustomIdea.waiting_for_idea)
async def process_custom_idea(message: types.Message, state: FSMContext):
    idea = message.text
    client_id = message.from_user.id
    await message.answer("✅ <b>Идея зафиксирована!</b>", reply_markup=main_kb)
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💰 Предложить цену", callback_data=f"idea_take_{client_id}")]])
    await broadcast_order_to_drivers(client_id, f"💡 <b>НОВАЯ ИДЕЯ ОТ КЛИЕНТА</b> 💡\n\n👤 @{message.from_user.username}\n📝 Суть: {idea}", kb)

@dp.callback_query(F.data.startswith("idea_take_"))
async def driver_takes_idea(callback: types.CallbackQuery):
    await callback.answer("Свяжись с клиентом через личные сообщения для обсуждения деталей!", show_alert=True)

# ==========================================
# 🚦 РЕГИСТРАЦИЯ ВОДИТЕЛЕЙ И АДМИНКА
# ==========================================
@dp.message(Command("driver"))
async def cmd_driver_register(message: types.Message, state: FSMContext):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM drivers WHERE user_id=?", (message.from_user.id,))
    res = cursor.fetchone()
    conn.close()
    
    if res:
        if res[0] == 'active': await message.answer("✅ Ты уже в деле! Твой кабинет: /cab")
        elif res[0] == 'pending': await message.answer("⏳ Твоя заявка на рассмотрении у Босса.")
        elif res[0] == 'blocked': await message.answer("❌ Твой аккаунт заблокирован.")
        return

    await message.answer("🚕 <b>РЕГИСТРАЦИЯ ВОДИТЕЛЯ</b>\nНапиши марку своей машины, цвет и госномер:")
    await state.set_state(DriverRegistration.waiting_for_car)

@dp.message(DriverRegistration.waiting_for_car)
async def process_car_info(message: types.Message, state: FSMContext):
    await state.update_data(car_info=message.text)
    await message.answer("💳 Напиши свои <b>реквизиты для получения оплат</b>:")
    await state.set_state(DriverRegistration.waiting_for_payment_info)

@dp.message(DriverRegistration.waiting_for_payment_info)
async def process_payment_info(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    user_id = message.from_user.id
    username = message.from_user.username or "Без юзернейма"

    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO drivers (user_id, username, car_info, payment_info, status) VALUES (?, ?, ?, ?, 'pending')", (user_id, username, user_data['car_info'], message.text))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer("📝 Заявка отправлена Боссу! Ожидай одобрения.")

    admin_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Одобрить", callback_data=f"adm_approve_{user_id}")], [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_reject_{user_id}")]])
    await bot.send_message(BOSS_ID, f"🚨 <b>НОВАЯ ЗАЯВКА</b> 🚨\n👤 @{username}\n🚗 {user_data['car_info']}\n💳 {message.text}", reply_markup=admin_kb)

@dp.callback_query(F.data.startswith("adm_approve_"))
async def admin_approve_driver(callback: types.CallbackQuery):
    if callback.from_user.id != BOSS_ID: return
    d_id = int(callback.data.split("_")[2])
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE drivers SET status='active' WHERE user_id=?", (d_id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text(f"✅ Водитель {d_id} <b>ОДОБРЕН</b>.")
    try: await bot.send_message(d_id, "🎉 <b>ТВОЯ ЗАЯВКА ОДОБРЕНА!</b>\nТеперь ты получаешь заказы. Твой личный кабинет доступен по команде: /cab")
    except: pass

@dp.callback_query(F.data.startswith("adm_reject_"))
async def admin_reject_driver(callback: types.CallbackQuery):
    if callback.from_user.id != BOSS_ID: return
    d_id = int(callback.data.split("_")[2])
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM drivers WHERE user_id=?", (d_id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text(f"❌ Водитель {d_id} <b>ОТКЛОНЕН</b>.")

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != BOSS_ID: return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, status, balance FROM drivers")
    all_drivers = cursor.fetchall()
    conn.close()

    text = "👑 <b>УПРАВЛЕНИЕ ФРАНШИЗОЙ</b> 👑\n\n"
    for d in all_drivers:
        status_emoji = "🟢" if d[2] == 'active' else "🔴" if d[2] == 'blocked' else "🟡"
        text += f"{status_emoji} <b>{d[1]}</b> (ID: {d[0]})\nДолг: <b>{d[3]}₽</b> | Статус: {d[2]}\nБлок: /block_{d[0]} | Анблок: /unblock_{d[0]}\n---\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Запросить оплату долгов", callback_data="adm_invoice_all")]])
    await message.answer(text, reply_markup=kb)

@dp.message(F.text.startswith("/block_"))
async def block_driver(message: types.Message):
    if message.from_user.id != BOSS_ID: return
    d_id = int(message.text.split("_")[1])
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE drivers SET status='blocked' WHERE user_id=?", (d_id,))
    conn.commit()
    conn.close()
    await message.answer(f"✅ Водитель {d_id} заблокирован.")

@dp.message(F.text.startswith("/unblock_"))
async def unblock_driver(message: types.Message):
    if message.from_user.id != BOSS_ID: return
    d_id = int(message.text.split("_")[1])
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE drivers SET status='active', balance=0 WHERE user_id=?", (d_id,))
    conn.commit()
    conn.close()
    await message.answer(f"✅ Водитель {d_id} разблокирован. Долг обнулен!")

@dp.callback_query(F.data == "adm_invoice_all")
async def invoice_all(callback: types.CallbackQuery):
    if callback.from_user.id != BOSS_ID: return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, balance FROM drivers WHERE balance > 0 AND status='active'")
    debtors = cursor.fetchall()
    conn.close()
    
    for d_id, debt in debtors:
        try: await bot.send_message(d_id, f"⚠️ <b>ВРЕМЯ ПЛАТИТЬ ПО СЧЕТАМ</b> ⚠️\nТвой долг по комиссии: <b>{debt}₽</b>.\nПереведи на реквизиты Босса (Яндекс Банк: +79012723729 Андрей И.), иначе отключим от сети!")
        except: pass
    await callback.answer("Счета разосланы должникам!", show_alert=True)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
