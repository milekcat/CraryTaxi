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
BOSS_ID = os.getenv("DRIVER_ID") 

if not API_TOKEN or not BOSS_ID:
    logging.error("ВНИМАНИЕ: API_TOKEN или DRIVER_ID не найдены!")

BOSS_ID = int(BOSS_ID)
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

active_orders = {} 
# Словарь привязки: {client_id: driver_id} (кто с кем едет)
client_driver_link = {}

# ==========================================
# 🗄️ БАЗА ДАННЫХ (НОВАЯ СТРУКТУРА)
# ==========================================
DB_PATH = "/data/taxi_db.sqlite" if os.path.exists("/data") else "taxi_db.sqlite"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Добавлено поле access_code (Ключ водителя)
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
    cursor.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id INTEGER,
            service_name TEXT,
            price INTEGER
        )
    """)
    
    # АВТО-РЕГИСТРАЦИЯ БОССА (Код по умолчанию: BOSS)
    cursor.execute("SELECT 1 FROM drivers WHERE user_id = ?", (BOSS_ID,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO drivers (user_id, username, car_info, payment_info, access_code, status) VALUES (?, ?, ?, ?, ?, 'active')",
            (BOSS_ID, "BOSS_NETWORK", "BOSS (Black Car)", "Яндекс Банк +79012723729", "BOSS")
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

def get_driver_by_code(code):
    """Ищет водителя по секретному ключу"""
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

# --- БАЗА УСЛУГ ---
CRAZY_SERVICES = {
    "candy": {"name": "🍬 Конфетка", "price": 0, "desc": "Водитель торжественно вручит вам вкусную конфетку."},
    "joke": {"name": "🎭 Анекдот", "price": 50, "desc": "Анекдот из золотой коллекции."},
    "tale": {"name": "📖 Сказка на ночь", "price": 300, "desc": "Захватывающая история из жизни таксиста."},
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
    waiting_for_code = State() # Новый шаг: ввод кода

class UnlockMenu(StatesGroup):
    waiting_for_key = State()

class AdminEditDriver(StatesGroup):
    waiting_for_new_value = State()

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
# 🛑 СТАРТ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("⚠️ <b>CRAZY TAXI: ЗОНА АРТ-ПЕРФОРМАНСА</b>\n\nПодпиши контракт кровью (цифровой), чтобы продолжить.", reply_markup=tos_kb)

@dp.callback_query(F.data == "accept_tos")
async def tos_accepted(callback: types.CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (callback.from_user.id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("🔥 <b>ДОСТУП РАЗРЕШЕН!</b>")
    await callback.message.answer("Выбирай действие в меню ниже 👇", reply_markup=main_kb)

@dp.callback_query(F.data == "decline_tos")
async def tos_declined(callback: types.CallbackQuery):
    await callback.message.edit_text("🚶‍♂️ Выход там.")

async def check_tos(message: types.Message) -> bool:
    if not is_client_accepted(message.from_user.id):
        await message.answer("🛑 Сначала нажми /start и прими правила.")
        return False
    return True

# ==========================================
# 🔐 СИСТЕМА КЛЮЧЕЙ (ПРИВЯЗКА К ВОДИТЕЛЮ)
# ==========================================
@dp.message(F.text == "🔐 Ввести КЛЮЧ услуги")
async def ask_for_key(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    await message.answer("🕵️‍♂️ <b>Введи секретный код водителя</b> (спроси у него):\n\nЭто разблокирует доступ к меню услуг именно в этой машине.")
    await state.set_state(UnlockMenu.waiting_for_key)

@dp.message(UnlockMenu.waiting_for_key)
async def process_key(message: types.Message, state: FSMContext):
    code = message.text.strip()
    driver = get_driver_by_code(code)
    
    if driver:
        driver_id, driver_name, car_info = driver
        # Привязываем клиента к этому водителю
        client_driver_link[message.from_user.id] = driver_id
        
        await message.answer(f"🔓 <b>ДОСТУП РАЗРЕШЕН!</b>\n\n🚘 Вы подключены к борту: <b>{car_info}</b>\n👤 Водитель: <b>@{driver_name}</b>\n\nТеперь раздел 'CRAZY ХАОС-МЕНЮ' отправляет заказы лично ему.", reply_markup=main_kb)
        await state.clear()
        
        # Уведомляем водителя
        try: await bot.send_message(driver_id, f"🔗 Клиент @{message.from_user.username} активировал твой ключ! Жди заказов.")
        except: pass
    else:
        await message.answer("❌ <b>Неверный ключ!</b> Спроси код у водителя еще раз или попробуй снова.")

# ==========================================
# 📜 CRAZY МЕНЮ (ТОЛЬКО ПО ПРИВЯЗКЕ)
# ==========================================
@dp.message(F.text == "📜 CRAZY ХАОС-МЕНЮ (В поездке)")
async def show_crazy_menu(message: types.Message):
    if not await check_tos(message): return
    
    # Проверка привязки
    if message.from_user.id not in client_driver_link:
        await message.answer("🔒 <b>МЕНЮ ЗАБЛОКИРОВАНО</b>\n\nВы еще не ввели ключ водителя. Нажмите кнопку <b>'🔐 Ввести КЛЮЧ услуги'</b> и введите код, который скажет водитель.", reply_markup=main_kb)
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
    await message.answer("🔥 <b>CRAZY МЕНЮ (ПРЯМОЙ ЗАКАЗ)</b> 🔥\nВыбирай, водитель ждет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("csel_"))
async def process_crazy_selection(callback: types.CallbackQuery):
    client_id = callback.from_user.id
    
    # Повторная проверка привязки (на случай перезагрузки)
    driver_id = client_driver_link.get(client_id)
    if not driver_id:
        await callback.answer("Связь с водителем потеряна. Введите ключ заново!", show_alert=True)
        return

    service_key = callback.data.split("_")[1]
    service = CRAZY_SERVICES[service_key]
    
    active_orders[client_id] = {"type": "crazy", "status": "direct_order", "price": str(service["price"]), "driver_id": driver_id, "service": service}
    price_text = "БЕСПЛАТНО" if service["price"] == 0 else f"{service['price']}₽"
    
    await callback.message.edit_text(f"🚀 <b>Заказ отправлен лично водителю!</b>\n🎪 Услуга: {service['name']}\n💰 {price_text}")
    
    # ОТПРАВЛЯЕМ НАПРЯМУЮ ВОДИТЕЛЮ (БЕЗ РАССЫЛКИ)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ И ВЫПОЛНИТЬ", callback_data=f"driver_direct_accept_{client_id}")]])
    await bot.send_message(driver_id, f"🔔 <b>ПЕРСОНАЛЬНЫЙ ЗАКАЗ (По ключу)</b>\n👤 Клиент здесь!\n🎭 Хочет: <b>{service['name']}</b>", reply_markup=kb)
    
    # Уведомляем Босса для контроля
    if driver_id != BOSS_ID:
        await bot.send_message(BOSS_ID, f"👀 <b>КОНТРОЛЬ:</b> @{callback.from_user.username} заказал {service['name']} у водителя {driver_id}")

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
        await bot.send_message(client_id, f"✅ Водитель принял заказ!\n🎁 Услуга бесплатная. Жми кнопку!", reply_markup=pay_kb)
    else:
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Я ОПЛАТИЛ", callback_data=f"cpay_done_{client_id}")]])
        await bot.send_message(client_id, f"✅ Водитель готов!\n💳 Переведи <b>{order['price']}</b> на: <code>{driver_info[2]}</code>", reply_markup=pay_kb)
    
    await callback.message.edit_text("✅ Ты принял заказ. Жди подтверждения клиента.")

# --- Логика оплаты Crazy (стандартная) ---
@dp.callback_query(F.data.startswith("cpay_done_"))
async def client_paid_crazy(callback: types.CallbackQuery):
    client_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ГОТОВО (Закрыть)", callback_data=f"confirm_pay_{client_id}")]])
    await callback.message.edit_text("⏳ Ждем подтверждения водителя...")
    await bot.send_message(order["driver_id"], f"💸 Клиент нажал кнопку (Оплатил/Ждет). Выполняй!", reply_markup=kb)

@dp.callback_query(F.data.startswith("confirm_pay_"))
async def driver_confirms_pay(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return
    
    price_int = extract_price(order['price'])
    add_commission(driver_id, price_int)
    log_order(driver_id, order['service']['name'], price_int)
    
    await callback.message.edit_text("✅ Заказ закрыт.")
    await bot.send_message(client_id, "🎉 Услуга выполнена! Спасибо за безумие.")
    del active_orders[client_id]

# ==========================================
# 🚕 ЗАКАЗ ТАКСИ (ОСТАЕТСЯ РАССЫЛКОЙ)
# ==========================================
# (Тут код без изменений: broadcast_order_to_drivers и т.д. для поиска машины)
async def broadcast_order_to_drivers(client_id, order_text, driver_kb, boss_kb):
    boss_msg = await bot.send_message(chat_id=BOSS_ID, text=f"🚨 <b>ПОИСК МАШИНЫ</b>\n{order_text}", reply_markup=boss_kb)
    if client_id in active_orders:
        active_orders[client_id]['boss_msg_id'] = boss_msg.message_id
        active_orders[client_id]['broadcasting_text'] = order_text

    search_msg = await bot.send_message(client_id, "📡 <i>Ищем водителей...</i>")
    await asyncio.sleep(2.0)
    
    drivers = get_active_drivers()
    drivers_to_broadcast = [d for d in drivers if d != BOSS_ID]
    
    if not drivers_to_broadcast:
        await search_msg.edit_text("😔 Нет свободных машин.")
        return
    await search_msg.edit_text("⏳ Запрос отправлен всем!")
    
    async def send_to_driver(d_id):
        try: await bot.send_message(chat_id=d_id, text=order_text, reply_markup=driver_kb)
        except: return False
    tasks = [send_to_driver(d_id) for d_id in drivers_to_broadcast]
    await asyncio.gather(*tasks)

# ... (Методы заказа такси OrderRide оставлены такими же, как в прошлом коде, они работают через broadcast) ...
# Чтобы не дублировать огромный кусок, я вставил логику broadcast выше. 
# ВНИМАНИЕ: Сюда нужно вставить блоки: @dp.message(F.text == "🚕 Заказать такси (Поиск)"), process_from_address и т.д.
# Для экономии места я пишу их сокращенно, но в полной версии они должны быть.

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
    active_orders[client_id] = {"type": "taxi", "status": "pending", "price": message.text, "from": user_data['from_address'], "to": user_data['to_address'], "phone": user_data['phone'], "driver_offers": {}}
    await message.answer("✅ Ищем...", reply_markup=main_kb)
    await state.clear()
    
    dkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Забрать", callback_data=f"take_taxi_{client_id}")]])
    bkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ БОСС ЗАБРАТЬ", callback_data=f"boss_take_taxi_{client_id}")]])
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
    await update_boss_monitor(client_id, driver_id)
    
    # АВТОМАТИЧЕСКАЯ ПРИВЯЗКА КЛИЕНТА К ВОДИТЕЛЮ ПРИ ВЗЯТИИ ЗАКАЗА ТАКСИ
    client_driver_link[client_id] = driver_id
    
    info = get_driver_info(driver_id)
    await callback.message.edit_text(f"✅ Взято. Клиент: {order['phone']}")
    await bot.send_message(client_id, f"🚕 Едет: {info[0]} ({info[1]})\n📞 {order['phone']}\n\n🔐 <b>Твой код доступа к Crazy-меню:</b> {info[5]}\n(Введи его в разделе 'Ввести КЛЮЧ', чтобы заказывать услуги в пути!)")

# ==========================================
# 🚦 РЕГИСТРАЦИЯ (С КОДОМ)
# ==========================================
@dp.message(Command("driver"))
async def cmd_driver_register(message: types.Message, state: FSMContext):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT status FROM drivers WHERE user_id=?", (message.from_user.id,)).fetchone()
    conn.close()
    if res:
        await message.answer("Ты уже в базе.")
        return
    await message.answer("🚕 <b>РЕГИСТРАЦИЯ</b>\nАвто, цвет, номер:")
    await state.set_state(DriverRegistration.waiting_for_car)

@dp.message(DriverRegistration.waiting_for_car)
async def reg_car(message: types.Message, state: FSMContext):
    await state.update_data(car=message.text)
    await message.answer("💳 Реквизиты:")
    await state.set_state(DriverRegistration.waiting_for_payment_info)

@dp.message(DriverRegistration.waiting_for_payment_info)
async def reg_pay(message: types.Message, state: FSMContext):
    await state.update_data(pay=message.text)
    await message.answer("🔑 <b>Придумай свой КОД-КЛЮЧ</b> (например: 777, BOSS, TAXI1):\nЭтот код ты будешь говорить клиентам, чтобы они открыли меню услуг.")
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
        await message.answer("❌ Такой код уже занят! Придумай другой.")
        return
    finally:
        conn.close()
    await state.clear()

# (Остальные админские функции update_boss_monitor, admin_approve и прочее остаются такими же, как в прошлом коде, я их не дублирую для краткости, но они должны быть в файле!)
# ВНИМАНИЕ: Обязательно вставь функции adm_approve, adm_reject, cmd_admin, edit_driver и т.д. из предыдущего ответа!

# ... (ВСТАВИТЬ СЮДА КОД АДМИНКИ ИЗ ПРОШЛОГО ОТВЕТА) ...
# Я добавлю только критически важную правку для админки ниже:

@dp.callback_query(F.data.startswith("adm_approve_"))
async def admin_approve_driver(callback: types.CallbackQuery):
    if callback.from_user.id != BOSS_ID: return
    d_id = int(callback.data.split("_")[2])
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE drivers SET status='active' WHERE user_id=?", (d_id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("✅ Одобрен.")
    try: await bot.send_message(d_id, "🎉 Одобрен! Твой код работает.")
    except: pass

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
