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

# Получение токенов
API_TOKEN = os.getenv("API_TOKEN")
BOSS_ID = os.getenv("DRIVER_ID") 

if not API_TOKEN or not BOSS_ID:
    logging.error("CRITICAL: API_TOKEN или DRIVER_ID не найдены!")
    exit()

BOSS_ID = int(BOSS_ID)
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# Глобальные переменные
active_orders = {} 
client_driver_link = {} # Связь: {id_клиента: id_водителя}

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
    
    # Авто-регистрация БОССА
    # В поле payment_info здесь прописываем реквизиты БОССА
    cursor.execute("SELECT 1 FROM drivers WHERE user_id = ?", (BOSS_ID,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO drivers (user_id, username, car_info, payment_info, access_code, status) VALUES (?, ?, ?, ?, ?, 'active')",
            (BOSS_ID, "BOSS_NETWORK", "BOSS (Black Car)", "Яндекс Банк +79012723729", "BOSS")
        )
    conn.commit()
    conn.close()

init_db()

# --- Вспомогательные функции ---
def get_active_drivers():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM drivers WHERE status='active'")
    res = [d[0] for d in cursor.fetchall()]
    conn.close()
    return res

def get_driver_by_code(code):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, car_info FROM drivers WHERE access_code=? AND status='active'", (code,))
    res = cursor.fetchone()
    conn.close()
    return res

def get_driver_info(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 0:username, 1:car, 2:payment_info, 3:balance, 4:status, 5:code
    cursor.execute("SELECT username, car_info, payment_info, balance, status, access_code FROM drivers WHERE user_id=?", (user_id,))
    res = cursor.fetchone()
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
    conn.execute("INSERT INTO order_history (driver_id, service_name, price) VALUES (?, ?, ?)", (driver_id, service_name, price))
    conn.commit()
    conn.close()

def add_commission(driver_id, amount):
    if driver_id == BOSS_ID: return 
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

# ==========================================
# 📜 ПОЛНОЕ ОПИСАНИЕ УСЛУГ
# ==========================================
CRAZY_SERVICES = {
    "candy": {
        "name": "🍬 Конфетка", 
        "price": 0, 
        "desc": "Водитель торжественно вручит вам вкусную конфетку и пожелает хорошего дня. Мелочь, а приятно! (Сделано с уважением)"
    },
    "joke": {
        "name": "🎭 Анекдот", 
        "price": 50, 
        "desc": "Водитель расскажет анекдот из своей золотой коллекции. За качество юмора ответственность не несем, но стараться будем!"
    },
    "poem": {
        "name": "📜 Стих с выражением", 
        "price": 100, 
        "desc": "Прочту стихотворение с чувством, с толком, с расстановкой. Как на утреннике в детском саду, только в такси."
    },
    "sleep": {
        "name": "🛌 Сон под шепот ям", 
        "price": 150, 
        "desc": "Режим 'Ниндзя'. Аккуратная езда, расслабляющая музыка выключена, водитель молчит как рыба. Мы охраняем ваш покой."
    },
    "tale": {
        "name": "📖 Сказка на ночь", 
        "price": 300, 
        "desc": "Водитель расскажет захватывающую (и полностью выдуманную) историю из жизни таксиста про олигархов и инопланетян."
    },
    "granny": {
        "name": "👵 Бабушка-ворчунья", 
        "price": 800, 
        "desc": "Ролевая игра. Всю дорогу буду бубнить, как ты плохо одет и что 'в наше время было лучше'. Полное погружение."
    },
    "spy": {
        "name": "🕵️‍♂️ Шпионский эскорт", 
        "price": 2000, 
        "desc": "Едем за 'той машиной'. Водитель надевает черные очки, говорит по рации кодами и нервно смотрит в зеркала."
    },
    "karaoke": {
        "name": "🎤 Караоке-баттл", 
        "price": 5000, 
        "desc": "Поем во весь голос хиты 90-х. Водитель подпевает и жутко фальшивит, но делает это от чистого сердца!"
    },
    "dance": {
        "name": "🕺 Танцы на светофоре", 
        "price": 15000, 
        "desc": "Красный свет? Я выхожу из машины и танцую безумный танец (макарену или лезгинку)! Стыдно вам, весело всем."
    },
    "kidnap": {
        "name": "🎭 Дружеское похищение", 
        "price": 30000, 
        "desc": "Тебя 'жестко' пакуют в авто (по сценарию), надевают мешок (по желанию) и везут пить чай на природу."
    },
    "tarzan": {
        "name": "🦍 Тарзан-шоу", 
        "price": 50000, 
        "desc": "Перформанс с криками, биением себя в грудь и рычанием на прохожих. Максимальный уровень кринжа гарантирован."
    },
    "burn": {
        "name": "🔥 Сжечь машину", 
        "price": 1000000, 
        "desc": "Приезжаем на пустырь, ты даешь лям, я даю канистру. Гори оно всё огнем. Эпичный финал поездки."
    }
}

# ==========================================
# 🛠 FSM (Состояния)
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
    waiting_for_code = State()

class DriverChangeCode(StatesGroup):
    waiting_for_new_code = State()

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
# 🛑 СТАРТ И ЮРИДИЧЕСКИЙ ДИСКЛЕЙМЕР
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
# ⚖️ ЮРИДИЧЕСКИЙ РАЗДЕЛ (АДВОКАТ)
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
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚨 СВЯЗАТЬСЯ С АДВОКАТОМ 🚨", callback_data="call_lawyer")]])
    await message.answer(lawyer_text, reply_markup=kb)

@dp.callback_query(F.data == "call_lawyer")
async def alert_lawyer(callback: types.CallbackQuery):
    await callback.answer("🚨 Адвокат уже выехал... шучу, он занят подачей иска на твою скуку. Договаривайся с водителем!", show_alert=True)

# ==========================================
# 🪪 КАБИНЕТ ВОДИТЕЛЯ
# ==========================================
@dp.message(Command("cab"))
async def cmd_driver_cabinet(message: types.Message):
    info = get_driver_info(message.from_user.id)
    
    if not info:
        await message.answer("❌ <b>Ошибка доступа!</b>\nТы не зарегистрирован в системе Crazy Taxi.\nНапиши /driver чтобы подать заявку.")
        return
        
    if info[4] != 'active':
        status_txt = "⏳ На рассмотрении" if info[4] == 'pending' else "🔒 ЗАБЛОКИРОВАН"
        await message.answer(f"❌ Твой статус: <b>{status_txt}</b>.\nДождись решения Босса или оплати долги.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    hist = conn.execute("SELECT COUNT(*), SUM(price) FROM order_history WHERE driver_id=?", (message.from_user.id,)).fetchone()
    conn.close()
    
    orders_count = hist[0] or 0
    total_earned = hist[1] or 0
    debt = info[3]
    my_code = info[5]
    
    active_txt = ""
    for cid, o in active_orders.items():
        if o.get("driver_id") == message.from_user.id and o["status"] == "accepted":
            name = o.get("service", {}).get("name", "Такси")
            active_txt += f"🔹 {name} | 💰 {o['price']}\n"
    if not active_txt: active_txt = "<i>Пока нет активных заказов</i>"

    text = (
        f"🪪 <b>ЛИЧНЫЙ КАБИНЕТ ВОДИТЕЛЯ</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>{info[0]}</b>\n"
        f"🚘 Авто: <b>{info[1]}</b>\n"
        f"🔑 Твой секретный код: <code>{my_code}</code>\n"
        f"<i>(Говори этот код клиентам, чтобы они могли заказывать услуги!)</i>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Твоя статистика:</b>\n"
        f"✅ Выполнено заказов: <b>{orders_count}</b>\n"
        f"💰 Заработано всего: <b>{total_earned}₽</b>\n"
        f"⚠️ <b>ТЕКУЩИЙ ДОЛГ (10%): {debt}₽</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔥 <b>ПРЯМО СЕЙЧАС В РАБОТЕ:</b>\n{active_txt}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Сменить КОД доступа", callback_data="cab_change_code")],
        [InlineKeyboardButton(text="💸 Оплатить долг Боссу", callback_data="cab_pay_debt")]
    ])
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "cab_change_code")
async def cab_change_code_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("⌨️ <b>Введи новый код доступа</b> (например: BOSS777, TAXI1):\n<i>Код должен быть уникальным и легко запоминающимся.</i>")
    await state.set_state(DriverChangeCode.waiting_for_new_code)
    await callback.answer()

@dp.message(DriverChangeCode.waiting_for_new_code)
async def cab_save_new_code(message: types.Message, state: FSMContext):
    new_code = message.text.upper().strip()
    try:
        update_driver_field(message.from_user.id, "access_code", new_code)
        await message.answer(f"✅ <b>Код успешно обновлен!</b>\nТвой новый ключ: <code>{new_code}</code>")
    except sqlite3.IntegrityError:
        await message.answer("❌ Этот код уже занят другим водителем! Придумай что-то пооригинальнее.")
        return
    await state.clear()

@dp.callback_query(F.data == "cab_pay_debt")
async def cab_pay_debt(callback: types.CallbackQuery):
    info = get_driver_info(callback.from_user.id)
    # Берем реквизиты Босса
    boss_info = get_driver_info(BOSS_ID)
    boss_requisites = boss_info[2] if boss_info else "Уточните у Босса в ЛС"
    
    await callback.message.answer(
        f"💸 <b>ОПЛАТА КОМИССИИ</b>\n\n"
        f"Твой долг: <b>{info[3]}₽</b>\n"
        f"Переведи эту сумму Боссу:\n"
        f"💳 <b>{boss_requisites}</b>\n\n"
        f"После перевода скинь скриншот в личку Боссу!"
    )
    await callback.answer()

# ==========================================
# 🚦 РЕГИСТРАЦИЯ ВОДИТЕЛЯ
# ==========================================
@dp.message(Command("driver"))
async def cmd_driver_register(message: types.Message, state: FSMContext):
    res = get_driver_info(message.from_user.id)
    if res:
        await message.answer("Ты уже есть в базе данных! Используй /cab для входа.")
        return

    await message.answer(
        "🚕 <b>РЕГИСТРАЦИЯ В CRAZY TAXI</b>\n\n"
        "Хочешь творить хаос и зарабатывать на этом? Добро пожаловать в семью!\n\n"
        "<b>Шаг 1 из 3.</b> Напиши марку, цвет и госномер твоего боевого коня:"
    )
    await state.set_state(DriverRegistration.waiting_for_car)

@dp.message(DriverRegistration.waiting_for_car)
async def process_car(message: types.Message, state: FSMContext):
    await state.update_data(car=message.text)
    await message.answer("💳 <b>Шаг 2 из 3.</b> Напиши свои реквизиты (Банк + Номер карты/телефон) для приема оплат от клиентов:")
    await state.set_state(DriverRegistration.waiting_for_payment_info)

@dp.message(DriverRegistration.waiting_for_payment_info)
async def process_pay(message: types.Message, state: FSMContext):
    await state.update_data(pay=message.text)
    await message.answer("🔑 <b>Шаг 3 из 3.</b> Придумай свой <b>Секретный Код-Ключ</b> (например: 777, KING, JOKER):\nЭтот код ты будешь говорить клиентам, чтобы они могли разблокировать меню услуг у тебя в машине.")
    await state.set_state(DriverRegistration.waiting_for_code)

@dp.message(DriverRegistration.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    code = message.text.upper().strip()
    data = await state.get_data()
    
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT INTO drivers (user_id, username, car_info, payment_info, access_code, status) VALUES (?, ?, ?, ?, ?, 'pending')", 
            (message.from_user.id, message.from_user.username, data['car'], data['pay'], code)
        )
        conn.commit()
        await message.answer("📝 <b>Заявка отправлена Боссу!</b>\nЖди одобрения. Как только тебя примут, бот пришлет уведомление.")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Одобрить", callback_data=f"adm_approve_{message.from_user.id}")]])
        await bot.send_message(BOSS_ID, f"🚨 <b>НОВАЯ ЗАЯВКА ВОДИТЕЛЯ</b>\n👤 @{message.from_user.username}\n🚘 {data['car']}\n🔑 Код: {code}\n💳 {data['pay']}", reply_markup=kb)
        
    except sqlite3.IntegrityError:
        await message.answer("❌ Упс! Такой код уже занят. Придумай другой.")
        return
    finally:
        conn.close()
    await state.clear()

# ==========================================
# 🔐 СИСТЕМА КЛЮЧЕЙ
# ==========================================
@dp.message(F.text == "🔐 Ввести КЛЮЧ услуги")
async def ask_for_key(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    await message.answer("🕵️‍♂️ <b>Введи секретный код водителя</b> (спроси у него, он знает):\nЭто разблокирует Crazy-меню именно для этой поездки.")
    await state.set_state(UnlockMenu.waiting_for_key)

@dp.message(UnlockMenu.waiting_for_key)
async def process_key(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    driver = get_driver_by_code(code)
    
    if driver:
        driver_id, driver_name, car_info = driver
        client_driver_link[message.from_user.id] = driver_id
        await message.answer(f"🔓 <b>КЛЮЧ ПРИНЯТ! ДОСТУП РАЗРЕШЕН!</b>\n\n🚘 Борт: <b>{car_info}</b>\n👤 Водитель: <b>@{driver_name}</b>\n\nТеперь раздел 'CRAZY МЕНЮ' работает и отправляет заказы лично этому водителю.", reply_markup=main_kb)
        await state.clear()
        try: await bot.send_message(driver_id, f"🔗 Клиент @{message.from_user.username} ввел твой ключ и подключился к борту!")
        except: pass
    else:
        await message.answer("❌ <b>Неверный ключ!</b> Попробуй снова или спроси у водителя.")

# ==========================================
# 🚀 МОНИТОРИНГ
# ==========================================
async def update_boss_monitor(client_id, taking_driver_id):
    order = active_orders.get(client_id)
    if not order or 'boss_msg_id' not in order: return
    
    drv_info = get_driver_info(taking_driver_id)
    drv_name = f"@{drv_info[0]}" if drv_info[0] else "Unknown"
    text_prefix = "🚫 <b>ЗАБРАЛ:</b> " + ("ТЫ (БОСС)!" if taking_driver_id == BOSS_ID else f"{drv_name} ({drv_info[1]})")
    
    try: await bot.edit_message_text(chat_id=BOSS_ID, message_id=order['boss_msg_id'], text=f"{text_prefix}\n\n{order.get('broadcasting_text','')}", reply_markup=None)
    except TelegramBadRequest: pass

async def broadcast_order_to_drivers(client_id, order_text, driver_kb, boss_kb):
    boss_msg = await bot.send_message(chat_id=BOSS_ID, text=f"🚨 <b>МОНИТОРИНГ СЕТИ</b>\n{order_text}", reply_markup=boss_kb)
    if client_id in active_orders:
        active_orders[client_id]['boss_msg_id'] = boss_msg.message_id
        active_orders[client_id]['broadcasting_text'] = order_text

    search_msg = await bot.send_message(client_id, "📡 <i>Радары включены. Сканируем улицы в поисках безумцев...</i>")
    await asyncio.sleep(2.5)
    
    drivers = get_active_drivers()
    drivers_to_broadcast = [d for d in drivers if d != BOSS_ID]
    
    if not drivers_to_broadcast:
        await search_msg.edit_text("😔 <b>Все водители сейчас заняты.</b>\nБосс уведомлен о твоем запросе.")
        return
        
    await search_msg.edit_text("⏳ <b>Сигнал передан всем водителям на линии!</b>\nЖдем, кто успеет первым...")
    
    async def send_to_driver(d_id):
        try: await bot.send_message(chat_id=d_id, text=order_text, reply_markup=driver_kb)
        except: return False
    tasks = [send_to_driver(d_id) for d_id in drivers_to_broadcast]
    await asyncio.gather(*tasks)

# ==========================================
# 📜 CRAZY МЕНЮ
# ==========================================
@dp.message(F.text == "📜 CRAZY ХАОС-МЕНЮ (В поездке)")
async def show_crazy_menu(message: types.Message):
    if not await check_tos(message): return
    if message.from_user.id not in client_driver_link:
        await message.answer("🔒 <b>МЕНЮ ЗАБЛОКИРОВАНО</b>\nСначала нажми '🔐 Ввести КЛЮЧ услуги' и введи код водителя.", reply_markup=main_kb)
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
    await message.answer("🔥 <b>CRAZY МЕНЮ (ПРЯМОЙ ЗАКАЗ)</b> 🔥\nВыбирай приключение:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("csel_"))
async def process_crazy_selection(callback: types.CallbackQuery):
    client_id = callback.from_user.id
    driver_id = client_driver_link.get(client_id)
    if not driver_id:
        await callback.answer("Связь потеряна. Введи ключ.", show_alert=True)
        return

    service = CRAZY_SERVICES[callback.data.split("_")[1]]
    active_orders[client_id] = {"type": "crazy", "status": "direct_order", "price": str(service["price"]), "driver_id": driver_id, "service": service}
    
    await callback.message.edit_text(f"🚀 <b>Заказ отправлен лично водителю!</b>\n🎭 Услуга: <b>{service['name']}</b>\n📝 {service['desc']}")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ И ВЫПОЛНИТЬ", callback_data=f"driver_direct_accept_{client_id}")]])
    await bot.send_message(driver_id, f"🔔 <b>ПЕРСОНАЛЬНЫЙ ЗАКАЗ (По ключу)</b>\n👤 Клиент здесь!\n🎭 Хочет: <b>{service['name']}</b>", reply_markup=kb)
    if driver_id != BOSS_ID: await bot.send_message(BOSS_ID, f"👀 КОНТРОЛЬ: {service['name']} -> {driver_id}")

@dp.callback_query(F.data.startswith("driver_direct_accept_"))
async def driver_direct_accept(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[3])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return
    
    info = get_driver_info(driver_id)
    price_val = extract_price(order['price'])
    
    if price_val == 0:
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ЖДУ СЮРПРИЗ!", callback_data=f"cpay_done_{client_id}")]])
        await bot.send_message(client_id, f"✅ Водитель принял заказ!\n🎁 Эта услуга бесплатна. Жми кнопку!", reply_markup=pay_kb)
    else:
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Я ОПЛАТИЛ", callback_data=f"cpay_done_{client_id}")]])
        await bot.send_message(client_id, f"✅ Водитель готов!\n💳 Переведи <b>{order['price']}</b> на реквизиты:\n<code>{info[2]}</code>", reply_markup=pay_kb)
    await callback.message.edit_text("✅ Ты принял заказ. Жди подтверждения клиента.")

# --- Оплата ---
@dp.callback_query(F.data.startswith("cpay_done_"))
async def client_paid_crazy(callback: types.CallbackQuery):
    client_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ВЫПОЛНИЛ (Закрыть)", callback_data=f"confirm_pay_{client_id}")]])
    await callback.message.edit_text("⏳ Ждем подтверждения водителя...")
    await bot.send_message(order["driver_id"], f"💸 Клиент нажал кнопку 'Оплатил/Жду'. Проверь и выполняй!", reply_markup=kb)

@dp.callback_query(F.data.startswith("confirm_pay_"))
async def driver_confirms_pay(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return
    
    price = extract_price(order['price'])
    add_commission(driver_id, price)
    log_order(driver_id, order['service']['name'], price)
    
    await callback.message.edit_text("✅ Заказ закрыт и добавлен в статистику.")
    await bot.send_message(client_id, "🎉 Услуга выполнена! Спасибо за безумие.")
    del active_orders[client_id]

# ==========================================
# 🚕 ТАКСИ + АУКЦИОН
# ==========================================
@dp.message(F.text == "🚕 Заказать такси (Поиск)")
async def start_taxi(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    await message.answer("📍 <b>Откуда тебя забрать?</b>", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(OrderRide.waiting_for_from)

@dp.message(OrderRide.waiting_for_from)
async def taxi_from(message: types.Message, state: FSMContext):
    await state.update_data(fr=message.text)
    await message.answer("🏁 <b>Куда мчим?</b>")
    await state.set_state(OrderRide.waiting_for_to)

@dp.message(OrderRide.waiting_for_to)
async def taxi_to(message: types.Message, state: FSMContext):
    await state.update_data(to=message.text)
    await message.answer("📞 <b>Напиши свой телефон для связи:</b>")
    await state.set_state(OrderRide.waiting_for_phone)

@dp.message(OrderRide.waiting_for_phone)
async def taxi_ph(message: types.Message, state: FSMContext):
    await state.update_data(ph=message.text)
    await message.answer("💰 <b>Предложи свою цену (руб):</b>")
    await state.set_state(OrderRide.waiting_for_price)

@dp.message(OrderRide.waiting_for_price)
async def taxi_pr(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cid = message.from_user.id
    active_orders[cid] = {"type": "taxi", "status": "pending", "price": message.text, "from": data['fr'], "to": data['to'], "phone": data['ph'], "driver_offers": {}}
    await message.answer("✅ <b>Параметры приняты! Ищем машину...</b>", reply_markup=main_kb)
    await state.clear()
    
    dkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Забрать", callback_data=f"take_taxi_{cid}")], [InlineKeyboardButton(text="💰 Своя цена", callback_data=f"counter_taxi_{cid}")]])
    bkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ БОСС ЗАБРАТЬ", callback_data=f"boss_take_taxi_{cid}")], [InlineKeyboardButton(text="💰 Своя цена", callback_data=f"counter_taxi_{cid}")]])
    text = f"🚕 <b>ЗАКАЗ ТАКСИ</b>\n📍 {data['fr']} -> {data['to']}\n💰 Предлагает: <b>{message.text}</b>"
    await broadcast_order_to_drivers(cid, text, dkb, bkb)

@dp.callback_query(F.data.startswith("take_taxi_") | F.data.startswith("boss_take_taxi_"))
async def take_taxi(callback: types.CallbackQuery):
    is_boss = callback.data.startswith("boss_take_")
    client_id = int(callback.data.split("_")[3 if is_boss else 2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)
    
    if not order or order["status"] != "pending":
        await callback.answer("Упс! Заказ уже забрали.", show_alert=True)
        return
    
    order["status"] = "accepted"
    order["driver_id"] = driver_id
    client_driver_link[client_id] = driver_id 
    await update_boss_monitor(client_id, driver_id)
    
    info = get_driver_info(driver_id)
    finish_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Завершить поездку", callback_data=f"finish_taxi_{client_id}")]])
    
    await callback.message.edit_text(f"✅ <b>Ты забрал поездку!</b>\n📞 Клиент: {order['phone']}", reply_markup=finish_kb)
    await bot.send_message(client_id, f"🚕 <b>ВОДИТЕЛЬ НАЙДЕН!</b>\nК тебе едет: {info[0]} ({info[1]})\n📞 Телефон: {order['phone']}\n\n🔐 <b>Твой код для Crazy-меню:</b> {info[5]}")

@dp.callback_query(F.data.startswith("finish_taxi_"))
async def finish_taxi(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return
    
    price = extract_price(order['price'])
    add_commission(driver_id, price)
    log_order(driver_id, "Такси", price)
    
    await callback.message.edit_text("✅ Поездка успешно завершена.")
    await bot.send_message(client_id, "🏁 Поездка завершена. Спасибо, что выбираете Crazy Taxi!")
    del active_orders[client_id]

# ==========================================
# 💡 СВОЙ ВАРИАНТ (АУКЦИОН)
# ==========================================
@dp.message(F.text == "💡 Свой вариант (Предложить идею)")
async def custom_idea(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    await message.answer("Опиши свою безумную идею:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(CustomIdea.waiting_for_idea)

@dp.message(CustomIdea.waiting_for_idea)
async def custom_pr(message: types.Message, state: FSMContext):
    await state.update_data(idea=message.text)
    await message.answer("💰 Какой бюджет? (сумма в рублях):")
    await state.set_state(CustomIdea.waiting_for_price)

@dp.message(CustomIdea.waiting_for_price)
async def custom_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cid = message.from_user.id
    active_orders[cid] = {"type": "crazy", "status": "pending", "price": message.text, "service": {"name": f"Идея ({data['idea'][:10]}...)", "desc": data['idea']}, "driver_offers": {}}
    await message.answer("✅ <b>Идея зафиксирована!</b> Ждем ответа водителей...", reply_markup=main_kb)
    await state.clear()
    
    dkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ЗАБРАТЬ", callback_data=f"take_crazy_{cid}")], [InlineKeyboardButton(text="💰 Своя цена", callback_data=f"counter_crazy_{cid}")]])
    bkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ БОСС ЗАБРАТЬ", callback_data=f"boss_take_crazy_{cid}")], [InlineKeyboardButton(text="💰 Своя цена", callback_data=f"counter_crazy_{cid}")]])
    text = f"💡 <b>ИДЕЯ ОТ КЛИЕНТА</b>\n📝 {data['idea']}\n💰 Бюджет: <b>{message.text}</b>"
    await broadcast_order_to_drivers(cid, text, dkb, bkb)

# Универсальное взятие "Идеи"
@dp.callback_query(F.data.startswith("take_crazy_") | F.data.startswith("boss_take_crazy_"))
async def take_crazy_gen(callback: types.CallbackQuery):
    is_boss = callback.data.startswith("boss_take_")
    client_id = int(callback.data.split("_")[3 if is_boss else 2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)
    
    if not order or order["status"] != "pending":
        await callback.answer("Упс! Уже забрали.", show_alert=True)
        return
    
    order["status"] = "accepted"
    order["driver_id"] = driver_id
    client_driver_link[client_id] = driver_id
    await update_boss_monitor(client_id, driver_id)
    await callback.message.edit_text("✅ Ты забрал этот спецзаказ!")
    
    info = get_driver_info(driver_id)
    pay_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 ОПЛАТИЛ", callback_data=f"cpay_done_{client_id}")]])
    await bot.send_message(client_id, f"✅ <b>ИСПОЛНИТЕЛЬ НАЙДЕН!</b>\n👤 {info[0]} ({info[1]})\n💳 Переведи бюджет на: <code>{info[2]}</code>\n🔐 Код: {info[5]}", reply_markup=pay_kb)

# ==========================================
# 🤝 ТОРГ (COUNTER-OFFER)
# ==========================================
@dp.callback_query(F.data.startswith("counter_"))
async def start_counter(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    await state.update_data(cid=int(parts[2]), type=parts[1])
    await callback.message.answer("✍️ <b>Напиши свою цену и условия</b> (например: '2000р, буду через 5 мин'):")
    await state.set_state(DriverCounterOffer.waiting_for_offer)
    await callback.answer()

@dp.message(DriverCounterOffer.waiting_for_offer)
async def send_counter(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cid, otype, text = data['cid'], data['type'], message.text
    driver_id = message.from_user.id
    
    order = active_orders.get(cid)
    if not order: 
        await message.answer("Поздно, заказ ушел.")
        return
        
    if "driver_offers" not in order: order["driver_offers"] = {}
    order["driver_offers"][driver_id] = text
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Согласен", callback_data=f"acc_coff_{otype}_{cid}_{driver_id}")], [InlineKeyboardButton(text="❌ Отказ", callback_data=f"rej_coff_{cid}")]])
    label = "БОСС" if driver_id == BOSS_ID else "Водитель"
    await bot.send_message(cid, f"⚡️ <b>{label} предлагает свои условия:</b>\n\n{text}\n\nСогласны?", reply_markup=kb)
    await message.answer("✅ Предложение отправлено клиенту!")
    await state.clear()

@dp.callback_query(F.data.startswith("acc_coff_"))
async def accept_offer(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    otype, cid, did = parts[2], int(parts[3]), int(parts[4])
    
    order = active_orders.get(cid)
    if not order or order["status"] != "pending": return
    
    order["status"] = "accepted"
    order["driver_id"] = did
    # Обновляем цену, пытаясь извлечь цифры из текста предложения водителя
    offered_text = order["driver_offers"].get(did, "")
    extracted = extract_price(offered_text)
    if extracted > 0: order["price"] = str(extracted)
    
    client_driver_link[cid] = did
    await update_boss_monitor(cid, did)
    info = get_driver_info(did)
    
    if otype == "crazy":
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 ОПЛАТИЛ", callback_data=f"cpay_done_{cid}")]])
        await callback.message.edit_text(f"🤝 <b>ДОГОВОРИЛИСЬ!</b>\nИсполнитель: {info[0]}\n💳 Реквизиты: <code>{info[2]}</code>\n🔐 Код: {info[5]}", reply_markup=pay_kb)
    else:
        finish_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Завершить", callback_data=f"finish_taxi_{cid}")]])
        await bot.send_message(did, f"✅ Клиент согласился на твои условия!\n📞 Телефон: <b>{order['phone']}</b>", reply_markup=finish_kb)
        await callback.message.edit_text(f"🚕 <b>ВОДИТЕЛЬ ВЫЕЗЖАЕТ!</b>\n{info[0]} свяжется по номеру {order['phone']}!\n🔐 Код: {info[5]}")

@dp.callback_query(F.data.startswith("rej_coff_"))
async def reject_offer(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Вы отказались от этого предложения. Ждем других.")

# ==========================================
# 👑 АДМИНКА
# ==========================================
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != BOSS_ID: return
    conn = sqlite3.connect(DB_PATH)
    drivers = conn.execute("SELECT user_id, username, status, balance FROM drivers").fetchall()
    conn.close()
    text = "👑 <b>УПРАВЛЕНИЕ ФРАНШИЗОЙ</b>\n\n"
    for d in drivers:
        icon = "🟢" if d[2]=='active' else "🔴"
        text += f"{icon} <b>{d[1]}</b> (ID: {d[0]})\n💰 Долг: {d[3]}₽\n👉 Управление: /edit_{d[0]}\n\n"
    await message.answer(text)

@dp.callback_query(F.data.startswith("adm_approve_"))
async def adm_app(c: types.CallbackQuery):
    if c.from_user.id != BOSS_ID: return
    d_id = int(c.data.split("_")[2])
    update_driver_field(d_id, "status", "active")
    await c.message.edit_text("✅ Водитель ОДОБРЕН.")
    try: await bot.send_message(d_id, "🎉 <b>ТВОЯ ЗАЯВКА ОДОБРЕНА!</b>\nТеперь ты в деле. Нажми /cab чтобы увидеть свой профиль и код доступа.")
    except: pass

@dp.message(F.text.startswith("/edit_"))
async def edit_dr(m: types.Message):
    if m.from_user.id != BOSS_ID: return
    try: d_id = int(m.text.split("_")[1])
    except: return
    
    info = get_driver_info(d_id)
    if not info: 
        await m.answer("Водитель не найден.")
        return
    
    act = "block" if info[4]=='active' else "unblock"
    txt = "🔒 Заблочить" if info[4]=='active' else "🔓 Разблочить"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 Изм. Авто", callback_data=f"edt_car_{d_id}"), InlineKeyboardButton(text="💳 Изм. Рекв", callback_data=f"edt_pay_{d_id}")],
        [InlineKeyboardButton(text="💰 Баланс", callback_data=f"edt_bal_{d_id}"), InlineKeyboardButton(text="🔑 Код", callback_data=f"edt_acc_{d_id}")],
        [InlineKeyboardButton(text=txt, callback_data=f"adm_act_{act}_{d_id}"), InlineKeyboardButton(text="💸 Выставить счет", callback_data=f"adm_act_bill_{d_id}")]
    ])
    await m.answer(f"✏️ <b>РЕДАКТОР: {info[0]}</b>\n🔑 Код: <code>{info[5]}</code>\n💰 Долг: {info[3]}₽", reply_markup=kb)

@dp.callback_query(F.data.startswith("edt_"))
async def edt_cb(c: types.CallbackQuery, state: FSMContext):
    parts = c.data.split("_")
    fmap = {"car":"car_info", "pay":"payment_info", "bal":"balance", "acc":"access_code"}
    await state.update_data(did=int(parts[2]), fld=fmap[parts[1]])
    await c.message.answer(f"✍️ Введи новое значение для {parts[1]}:")
    await state.set_state(AdminEditDriver.waiting_for_new_value)
    await c.answer()

@dp.message(AdminEditDriver.waiting_for_new_value)
async def edt_save(m: types.Message, state: FSMContext):
    data = await state.get_data()
    update_driver_field(data['did'], data['fld'], m.text)
    await m.answer("✅ Успешно сохранено.")
    await state.clear()

@dp.callback_query(F.data.startswith("adm_act_"))
async def adm_act(c: types.CallbackQuery):
    if c.from_user.id != BOSS_ID: return
    parts = c.data.split("_")
    act, d_id = parts[2], int(parts[3])
    
    if act == "block":
        update_driver_field(d_id, "status", "blocked")
        await c.message.edit_text("🔒 Водитель заблокирован.")
        try: await bot.send_message(d_id, "❌ Твой аккаунт временно заблокирован Боссом.")
        except: pass
    elif act == "unblock":
        update_driver_field(d_id, "status", "active")
        await c.message.edit_text("🔓 Водитель разблокирован.")
        try: await bot.send_message(d_id, "✅ Твой аккаунт снова активен!")
        except: pass
    elif act == "bill":
        info = get_driver_info(d_id)
        boss_info = get_driver_info(BOSS_ID)
        boss_req = boss_info[2] if boss_info else "Спроси у Босса"
        
        try: await bot.send_message(d_id, f"⚠️ <b>ВРЕМЯ ПЛАТИТЬ!</b>\nТвой долг: <b>{info[3]}₽</b>\nПереведи на карту Босса:\n💳 <b>{boss_req}</b>")
        except: pass
        await c.answer("Счет и реквизиты отправлены.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
