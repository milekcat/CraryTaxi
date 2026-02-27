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

# --- БАЗА УСЛУГ ---
CRAZY_SERVICES = {
    "candy": {"name": "🍬 Конфетка", "price": 0, "desc": "Водитель торжественно вручит вам вкусную конфетку. Мелочь, а приятно!"},
    "napkin": {"name": "🧻 Салфетка", "price": 0, "desc": "Влажная салфетка, чтобы вытереть слезы счастья (или страха)."},
    "joke": {"name": "🎭 Анекдот", "price": 50, "desc": "Анекдот из золотой коллекции. За качество юмора ответственность не несем!"},
    "poem": {"name": "📜 Стих", "price": 100, "desc": "Прочту стихотворение с выражением, как на утреннике в детском саду."},
    "sleep": {"name": "🛌 Сон под шепот ям", "price": 150, "desc": "Аккуратная езда, расслабляющая музыка, водитель молчит как рыба."},
    "tale": {"name": "📖 Сказка на ночь", "price": 300, "desc": "Захватывающая (и полностью выдуманная) история из жизни таксиста."},
    "granny": {"name": "👵 Бабушка-ворчунья", "price": 800, "desc": "Всю дорогу буду бубнить, как ты плохо одет и что 'в наше время было лучше'."},
    "spy": {"name": "🕵️‍♂️ Шпион", "price": 2000, "desc": "Едем за 'той машиной'. Водитель надевает черные очки и говорит по рации."},
    "karaoke": {"name": "🎤 Караоке-баттл", "price": 5000, "desc": "Поем во весь голос хиты 90-х. Водитель подпевает и жутко фальшивит."},
    "dance": {"name": "🕺 Танцы на светофоре", "price": 15000, "desc": "Красный свет? Я выхожу из машины и танцую безумный танец!"},
    "kidnap": {"name": "🎭 Дружеское похищение", "price": 30000, "desc": "Тебя 'жестко' пакуют в авто (по сценарию) и везут пить чай на природу."},
    "tarzan": {"name": "🦍 Тарзан-шоу", "price": 50000, "desc": "Перформанс с криками и биением себя в грудь. Максимальный кринж!"},
    "burn": {"name": "🔥 Сжечь машину", "price": 1000000, "desc": "Приезжаем на пустырь, ты даешь лям, я даю канистру. Гори оно всё огнем."}
}

class OrderRide(StatesGroup):
    waiting_for_from = State()
    waiting_for_to = State()
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
        "2. Вы заранее отказываетесь от любых судебных исков и претензий на моральный ущерб.\n"
        "3. Наш адвокат слишком хорош — он однажды выиграл дело у здравого смысла. Судиться с нами бесполезно.\n"
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
    await callback.message.edit_text("🔥 <b>ДОБРО ПОЖАЛОВАТЬ В CRAZY TAXI!</b> 🔥\nКонтракт подписан цифровой подписью. Двери заблокированы (шутка).")
    await callback.message.answer("Выбирай действие в меню ниже 👇", reply_markup=main_kb)

@dp.callback_query(F.data == "decline_tos")
async def tos_declined(callback: types.CallbackQuery):
    await callback.message.edit_text("🚶‍♂️ Очень жаль! Водитель разблокировал двери. Удачной пешей прогулки!")

async def check_tos(message: types.Message) -> bool:
    if not is_client_accepted(message.from_user.id):
        await message.answer("🛑 <b>ОШИБКА ДОСТУПА!</b>\nСначала нужно подписать контракт о снятии ответственности. Нажми /start")
        return False
    return True

# ==========================================
# ⚖️ ЮРИДИЧЕСКИЙ РАЗДЕЛ И АДВОКАТ
# ==========================================
@dp.message(F.text == "⚖️ Вызвать адвоката / Правила")
async def lawyer_menu(message: types.Message):
    if not await check_tos(message): return
    
    lawyer_text = (
        "⚖️ <b>НАШ НЕПОБЕДИМЫЙ АДВОКАТ</b> ⚖️\n\n"
        "Думаешь, что-то вышло из-под контроля? Хочешь пожаловаться?\n\n"
        "<b>Ознакомься с прецедентами:</b>\n"
        "• Наш юрист доказал в суде, что красный свет светофора — это 'субъективное восприятие цвета'.\n"
        "• Любой твой испуганный крик в салоне по договору классифицируется как 'активное участие в интерактиве'.\n"
        "• Читать права здесь будет только он, и то на латыни.\n\n"
        "<i>Все еще хочешь с ним связаться? Жми кнопку, если не боишься встречного иска за отрыв от важных дел!</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚨 СВЯЗАТЬСЯ С АДВОКАТОМ 🚨", callback_data="call_lawyer")]
    ])
    await message.answer(lawyer_text, reply_markup=kb)

@dp.callback_query(F.data == "call_lawyer")
async def alert_lawyer(callback: types.CallbackQuery):
    await callback.answer("🚨 Адвокат уже выехал... шучу, он занят подачей иска на твою скуку. Договаривайся с водителем!", show_alert=True)
    drivers = get_active_drivers()
    for d_id in drivers:
        try: await bot.send_message(d_id, f"⚖️ Внимание! Клиент @{callback.from_user.username} пытается вызвать адвоката! Кажется, кто-то переборщил с перформансом.")
        except: pass

# ==========================================
# 🚀 МГНОВЕННАЯ РАССЫЛКА ЗАКАЗОВ ВОДИТЕЛЯМ
# ==========================================
async def send_to_driver(d_id, order_text, reply_markup):
    """Отправка сообщения одному водителю (для параллельного запуска)"""
    try:
        await bot.send_message(chat_id=d_id, text=order_text, reply_markup=reply_markup)
        return True
    except Exception as e:
        logging.error(f"Не удалось отправить водителю {d_id}: {e}")
        return False

async def broadcast_order_to_drivers(client_id, order_text, reply_markup):
    """Умное распределение заказов с имитацией поиска"""
    
    # 1. Запускаем "Радар" для клиента
    search_msg = await bot.send_message(client_id, "📡 <i>Радары включены. Сканируем улицы в поисках безумцев...</i>")
    await asyncio.sleep(3.5) # Пауза для создания эффекта реального поиска
    
    drivers = get_active_drivers()
    
    # 2. Если водителей вообще нет на линии
    if not drivers:
        await search_msg.edit_text("😔 <b>Все машины сейчас заняты.</b>\nОни либо на других заказах, либо в отключке. Попробуй повторить вызов через пару минут!")
        if client_id in active_orders:
            del active_orders[client_id]
        return
        
    # 3. Обновляем статус клиенту
    await search_msg.edit_text("⏳ <b>Сигнал передан всем водителям на линии!</b>\nЖдем, кто из них успеет забрать заказ первым...")
    
    # 4. Мгновенная параллельная рассылка всем водителям одновременно
    tasks = [send_to_driver(d_id, order_text, reply_markup) for d_id in drivers]
    results = await asyncio.gather(*tasks)
    
    # Если рассылка технически не прошла ни одному
    if not any(results):
        await bot.send_message(client_id, "🔌 Произошла ошибка связи с таксопарком. Попробуй позже.")
        if client_id in active_orders:
            del active_orders[client_id]

# ==========================================
# 📜 CRAZY ХАОС-МЕНЮ И ЛОГИКА ОПЛАТЫ
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
        client_text = (
            f"🚕 <b>ВОДИТЕЛЬ НАЙДЕН!</b>\n"
            f"К тебе приедет: {driver_info[0]} ({driver_info[1]})\n\n"
            f"🎁 <b>Эта услуга абсолютно бесплатна!</b>\n\n"
            f"Жми кнопку ниже, чтобы водитель начал!"
        )
    else:
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Я ОПЛАТИЛ", callback_data=f"cpay_done_{client_id}")]])
        client_text = (
            f"🚕 <b>ВОДИТЕЛЬ НАЙДЕН!</b>\n"
            f"К тебе приедет: {driver_info[0]} ({driver_info[1]})\n\n"
            f"💳 <b>Переведи {order['price']}₽ на реквизиты:</b>\n<code>{driver_info[2]}</code>\n\n"
            f"Жми кнопку ниже после перевода!"
        )
        
    await bot.send_message(client_id, client_text, reply_markup=pay_kb)

@dp.callback_query(F.data.startswith("cpay_done_"))
async def client_paid_crazy(callback: types.CallbackQuery):
    client_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return
    
    if order['price'] == 0:
        await callback.message.edit_text("⏳ Водитель готовится к перформансу...")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ВЫПОЛНИЛ!", callback_data=f"confirm_pay_{client_id}")]])
        await bot.send_message(order["driver_id"], f"🎁 Клиент @{callback.from_user.username} ждет свой бонус: <b>{order['service']['name']}</b>!\nСделай это и нажми кнопку.", reply_markup=kb)
    else:
        await callback.message.edit_text("⏳ Проверяем поступление средств...")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ДЕНЬГИ ПРИШЛИ (Начать)", callback_data=f"confirm_pay_{client_id}")]])
        await bot.send_message(order["driver_id"], f"💸 Клиент @{callback.from_user.username} нажал 'Оплатил' за {order['service']['name']}.\nПроверь баланс {order['price']}₽ и подтверди!", reply_markup=kb)

@dp.callback_query(F.data.startswith("confirm_pay_"))
async def driver_confirms_pay(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)
    
    if not order: return
    
    add_commission(driver_id, order['price'])
    
    if order['price'] == 0:
        await callback.message.edit_text("✅ Бесплатный заказ выполнен! Ты красавчик.")
        await bot.send_message(client_id, "🎉 Водитель подтвердил выполнение! Надеюсь, тебе понравилось!")
    else:
        await callback.message.edit_text("✅ Оплата подтверждена! Комиссия 10% записана в твой долг. Выполняй заказ!")
        await bot.send_message(client_id, "🎉 Водитель подтвердил оплату! Шоу начинается 💨")
        
    del active_orders[client_id]

# ==========================================
# 💡 СВОЙ ВАРИАНТ (ИНДИВИДУАЛЬНЫЙ ЗАКАЗ)
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
# 🚕 ОБЫЧНОЕ ТАКСИ (ТОРГ)
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
    await message.answer("💰 <b>Сколько готов заплатить?</b> (Сумма в рублях):")
    await state.set_state(OrderRide.waiting_for_price)

@dp.message(OrderRide.waiting_for_price)
async def process_price(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    client_id = message.from_user.id
    
    active_orders[client_id] = {
        "type": "taxi", "status": "pending", "price": message.text,
        "from": user_data['from_address'], "to": user_data['to_address']
    }

    await message.answer("✅ <b>Параметры поездки приняты!</b>", reply_markup=main_kb)
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Забрать поездку", callback_data=f"take_taxi_{client_id}")]])
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
    driver_info = get_driver_info(driver_id)
    
    await callback.message.edit_text(f"✅ Ты забрал поездку!\nМаршрут: {order['from']} -> {order['to']}")
    await bot.send_message(client_id, f"🚕 <b>ВОДИТЕЛЬ НАЙДЕН!</b>\nК тебе едет: {driver_info[0]} ({driver_info[1]})\nСвяжитесь для уточнения деталей!")

# ==========================================
# 🚦 РЕГИСТРАЦИЯ ВОДИТЕЛЕЙ (ПОЛНАЯ ВЕРСИЯ)
# ==========================================
@dp.message(Command("driver"))
async def cmd_driver_register(message: types.Message, state: FSMContext):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM drivers WHERE user_id=?", (message.from_user.id,))
    res = cursor.fetchone()
    conn.close()
    
    if res:
        status = res[0]
        if status == 'active':
            await message.answer("✅ Ты уже в деле! Ожидай новые заказы.")
        elif status == 'pending':
            await message.answer("⏳ Твоя заявка на рассмотрении у Босса. Ожидай.")
        elif status == 'blocked':
            await message.answer("❌ Твой аккаунт заблокирован. Свяжись с Боссом для оплаты долга.")
        return

    await message.answer(
        "🚕 <b>РЕГИСТРАЦИЯ ВОДИТЕЛЯ CRAZY TAXI</b>\n\n"
        "Хочешь творить хаос и зарабатывать? Отлично!\n"
        "Напиши марку своей машины, цвет и госномер (Например: <i>Желтый Kia Rio, А123ВВ76</i>):"
    )
    await state.set_state(DriverRegistration.waiting_for_car)

@dp.message(DriverRegistration.waiting_for_car)
async def process_car_info(message: types.Message, state: FSMContext):
    await state.update_data(car_info=message.text)
    await message.answer(
        "💳 Отлично. Теперь напиши свои <b>реквизиты для получения оплат от клиентов</b> (Например: <i>Сбербанк/Тинькофф +79991234567 Иван И.</i>):"
    )
    await state.set_state(DriverRegistration.waiting_for_payment_info)

@dp.message(DriverRegistration.waiting_for_payment_info)
async def process_payment_info(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    car_info = user_data['car_info']
    payment_info = message.text
    user_id = message.from_user.id
    username = message.from_user.username or "Без юзернейма"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO drivers (user_id, username, car_info, payment_info, status) VALUES (?, ?, ?, ?, 'pending')",
        (user_id, username, car_info, payment_info)
    )
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(
        "📝 Заявка отправлена Боссу!\n\n"
        "⚠️ <b>ВНИМАНИЕ:</b> Для активации аккаунта предусмотрен стартовый взнос.\n"
        "Ожидай решения администрации."
    )

    admin_text = (
        f"🚨 <b>НОВАЯ ЗАЯВКА ВОДИТЕЛЯ</b> 🚨\n\n"
        f"👤 @{username} (ID: <code>{user_id}</code>)\n"
        f"🚗 Авто: {car_info}\n"
        f"💳 Реквизиты: {payment_info}\n\n"
        f"<i>Прими решение о допуске:</i>"
    )
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"adm_approve_{user_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_reject_{user_id}")]
    ])
    await bot.send_message(chat_id=BOSS_ID, text=admin_text, reply_markup=admin_kb)

# ==========================================
# 👑 АДМИН-ПАНЕЛЬ И УПРАВЛЕНИЕ
# ==========================================
@dp.callback_query(F.data.startswith("adm_approve_"))
async def admin_approve_driver(callback: types.CallbackQuery):
    if callback.from_user.id != BOSS_ID: return
    driver_id = int(callback.data.split("_")[2])
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE drivers SET status='active' WHERE user_id=?", (driver_id,))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(f"✅ Водитель {driver_id} <b>ОДОБРЕН</b> и добавлен в сеть.")
    try: await bot.send_message(chat_id=driver_id, text="🎉 <b>ТВОЯ ЗАЯВКА ОДОБРЕНА!</b>\nДобро пожаловать во франшизу Crazy Taxi. Теперь ты будешь получать заказы от клиентов.")
    except: pass

@dp.callback_query(F.data.startswith("adm_reject_"))
async def admin_reject_driver(callback: types.CallbackQuery):
    if callback.from_user.id != BOSS_ID: return
    driver_id = int(callback.data.split("_")[2])
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM drivers WHERE user_id=?", (driver_id,))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(f"❌ Водитель {driver_id} <b>ОТКЛОНЕН</b>.")
    try: await bot.send_message(chat_id=driver_id, text="❌ К сожалению, Босс отклонил твою заявку в Crazy Taxi.")
    except: pass

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
        text += f"{status_emoji} <b>{d[1]}</b> (ID: {d[0]})\nДолг: <b>{d[3]}₽</b> | Статус: {d[2]}\n"
        text += f"Блок: /block_{d[0]} | Анблок: /unblock_{d[0]}\n---\n"

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
