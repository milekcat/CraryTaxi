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

# ==========================================
# ⚙️ НАСТРОЙКИ СИСТЕМЫ
# ==========================================
logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("API_TOKEN")
OWNER_ID_STR = os.getenv("DRIVER_ID") 

if not API_TOKEN or not OWNER_ID_STR:
    exit("⛔ ОШИБКА: API_TOKEN или DRIVER_ID не найдены!")

OWNER_ID = int(OWNER_ID_STR)
SECOND_ADMIN_ID = 6004764782
# Супер-админы (Железный доступ)
SUPER_ADMINS = [OWNER_ID, SECOND_ADMIN_ID]

VIP_DRIVER_KEY = "CRAZY_START"
LAWYER_LINK = "https://t.me/Ai_advokatrobot"

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

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
    cursor.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY)")
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
    for admin_id in SUPER_ADMINS:
        cursor.execute("SELECT 1 FROM drivers WHERE user_id = ?", (admin_id,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, role, balance, rating_sum, rating_count, commission) VALUES (?, ?, ?, ?, ?, ?, 'active', 'owner', 0, 0, 0, 0)",
                (admin_id, "BOSS", "Админ Сервиса", "Black Volga VIP", "CASH", f"ADMIN_{admin_id}")
            )
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 🛠 УТИЛИТЫ
# ==========================================

def get_all_admins_ids():
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT user_id FROM drivers WHERE role IN ('owner', 'admin') AND status='active'").fetchall()
    conn.close()
    return list(set([r[0] for r in res] + SUPER_ADMINS))

def is_admin(user_id):
    if user_id in SUPER_ADMINS: return True
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT 1 FROM drivers WHERE user_id=? AND role IN ('owner', 'admin') AND status='active'", (user_id,)).fetchone()
    conn.close()
    return bool(res)

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

def extract_price(text):
    nums = re.findall(r'\d+', str(text))
    return int("".join(nums)) if nums else 0

# ==========================================
# 📜 ПОЛНОЕ МЕНЮ (ВСЕ ТЕКСТЫ)
# ==========================================
CRAZY_SERVICES = {
    "candy": {"cat": 1, "price": 0, "name": "🍬 Конфетка", "desc": "Водитель с максимально серьезным лицом (как на государственных похоронах) вручает вам элитную барбариску. Это знак глубочайшего уважения и начала крепкой дружбы."},
    "nose": {"cat": 1, "price": 300, "name": "👃 Палец в носу", "desc": "Всю поездку (или до первого поста ГАИ) водитель едет с пальцем в носу. Вы платите за его моральные страдания, потерю авторитета и ваш истерический смех."},
    "butler": {"cat": 1, "price": 200, "name": "🤵 Дворецкий", "desc": "Водитель выходит, картинно открывает вам дверь, кланяется в пояс и называет вас 'Сир' или 'Миледи'. Чувство превосходства включено в стоимость."},
    "joke": {"cat": 1, "price": 50, "name": "🤡 Тупой анекдот", "desc": "Анекдот категории 'Б' из золотой коллекции таксиста 90-х. Смеяться не обязательно, но желательно, чтобы не обидеть тонкую творческую натуру водителя."},
    "silence": {"cat": 1, "price": 150, "name": "🤐 Полная тишина", "desc": "Режим 'Ниндзя'. Музыка выключается, водитель молчит как рыба. Даже если вы спросите дорогу — он ответит языком жестов. Идеально для интровертов."},
    "granny": {"cat": 2, "price": 800, "name": "👵 Бабушка-ворчунья", "desc": "Ролевая игра. Всю дорогу водитель будет бубнить: 'Куда прешь, наркоман?', 'Шапку надень!', 'Вот в наше время такси стоило копейку!'. Полное погружение в детство."},
    "gopnik": {"cat": 2, "price": 500, "name": "🍺 Четкий пацанчик", "desc": "Едем под пацанский рэп, водитель сидит на корточках (шутка, за рулем), называет вас 'Братишка', лузгает семечки и решает вопросики по телефону."},
    "guide": {"cat": 2, "price": 600, "name": "🗣 Ужасный гид", "desc": "Водитель проводит экскурсию, на ходу выдумывая факты. 'Вот этот ларек построил Иван Грозный лично'. Чем бредовее факты, тем лучше."},
    "psych": {"cat": 2, "price": 1000, "name": "🧠 Психолог", "desc": "Вы жалуетесь на жизнь, бывших и начальника. Водитель кивает, говорит 'Угу', вздыхает и дает житейские советы уровня Ошо."},
    "spy": {"cat": 3, "price": 2000, "name": "🕵️‍♂️ Шпион 007", "desc": "Черные очки, паранойя. Водитель постоянно проверяет 'хвост', говорит по рации кодами ('Орел в гнезде') и прячет лицо от камер."},
    "karaoke": {"cat": 3, "price": 5000, "name": "🎤 Адское Караоке", "desc": "Врубаем 'Рюмку водки' или 'Знаешь ли ты' на полную! Водитель орет песни вместе с вами. Фальшиво, громко, но очень душевно."},
    "dance": {"cat": 3, "price": 15000, "name": "💃 Танцы на капоте", "desc": "На красном свете водитель выбегает из машины и танцует макарену или лезгинку перед капотом. Прохожие снимают, вам стыдно, всем весело!"},
    "kidnap": {"cat": 4, "price": 30000, "name": "🎭 Дружеское похищение", "desc": "Вас (понарошку, но реалистично) грузят в багажник (или на заднее), надевают мешок на голову и везут в лес... пить элитный чай с баранками."},
    "tarzan": {"cat": 4, "price": 50000, "name": "🦍 Тарзан-Шоу", "desc": "Водитель бьет себя в грудь, рычит на прохожих и называет другие машины 'железными буйволами'. Санитары уже выехали."},
    "burn": {"cat": 4, "price": 1000000, "name": "🔥 Сжечь машину", "desc": "Финальный аккорд. Едем на пустырь. Вы платите миллион, я даю канистру. Гори оно всё огнем. Эпичный финал."},
    "eyes": {"cat": 5, "price": 0, "name": "👁️ Глаз-алмаз", "desc": "Водитель сделает изысканный комплимент вашим глазам. Возможно, сравнит их с звездами или фарами ксенона."},
    "smile": {"cat": 5, "price": 0, "name": "😁 Улыбка Джоконды", "desc": "Водитель скажет, что ваша улыбка освещает этот старый, пыльный салон лучше, чем аварийка в ночи."},
    "style": {"cat": 5, "price": 0, "name": "👠 Икона стиля", "desc": "Восхищение вашим образом. Водитель поинтересуется, не едете ли вы случайно с показа мод в Париже."},
    "improv": {"cat": 5, "price": 0, "name": "✨ Импровизация", "desc": "Водитель сам найдет, что в вас похвалить. Рискованно, но приятно. Полный фристайл и галантность."},
    "propose": {"cat": 5, "price": 1000, "name": "💍 Сделать предложение", "desc": "Вы делаете предложение руки, сердца или ипотеки водителю. Шанс 50/50. ⚠️ ПРИ ОТКАЗЕ 1000₽ НЕ ВОЗВРАЩАЮТСЯ!"}
}

CATEGORIES = {1: "🟢 ЛАЙТ", 2: "🟡 МЕДИУМ", 3: "🔴 ХАРД", 4: "☠️ VIP БЕЗУМИЕ", 5: "🌹 ДЛЯ ДАМ"}

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
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT 1 FROM clients WHERE user_id = ?", (message.from_user.id,)).fetchone()
    conn.close()
    if res:
        await message.answer("⚠️ <b>CRAZY TAXI: С возвращением!</b>\nДвери заблокированы, шоу продолжается.", reply_markup=main_kb)
    else:
        await message.answer(
            "⚠️ <b>CRAZY TAXI: ЗОНА ПОВЫШЕННОГО РИСКА</b>\n\n"
            "Мы не возим скучных людей. Мы продаем эмоции и истории.\n\n"
            "<b>📜 Правила нашего клуба:</b>\n"
            "1. Что происходит в такси — остается в такси.\n"
            "2. Водитель — непризнанный гений и художник, салон — его холст.\n"
            "3. Наш юридический отдел уже выиграл суд у здравого смысла.\n\n"
            "Готовы рискнуть рассудком ради поездки?", reply_markup=tos_kb
        )

@dp.callback_query(F.data == "accept_tos")
async def tos_accepted(callback: types.CallbackQuery, state: FSMContext):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (callback.from_user.id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("🔥 <b>КОНТРАКТ ПОДПИСАН!</b>")
    await callback.message.answer("Добро пожаловать в сервис доп. услуг. Выбирай 👇", reply_markup=main_kb)

@dp.message(F.text == "⚖️ Вызвать адвоката")
async def lawyer_menu(message: types.Message, state: FSMContext):
    await message.answer("⚖️ <b>ЮРИДИЧЕСКИЙ ОТДЕЛ</b>\nПартнер — цифровой юрист:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚨 ПЕРЕЙТИ К АДВОКАТУ", url=LAWYER_LINK)]]))

# ==========================================
# 🚕 ТАКСИ + ОПЛАТА
# ==========================================
@dp.message(F.text == "🚕 Заказать такси (Поиск)")
async def taxi_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("📍 <b>Откуда вас забрать?</b>", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(OrderRide.waiting_for_from)

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
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ВЗЯТЬ", callback_data=f"t_ok_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"t_bid_{cid}")]])
    
    admins = get_all_admins_ids()
    for adm in admins: await bot.send_message(adm, f"🚨 <b>МОНИТОРИНГ</b>\n{txt}", reply_markup=kb)
    for drv in [d[0] for d in sqlite3.connect(DB_PATH).execute("SELECT user_id FROM drivers WHERE status='active'").fetchall()]:
        if drv not in SUPER_ADMINS: await bot.send_message(drv, txt, reply_markup=kb)

@dp.callback_query(F.data.startswith("t_ok_"))
async def taxi_take(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2]); did = callback.from_user.id; order = active_orders.get(cid)
    if not order or order["status"] != "pending": return await callback.answer("Уже занято!")
    
    order["status"] = "accepted"; order["driver_id"] = did; client_driver_link[cid] = did
    info = get_driver_info(did)
    
    # Кнопка завершения для водителя
    drv_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ", callback_data=f"ask_fin_{cid}")]])
    await callback.message.edit_text(f"✅ Взято! Телефон: {order['phone']}", reply_markup=drv_kb)
    
    # Кнопки для клиента
    cli_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Я ОПЛАТИЛ", callback_data=f"c_paid_{cid}")],
        [InlineKeyboardButton(text="➕ ДОБАВИТЬ ТОЧКУ", callback_data="add_s")]
    ])
    await bot.send_message(cid, f"🚕 <b>Едет: {info[7]}</b>\n🚘 {info[1]}\n💳 Реквизиты: <code>{info[2]}</code>\n🔐 Код: <code>{info[5]}</code>", reply_markup=cli_kb)

# --- ЛОГИКА ОПЛАТЫ ---
@dp.callback_query(F.data.startswith("c_paid_"))
async def client_paid(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2]); order = active_orders.get(cid)
    await callback.message.edit_text("⏳ Ждем подтверждения оплаты водителем...")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ДЕНЬГИ ПРИШЛИ", callback_data=f"d_confirm_{cid}")]])
    await bot.send_message(order["driver_id"], "💸 <b>Клиент нажал 'Оплачено'!</b> Подтвердите получение:", reply_markup=kb)

@dp.callback_query(F.data.startswith("d_confirm_"))
async def driver_confirm(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2]); order = active_orders.get(cid)
    await callback.message.edit_text("✅ Оплата подтверждена. Не забудьте завершить поездку в конце.")
    await bot.send_message(cid, "💎 <b>Оплата получена!</b> Приятной поездки.")

# ==========================================
# 📜 CRAZY МЕНЮ (ПОЛНОЕ)
# ==========================================
@dp.message(F.text == "📜 CRAZY МЕНЮ (Категории)")
async def show_cats(message: types.Message, state: FSMContext):
    if message.from_user.id not in client_driver_link: return await message.answer("🔒 Введите код водителя!")
    btns = [[InlineKeyboardButton(text=v, callback_data=f"cat_{k}")] for k, v in CATEGORIES.items()]
    await message.answer("🔥 <b>ВЫБЕРИТЕ УРОВЕНЬ ЖЕСТКОСТИ:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("cat_"))
async def open_cat(callback: types.CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[1])
    btns = [[InlineKeyboardButton(text=f"{v['name']} - {v['price']}₽", callback_data=f"srv_{k}")] for k, v in CRAZY_SERVICES.items() if v['cat']==cat_id]
    btns.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_c")])
    await callback.message.edit_text(f"📂 <b>{CATEGORIES[cat_id]}</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("srv_"))
async def sel_srv(callback: types.CallbackQuery, state: FSMContext):
    key = callback.data.split("_")[1]; srv = CRAZY_SERVICES[key]
    txt = f"🎭 <b>{srv['name']}</b>\n💰 <b>{srv['price']}₽</b>\n\n<i>{srv['desc']}</i>"
    kb = [[InlineKeyboardButton(text="✅ ЗАКАЗАТЬ", callback_data=f"do_{key}")], [InlineKeyboardButton(text="🔙 Назад", callback_data=f"cat_{srv['cat']}")]]
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("do_"))
async def do_order(callback: types.CallbackQuery, state: FSMContext):
    key = callback.data.split("_")[1]; srv = CRAZY_SERVICES[key]; cid = callback.from_user.id; did = client_driver_link.get(cid)
    active_orders[cid] = {"type": "crazy", "price": str(srv["price"]), "driver_id": did, "service": srv}
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"c_acc_{cid}")]])
    await bot.send_message(did, f"🔔 <b>ЗАКАЗ: {srv['name']}</b>\n💰 {srv['price']}₽", reply_markup=kb)
    await callback.message.edit_text("⏳ Запрос отправлен пилоту...")

@dp.callback_query(F.data.startswith("c_acc_"))
async def crazy_accept(callback: types.CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2]); info = get_driver_info(callback.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Я ОПЛАТИЛ", callback_data=f"c_paid_{cid}")]])
    await bot.send_message(cid, f"✅ Пилот готов! Перевод: <code>{info[2]}</code>", reply_markup=kb)
    await callback.message.edit_text("✅ Вы приняли вызов. Ожидайте оплату.")

# ==========================================
# 🪪 КАБИНЕТ + РЕГИСТРАЦИЯ (ИСПРАВЛЕНО)
# ==========================================
@dp.message(Command("cab"))
async def cab(message: types.Message, state: FSMContext):
    await state.clear(); info = get_driver_info(message.from_user.id)
    if not info: return await message.answer("❌ Нет регистрации. /drive")
    
    role_map = {'owner':"👑 БОСС", 'admin':"👮‍♂️ АДМИН", 'driver':"🚕 ВОДИТЕЛЬ"}
    txt = (f"🪪 <b>КАБИНЕТ ПИЛОТА</b>\n🔰 Роль: {role_map.get(info[6])}\n👤 {info[7]}\n"
           f"💰 Баланс: {info[3]}₽\n📊 Комиссия: {info[10]}%\n🔑 Код: <code>{info[5]}</code>")
    kb = [[InlineKeyboardButton(text="🔄 Сменить код", callback_data="chg_c")], [InlineKeyboardButton(text="💸 Оплатить долг", callback_data="pay_d")]]
    await message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.message(Command("driver", "drive"))
async def reg_start(message: types.Message, state: FSMContext):
    await state.clear(); await message.answer("📝 Введите ваше ФИО:"); await state.set_state(DriverRegistration.waiting_for_fio)

@dp.message(DriverRegistration.waiting_for_fio)
async def r1(m: types.Message, state: FSMContext): await state.update_data(fio=m.text); await m.answer("🚘 Авто:"); await state.set_state(DriverRegistration.waiting_for_car)
@dp.message(DriverRegistration.waiting_for_car)
async def r2(m: types.Message, state: FSMContext): await state.update_data(car=m.text); await m.answer("💳 Реквизиты:"); await state.set_state(DriverRegistration.waiting_for_payment_info)
@dp.message(DriverRegistration.waiting_for_payment_info)
async def r3(m: types.Message, state: FSMContext): await state.update_data(pay=m.text); await m.answer("🔑 Код-пароль:"); await state.set_state(DriverRegistration.waiting_for_code)
@dp.message(DriverRegistration.waiting_for_code)
async def r4(message: types.Message, state: FSMContext):
    d = await state.get_data(); code = message.text.upper().strip(); conn = sqlite3.connect(DB_PATH)
    try:
        # Исправленный INSERT (12 полей)
        conn.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, role, balance, rating_sum, rating_count, commission) VALUES (?, ?, ?, ?, ?, ?, 'pending', 'driver', 0, 0, 0, 10)", 
                     (message.from_user.id, message.from_user.username, d['fio'], d['car'], d['pay'], code))
        conn.commit(); await message.answer("✅ Анкета отправлена! Ожидайте одобрения."); await notify_admins(f"🚨 <b>НОВЫЙ:</b> {d['fio']}")
    except: await message.answer("❌ Ошибка: Код уже занят.")
    conn.close(); await state.clear()

# ==========================================
# 👑 АДМИНКА
# ==========================================
@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id): return await message.answer("⛔ Доступ запрещен.")
    conn = sqlite3.connect(DB_PATH); drs = conn.execute("SELECT user_id, fio, balance FROM drivers").fetchall(); conn.close()
    txt = "👑 <b>АДМИН-ПАНЕЛЬ</b>\n"
    for d in drs: txt += f"• {d[1]} | {d[2]}₽ | /edit_{d[0]}\n"
    await message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 РАССЫЛКА", callback_data="brd")]]))

@dp.message(F.text.startswith("/edit_"))
async def ed_drv(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    did = int(message.text.split("_")[1]); info = get_driver_info(did)
    kb = [[InlineKeyboardButton(text="💰 Баланс", callback_data=f"eb_{did}"), InlineKeyboardButton(text="📊 %", callback_data=f"ec_{did}")],
          [InlineKeyboardButton(text="💸 Счет", callback_data=f"bl_{did}"), InlineKeyboardButton(text="🔒 Блок", callback_data=f"bk_{did}")]]
    await message.answer(f"Редактирование: {info[7]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- ПРОЧЕЕ ---
@dp.message(F.text == "🔐 Ввести КЛЮЧ услуги")
async def key_st(m: types.Message, state: FSMContext): await state.clear(); await m.answer("Введите код:"); await state.set_state(UnlockMenu.waiting_for_key)
@dp.message(UnlockMenu.waiting_for_key)
async def key_pr(m: types.Message, state: FSMContext):
    drv = get_driver_by_code(m.text.strip().upper())
    if drv: client_driver_link[m.from_user.id] = drv[0]; await m.answer(f"🔓 Доступ открыт! Пилот: {drv[3]}", reply_markup=main_kb); await state.clear()
    else: await m.answer("❌ Неверный код.")

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
