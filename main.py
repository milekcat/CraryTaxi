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
MASTER_INVITE_KEY = "CRAZY_START" # <--- ПАРОЛЬ ДЛЯ МГНОВЕННОГО НАЙМА

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
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            car_info TEXT,
            payment_info TEXT,
            access_code TEXT UNIQUE, 
            status TEXT DEFAULT 'pending',
            role TEXT DEFAULT 'driver',
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
    
    # Авто-регистрация ВЛАДЕЛЬЦА
    cursor.execute("SELECT 1 FROM drivers WHERE user_id = ?", (OWNER_ID,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO drivers (user_id, username, car_info, payment_info, access_code, status, role) VALUES (?, ?, ?, ?, ?, 'active', 'owner')",
            (OWNER_ID, "BOSS_NETWORK", "⚫ ЧЕРНАЯ ВОЛГА (БОСС)", "Яндекс Банк +79012723729", "BOSS")
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
    res = conn.execute("SELECT user_id, username, car_info FROM drivers WHERE access_code=? AND status='active'", (code,)).fetchone()
    conn.close()
    return res

def get_driver_info(user_id):
    conn = sqlite3.connect(DB_PATH)
    # 0:username, 1:car, 2:payment, 3:balance, 4:status, 5:code, 6:role
    res = conn.execute("SELECT username, car_info, payment_info, balance, status, access_code, role FROM drivers WHERE user_id=?", (user_id,)).fetchone()
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
    "candy": {"cat": 1, "price": 0, "name": "🍬 Конфетка", "desc": "Водитель с серьезным лицом вручает вам конфету."},
    "nose": {"cat": 1, "price": 300, "name": "👃 Палец в носу", "desc": "Водитель едет с пальцем в носу. Вы платите за его моральный ущерб."},
    "butler": {"cat": 1, "price": 200, "name": "🤵 Дворецкий", "desc": "Открывает дверь, кланяется, называет 'Сир'."},
    "joke": {"cat": 1, "price": 50, "name": "🤡 Тупой анекдот", "desc": "Анекдот категории Б. Смеяться желательно."},
    "silence": {"cat": 1, "price": 150, "name": "🤐 Тишина", "desc": "Музыка выкл, водитель молчит. Режим 'Монах'."},
    # LEVEL 2
    "granny": {"cat": 2, "price": 800, "name": "👵 Бабушка", "desc": "Буду бубнить: 'Шапку надень!', 'Наркоманы одни'."},
    "gopnik": {"cat": 2, "price": 500, "name": "🍺 Пацанчик", "desc": "Рэпчик, 'братишка', решение вопросиков по телефону."},
    "guide": {"cat": 2, "price": 600, "name": "🗣 Ужасный гид", "desc": "Экскурсия с выдуманными фактами."},
    "psych": {"cat": 2, "price": 1000, "name": "🧠 Психолог", "desc": "Вы жалуетесь, водитель кивает и дает советы."},
    # LEVEL 3
    "spy": {"cat": 3, "price": 2000, "name": "🕵️‍♂️ Шпион", "desc": "Черные очки, паранойя, проверка хвоста."},
    "karaoke": {"cat": 3, "price": 5000, "name": "🎤 Караоке", "desc": "Орем песни на полную. Фальшиво и душевно."},
    "dance": {"cat": 3, "price": 15000, "name": "💃 Танцы", "desc": "Водитель танцует макарену на светофоре."},
    # LEVEL 4
    "kidnap": {"cat": 4, "price": 30000, "name": "🎭 Похищение", "desc": "Понарошку пакуем в багажник и везем в лес пить чай."},
    "tarzan": {"cat": 4, "price": 50000, "name": "🦍 Тарзан", "desc": "Крики, удары в грудь, рычание на прохожих."},
    "burn": {"cat": 4, "price": 1000000, "name": "🔥 Сжечь авто", "desc": "Едем на пустырь и сжигаем машину. Эпик."},
    # LEVEL 5 (ДЛЯ ДАМ)
    "eyes": {"cat": 5, "price": 0, "name": "👁️ Глаз-алмаз", "desc": "Изысканный комплимент вашим глазам."},
    "smile": {"cat": 5, "price": 0, "name": "😁 Улыбка", "desc": "Комплимент вашей улыбке (бесплатно)."},
    "style": {"cat": 5, "price": 0, "name": "👠 Икона стиля", "desc": "Восхищение вашим образом. 'Вы с показа мод?'"},
    "improv": {"cat": 5, "price": 0, "name": "✨ Импровизация", "desc": "Водитель сам найдет, что в вас похвалить. Эксклюзив."},
    "propose": {"cat": 5, "price": 1000, "name": "💍 Предложение", "desc": "Вы делаете предложение водителю (руки/ипотеки). ⚠️ При отказе 1000₽ НЕ возвращаются!"}
}

CATEGORIES = {
    1: "🟢 ЛАЙТ (До 300₽)",
    2: "🟡 МЕДИУМ (Ролевые)",
    3: "🔴 ХАРД (Треш)",
    4: "☠️ VIP БЕЗУМИЕ",
    5: "🌹 ДЛЯ ДАМ (Спецраздел)"
}

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

class DriverRegistration(StatesGroup):
    waiting_for_car = State()
    waiting_for_payment_info = State()
    waiting_for_code = State()

class DriverVipRegistration(StatesGroup): # Для мгновенной регистрации
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
        "3. Наш адвокат уже выиграл суд у здравого смысла.\n\n"
        "Готов рискнуть?", reply_markup=tos_kb
    )

@dp.callback_query(F.data == "accept_tos")
async def tos_accepted(callback: types.CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (callback.from_user.id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("🔥 <b>КОНТРАКТ ПОДПИСАН!</b>")
    await callback.message.answer("Куда едем или что творим?", reply_markup=main_kb)

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
        "<i>Жми кнопку, если не боишься встречного иска.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚨 ПОЖАЛОВАТЬСЯ", callback_data="call_lawyer")]])
    )

@dp.callback_query(F.data == "call_lawyer")
async def alert_lawyer(callback: types.CallbackQuery):
    await callback.answer("🚨 Жалоба отправлена в шредер.", show_alert=True)

# ==========================================
# 🚀 МОНИТОРИНГ
# ==========================================
async def update_admins_monitor(client_id, taking_driver_id):
    order = active_orders.get(client_id)
    if not order or 'admin_msg_ids' not in order: return
    
    drv_info = get_driver_info(taking_driver_id)
    drv_name = f"@{drv_info[0]}" if drv_info[0] else "Unknown"
    
    taker_role = "👑 БОСС" if taking_driver_id == OWNER_ID else ("👮‍♂️ АДМИН" if is_admin(taking_driver_id) else "🚕 ВОДИТЕЛЬ")
    
    text = f"🚫 <b>ЗАКАЗ ЗАБРАЛ: {taker_role} {drv_name}</b>\nАвто: {drv_info[1]}\n\n{order.get('broadcasting_text','')}"
    
    for admin_id, msg_id in order['admin_msg_ids'].items():
        try: await bot.edit_message_text(chat_id=admin_id, message_id=msg_id, text=text, reply_markup=None)
        except: pass

async def broadcast_order_to_drivers(client_id, order_text, driver_kb, admin_kb):
    # 1. Админам
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

    # 2. Водителям
    search_msg = await bot.send_message(client_id, "📡 <i>Ищем водителей...</i>")
    await asyncio.sleep(1.5)
    
    all_active = get_active_drivers()
    simple_drivers = [d for d in all_active if d not in admins]
    
    if not simple_drivers and not admins:
        await search_msg.edit_text("😔 <b>Нет свободных машин на линии.</b>")
        return

    tasks = []
    for d_id in simple_drivers:
        tasks.append(bot.send_message(d_id, f"⚡ <b>ЗАКАЗ!</b>\n{order_text}", reply_markup=driver_kb))
    
    if tasks: await asyncio.gather(*tasks, return_exceptions=True)
    await search_msg.edit_text("⏳ <b>Запрос отправлен!</b> Ждем.")

# ==========================================
# 📜 МЕНЮ (КАТЕГОРИИ)
# ==========================================
@dp.message(F.text == "📜 CRAZY МЕНЮ (Категории)")
async def show_cats(message: types.Message):
    if not await check_tos(message): return
    if message.from_user.id not in client_driver_link:
        await message.answer("🔒 <b>ДОСТУП ЗАКРЫТ!</b>\nСядь в машину и введи код водителя.", reply_markup=main_kb)
        return
    
    btns = []
    for cat_id, cat_name in CATEGORIES.items():
        btns.append([InlineKeyboardButton(text=cat_name, callback_data=f"cat_{cat_id}")])
    await message.answer("🔥 <b>ВЫБЕРИ КАТЕГОРИЮ:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("cat_"))
async def open_cat(callback: types.CallbackQuery):
    cat_id = int(callback.data.split("_")[1])
    btns = []
    for k, v in CRAZY_SERVICES.items():
        if v["cat"] == cat_id:
            pr = "БЕСПЛАТНО" if v['price']==0 else f"{v['price']}₽"
            btns.append([InlineKeyboardButton(text=f"{v['name']} — {pr}", callback_data=f"csel_{k}")])
    btns.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_cats")])
    await callback.message.edit_text(f"📂 <b>{CATEGORIES[cat_id]}</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "back_cats")
async def back_cats(callback: types.CallbackQuery):
    btns = [[InlineKeyboardButton(text=n, callback_data=f"cat_{i}")] for i, n in CATEGORIES.items()]
    await callback.message.edit_text("🔥 <b>УРОВНИ:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("csel_"))
async def sel_srv(callback: types.CallbackQuery):
    key = callback.data.split("_")[1]
    srv = CRAZY_SERVICES[key]
    did = client_driver_link.get(callback.from_user.id)
    if not did: return
    
    pr_text = "БЕСПЛАТНО" if srv['price'] == 0 else f"{srv['price']}₽"
    text = f"🎭 <b>{srv['name']}</b>\n💰 <b>{pr_text}</b>\n\n📝 <i>{srv['desc']}</i>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ЗАКАЗАТЬ", callback_data=f"do_order_{key}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"cat_{srv['cat']}")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("do_order_"))
async def do_order(callback: types.CallbackQuery):
    key = callback.data.split("_")[1]
    srv = CRAZY_SERVICES[key]
    cid, did = callback.from_user.id, client_driver_link.get(callback.from_user.id)
    
    active_orders[cid] = {"type": "crazy", "status": "direct", "price": str(srv["price"]), "driver_id": did, "service": srv}
    await callback.message.edit_text(f"⏳ <b>Отправляем заказ водителю...</b>")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"drv_acc_{cid}")]])
    await bot.send_message(did, f"🔔 <b>ПЕРСОНАЛЬНЫЙ ЗАКАЗ</b>\n\n🎭 <b>{srv['name']}</b>\n💰 <b>{srv['price']}₽</b>\n📝 {srv['desc']}", reply_markup=kb)
    await notify_admins(f"👀 <b>СДЕЛКА ВНУТРИ АВТО:</b> Клиент заказал '{srv['name']}' у водителя {did}")

@dp.callback_query(F.data.startswith("drv_acc_"))
async def drv_acc(callback: types.CallbackQuery):
    cid = int(callback.data.split("_")[2])
    order = active_orders.get(cid)
    if not order: return
    
    info = get_driver_info(callback.from_user.id)
    pr = extract_price(order['price'])
    
    if pr == 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ УСЛУГУ ПОЛУЧИЛ", callback_data=f"cli_pay_{cid}")]])
        await bot.send_message(cid, "✅ <b>Водитель принял!</b>\n🎁 Услуга бесплатная.", reply_markup=kb)
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Я ОПЛАТИЛ", callback_data=f"cli_pay_{cid}")]])
        await bot.send_message(cid, f"✅ <b>Водитель готов!</b>\n💳 Переведи <b>{pr}₽</b> сюда:\n<code>{info[2]}</code>", reply_markup=kb)
    await callback.message.edit_text("✅ Принято. Жди клиента.")

@dp.callback_query(F.data.startswith("cli_pay_"))
async def cli_pay(callback: types.CallbackQuery):
    cid = callback.from_user.id
    order = active_orders.get(cid)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ДЕНЬГИ ПРИШЛИ / ГОТОВО", callback_data=f"drv_fin_{cid}")]])
    await callback.message.edit_text("⏳ Ждем водителя...")
    await bot.send_message(order["driver_id"], "💸 <b>Клиент подтвердил оплату!</b>\nПроверь и завершай.", reply_markup=kb)

@dp.callback_query(F.data.startswith("drv_fin_"))
async def drv_fin(callback: types.CallbackQuery):
    cid = int(callback.data.split("_")[2])
    did = callback.from_user.id
    order = active_orders.get(cid)
    pr = extract_price(order['price'])
    add_commission(did, pr)
    log_order(did, order['service']['name'], pr)
    await callback.message.edit_text("✅ <b>Закрыто.</b>")
    await bot.send_message(cid, "🎉 <b>Услуга выполнена!</b>")
    del active_orders[cid]

# ==========================================
# 🚕 ТАКСИ + ТОРГ
# ==========================================
@dp.message(F.text == "🚕 Заказать такси (Поиск)")
async def taxi_start(message: types.Message, state: FSMContext):
    await message.answer("📍 <b>Откуда?</b>", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(OrderRide.waiting_for_from)

@dp.message(OrderRide.waiting_for_from)
async def taxi_fr(message: types.Message, state: FSMContext):
    await state.update_data(fr=message.text)
    await message.answer("🏁 <b>Куда?</b>")
    await state.set_state(OrderRide.waiting_for_to)

@dp.message(OrderRide.waiting_for_to)
async def taxi_to(message: types.Message, state: FSMContext):
    await state.update_data(to=message.text)
    await message.answer("📞 <b>Телефон:</b>")
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
    await message.answer("✅ <b>Ищем...</b>", reply_markup=main_kb)
    await state.clear()
    
    text = f"🚕 <b>ЗАКАЗ ТАКСИ</b>\n📍 {data['fr']} -> {data['to']}\n💰 {message.text}"
    dkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ЗАБРАТЬ", callback_data=f"take_taxi_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"cnt_taxi_{cid}")]])
    akb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ЗАБРАТЬ (АДМИН)", callback_data=f"adm_take_taxi_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"cnt_taxi_{cid}")]])
    await broadcast_order_to_drivers(cid, text, dkb, akb)

@dp.callback_query(F.data.startswith("take_taxi_") | F.data.startswith("adm_take_taxi_"))
async def take_taxi(callback: types.CallbackQuery):
    cid = int(callback.data.split("_")[-1])
    did = callback.from_user.id
    order = active_orders.get(cid)
    
    if not order or order["status"] != "pending":
        await callback.answer("Упс! Занято.", show_alert=True)
        return
        
    order["status"] = "accepted"
    order["driver_id"] = did
    client_driver_link[cid] = did
    await update_admins_monitor(cid, did)
    
    info = get_driver_info(did)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ЗАВЕРШИТЬ", callback_data=f"fin_taxi_{cid}")]])
    await callback.message.edit_text(f"✅ <b>Взято!</b>\n📞 {order['phone']}", reply_markup=kb)
    await bot.send_message(cid, f"🚕 <b>ВОДИТЕЛЬ ЕДЕТ!</b>\n👤 {info[0]} ({info[1]})\n📞 {order['phone']}\n🔐 Код: <code>{info[5]}</code>")

@dp.callback_query(F.data.startswith("fin_taxi_"))
async def fin_taxi(callback: types.CallbackQuery):
    cid = int(callback.data.split("_")[2])
    did = callback.from_user.id
    order = active_orders.get(cid)
    pr = extract_price(order['price'])
    add_commission(did, pr)
    log_order(did, "Такси", pr)
    await callback.message.edit_text("✅ Завершено.")
    await bot.send_message(cid, "🏁 Приехали!")
    del active_orders[cid]

# ==========================================
# 💡 ИДЕЯ + ТОРГ
# ==========================================
@dp.message(F.text == "💡 Свой вариант (Идея)")
async def idea_st(message: types.Message, state: FSMContext):
    await message.answer("Суть идеи:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(CustomIdea.waiting_for_idea)

@dp.message(CustomIdea.waiting_for_idea)
async def idea_pr(message: types.Message, state: FSMContext):
    await state.update_data(idea=message.text)
    await message.answer("Бюджет?")
    await state.set_state(CustomIdea.waiting_for_price)

@dp.message(CustomIdea.waiting_for_price)
async def idea_snd(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cid = message.from_user.id
    active_orders[cid] = {"type": "crazy", "status": "pending", "price": message.text, "service": {"name": "Идея", "desc": data['idea']}, "driver_offers": {}}
    await message.answer("✅ Отправлено!", reply_markup=main_kb)
    await state.clear()
    
    text = f"💡 <b>ИДЕЯ</b>\n📝 {data['idea']}\n💰 {message.text}"
    dkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ЗАБРАТЬ", callback_data=f"take_crazy_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"cnt_crazy_{cid}")]])
    akb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ АДМИН ЗАБРАТЬ", callback_data=f"adm_take_crazy_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"cnt_crazy_{cid}")]])
    await broadcast_order_to_drivers(cid, text, dkb, akb)

@dp.callback_query(F.data.startswith("take_crazy_") | F.data.startswith("adm_take_crazy_"))
async def take_crazy_gen(callback: types.CallbackQuery):
    cid = int(callback.data.split("_")[-1])
    did = callback.from_user.id
    active_orders[cid]["status"] = "accepted"
    active_orders[cid]["driver_id"] = did
    client_driver_link[cid] = did
    await update_admins_monitor(cid, did)
    info = get_driver_info(did)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 ОПЛАТИЛ", callback_data=f"cpay_done_{cid}")]])
    await callback.message.edit_text("✅ Взято.")
    await bot.send_message(cid, f"✅ Исполнитель: {info[0]}\n💳 {info[2]}\n🔐 {info[5]}", reply_markup=kb)

@dp.callback_query(F.data.startswith("cnt_"))
async def start_cnt(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    await state.update_data(cid=int(parts[2]), type=parts[1])
    await callback.message.answer("Твоя цена и условия:")
    await state.set_state(DriverCounterOffer.waiting_for_offer)
    await callback.answer()

@dp.message(DriverCounterOffer.waiting_for_offer)
async def send_cnt(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cid, did = data['cid'], message.from_user.id
    order = active_orders.get(cid)
    if not order: return
    order.setdefault("driver_offers", {})[did] = message.text
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Да", callback_data=f"ok_off_{data['type']}_{cid}_{did}"), InlineKeyboardButton(text="❌ Нет", callback_data=f"no_off_{cid}")]])
    role_label = "АДМИН" if is_admin(did) else "Водитель"
    await bot.send_message(cid, f"⚡️ <b>{role_label} предлагает:</b>\n{message.text}", reply_markup=kb)
    await message.answer("Отправлено.")
    await state.clear()

@dp.callback_query(F.data.startswith("ok_off_"))
async def ok_off(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    cid, did = int(parts[3]), int(parts[4])
    order = active_orders.get(cid)
    order["status"] = "accepted"
    order["driver_id"] = did
    order["price"] = order["driver_offers"].get(did, order["price"])
    client_driver_link[cid] = did
    await update_admins_monitor(cid, did)
    info = get_driver_info(did)
    
    if parts[2] == "taxi":
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ЗАВЕРШИТЬ", callback_data=f"fin_taxi_{cid}")]])
        await bot.send_message(did, f"✅ Клиент согласен!\n📞 {order['phone']}", reply_markup=kb)
        await callback.message.edit_text(f"🚕 <b>Едет: {info[0]}</b>\n🔐 {info[5]}")
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 ОПЛАТИЛ", callback_data=f"cpay_done_{cid}")]])
        await callback.message.edit_text(f"🤝 <b>ОК!</b>\n💳 {info[2]}\n🔐 {info[5]}", reply_markup=kb)
        await bot.send_message(did, "✅ Клиент согласен!")

@dp.callback_query(F.data.startswith("no_off_"))
async def no_off(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Отказ.")

# ==========================================
# 🪪 КАБИНЕТ + РЕГИСТРАЦИЯ
# ==========================================
@dp.message(Command("cab"))
async def cab(message: types.Message):
    info = get_driver_info(message.from_user.id)
    if not info:
        await message.answer("❌ Нет доступа. /drive")
        return
    if info[4] != 'active': # Status
        await message.answer(f"❌ Статус: {info[4]}")
        return
        
    conn = sqlite3.connect(DB_PATH)
    hist = conn.execute("SELECT COUNT(*), SUM(price) FROM order_history WHERE driver_id=?", (message.from_user.id,)).fetchone()
    conn.close()
    
    roles = {'owner':"👑 ВЛАДЕЛЕЦ", 'admin':"👮‍♂️ АДМИН", 'driver':"🚕 ВОДИТЕЛЬ"}
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Сменить код", callback_data="cab_chg")],
        [InlineKeyboardButton(text="💸 Оплатить долг", callback_data="cab_pay")]
    ])
    await message.answer(f"🪪 <b>КАБИНЕТ</b>\nСтатус: {roles.get(info[6])}\n👤 {info[0]}\n🚘 {info[1]}\n🔑 {info[5]}\n💰 Долг: {info[3]}₽\n📊 Всего: {hist[1] or 0}₽", reply_markup=kb)

@dp.callback_query(F.data == "cab_chg")
async def cab_chg(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Новый код:")
    await state.set_state(DriverChangeCode.waiting_for_new_code)
    await callback.answer()

@dp.message(DriverChangeCode.waiting_for_new_code)
async def cab_save_code(message: types.Message, state: FSMContext):
    try: update_driver_field(message.from_user.id, "access_code", message.text.upper().strip())
    except: 
        await message.answer("Занят.")
        return
    await message.answer("✅")
    await state.clear()

@dp.callback_query(F.data == "cab_pay")
async def cab_pay(callback: types.CallbackQuery):
    info = get_driver_info(callback.from_user.id)
    boss = get_driver_info(OWNER_ID)
    await callback.message.answer(f"💸 Долг: <b>{info[3]}₽</b>\nПереведи Боссу: <b>{boss[2]}</b>")
    await callback.answer()

# ✅ РЕГИСТРАЦИЯ
@dp.message(Command("driver", "drive"))
async def reg_start(message: types.Message, state: FSMContext):
    info = get_driver_info(message.from_user.id)
    if info:
        if info[4]=='active': await message.answer("Уже в базе. /cab")
        else: await message.answer("Жди одобрения.")
        return
    await message.answer("🚕 Авто:")
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
        conn.execute("INSERT INTO drivers (user_id, username, car_info, payment_info, access_code, status) VALUES (?, ?, ?, ?, ?, 'pending')", 
                     (message.from_user.id, message.from_user.username, data['car'], data['pay'], code))
        conn.commit()
        await message.answer("📝 Отправлено.")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ОДОБРИТЬ", callback_data=f"adm_app_{message.from_user.id}")]])
        await notify_admins(f"🚨 <b>НОВЫЙ</b>\n@{message.from_user.username}\n{data['car']}", kb)
    except:
        await message.answer("❌ Код занят.")
    finally: conn.close()
    await state.clear()

# 🔥 БЫСТРЫЙ ВХОД ПО КЛЮЧУ
@dp.message(Command("vip"))
async def vip_reg(message: types.Message, state: FSMContext):
    try:
        key = message.text.split()[1]
        if key == MASTER_INVITE_KEY:
            await message.answer("🔑 <b>VIP КЛЮЧ ПРИНЯТ!</b>\nЗаполняем анкету.\n\n🚕 Твоя машина:")
            await state.set_state(DriverVipRegistration.waiting_for_car)
        else:
            await message.answer("❌ Неверный ключ.")
    except:
        await message.answer("Пиши: /vip КОД")

@dp.message(DriverVipRegistration.waiting_for_car)
async def vip_car(message: types.Message, state: FSMContext):
    await state.update_data(car=message.text)
    await message.answer("💳 Реквизиты:")
    await state.set_state(DriverVipRegistration.waiting_for_payment_info)

@dp.message(DriverVipRegistration.waiting_for_payment_info)
async def vip_pay(message: types.Message, state: FSMContext):
    await state.update_data(pay=message.text)
    await message.answer("🔑 Придумай свой код:")
    await state.set_state(DriverVipRegistration.waiting_for_code)

@dp.message(DriverVipRegistration.waiting_for_code)
async def vip_fin(message: types.Message, state: FSMContext):
    code = message.text.upper().strip()
    data = await state.get_data()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO drivers (user_id, username, car_info, payment_info, access_code, status) VALUES (?, ?, ?, ?, ?, 'active')", 
                     (message.from_user.id, message.from_user.username, data['car'], data['pay'], code))
        conn.commit()
        await message.answer("🚀 <b>ТЫ В ИГРЕ!</b>\nСтатус: ACTIVE. Жми /cab")
        await notify_admins(f"⭐ <b>VIP РЕГИСТРАЦИЯ</b>\n@{message.from_user.username}")
    except:
        await message.answer("❌ Код занят.")
    finally: conn.close()
    await state.clear()

# ==========================================
# 👑 АДМИНКА
# ==========================================
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id): return
    conn = sqlite3.connect(DB_PATH)
    drs = conn.execute("SELECT user_id, username, balance, role, status FROM drivers").fetchall()
    conn.close()
    txt = "👑 <b>АДМИНКА</b>\n"
    for d in drs:
        ic = "🔒" if d[4]=='blocked' else ("👑" if d[3]=='owner' else ("👮" if d[3]=='admin' else "🚕"))
        txt += f"{ic} {d[1]} | {d[2]}₽ | /edit_{d[0]}\n"
    await message.answer(txt)

@dp.message(Command("setadmin"))
async def set_ad(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    try:
        tid = int(message.text.split()[1])
        update_driver_field(tid, "role", "admin")
        await message.answer("✅ Назначен админом.")
        await bot.send_message(tid, "👮‍♂️ Ты теперь АДМИН!")
    except: pass

@dp.message(Command("deladmin"))
async def del_ad(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    try:
        tid = int(message.text.split()[1])
        update_driver_field(tid, "role", "driver")
        await message.answer("✅ Разжалован.")
    except: pass

@dp.callback_query(F.data.startswith("adm_app_"))
async def adm_app(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    did = int(callback.data.split("_")[2])
    update_driver_field(did, "status", "active")
    await callback.message.edit_text("✅ Одобрено.")
    try: await bot.send_message(did, "🎉 Принят! /cab")
    except: pass

@dp.message(F.text.startswith("/edit_"))
async def edit_d(message: types.Message):
    if not is_admin(message.from_user.id): return
    try: did = int(message.text.split("_")[1])
    except: return
    info = get_driver_info(did)
    if info[6]=='owner' and message.from_user.id!=OWNER_ID: 
        await message.answer("Нельзя.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Баланс", callback_data=f"edt_bal_{did}"), InlineKeyboardButton(text="Счет", callback_data=f"adm_bill_{did}")],
        [InlineKeyboardButton(text="Блок/Разблок", callback_data=f"adm_block_{did}")]
    ])
    await message.answer(f"Ред: {info[0]}", reply_markup=kb)

@dp.callback_query(F.data.startswith("edt_"))
async def edt_st(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.update_data(did=int(callback.data.split("_")[2]), fld="balance")
    await callback.message.answer("Новое значение:")
    await state.set_state(AdminEditDriver.waiting_for_new_value)
    await callback.answer()

@dp.message(AdminEditDriver.waiting_for_new_value)
async def edt_sv(message: types.Message, state: FSMContext):
    d = await state.get_data()
    update_driver_field(d['did'], d['fld'], message.text)
    await message.answer("✅")
    await state.clear()

@dp.callback_query(F.data.startswith("adm_"))
async def adm_act(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    parts = callback.data.split("_")
    did = int(parts[2])
    if parts[1] == "bill":
        boss = get_driver_info(OWNER_ID)
        info = get_driver_info(did)
        try: await bot.send_message(did, f"⚠️ ДОЛГ: {info[3]}₽\nРеквизиты: {boss[2]}")
        except: pass
        await callback.answer("Счет отправлен.")
    elif parts[1] == "block":
        if get_driver_info(did)[6] == 'owner': return
        cur = get_driver_info(did)[4]
        new_s = "blocked" if cur=="active" else "active"
        update_driver_field(did, "status", new_s)
        await callback.message.edit_text(f"Статус: {new_s}")

# ==========================================
# 🔐 КЛЮЧ
# ==========================================
@dp.message(F.text == "🔐 Ввести КЛЮЧ услуги")
async def ask_key(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    await message.answer("Код водителя:")
    await state.set_state(UnlockMenu.waiting_for_key)

@dp.message(UnlockMenu.waiting_for_key)
async def proc_key(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    drv = get_driver_by_code(code)
    if drv:
        client_driver_link[message.from_user.id] = drv[0]
        await message.answer(f"🔓 <b>ОК!</b>\n🚘 {drv[2]}\n👤 {drv[1]}", reply_markup=main_kb)
        await state.clear()
    else: await message.answer("❌ Неверно.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
