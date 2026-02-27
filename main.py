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

# ==========================================
# ⚙️ НАСТРОЙКИ
# ==========================================
logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("API_TOKEN")
OWNER_ID = int(os.getenv("DRIVER_ID"))

# 👑 СПИСОК АДМИНОВ (ТЫ + ПАРТНЕР)
ADMIN_IDS = [OWNER_ID, 6004764782]

# 🔑 КЛЮЧИ
VIP_DRIVER_KEY = "CRAZY_START"
VIP_ADMIN_KEY = "BIG_BOSS_777"

LAWYER_LINK = "https://t.me/Ai_advokatrobot"

if not API_TOKEN:
    exit("Error: No token")

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
    
    # Таблица водителей (ВСЕ ПОЛЯ ВЕРНУЛ)
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
    
    # АВТО-РЕГИСТРАЦИЯ ВСЕХ АДМИНОВ
    for admin_id in ADMIN_IDS:
        cursor.execute("SELECT 1 FROM drivers WHERE user_id = ?", (admin_id,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, role) VALUES (?, ?, ?, ?, ?, ?, 'active', 'owner')",
                (admin_id, "BOSS", "Владелец", "Black Volga", "Сбер", f"ADMIN_{admin_id}")
            )
        else:
            cursor.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (admin_id,))
            
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 🛠 ФУНКЦИИ
# ==========================================

def is_admin(user_id):
    if user_id in ADMIN_IDS: return True
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT 1 FROM drivers WHERE user_id=? AND role IN ('owner', 'admin') AND status='active'", (user_id,)).fetchone()
    conn.close()
    return bool(res)

def get_all_admins_db():
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT user_id FROM drivers WHERE role IN ('owner', 'admin') AND status='active'").fetchall()
    conn.close()
    db_admins = [r[0] for r in res]
    return list(set(db_admins + ADMIN_IDS))

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
    commission = int(amount * 0.10)
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
    admins = get_all_admins_db()
    for admin_id in admins:
        try: await bot.send_message(admin_id, text, reply_markup=markup)
        except: pass

# ==========================================
# 📜 ПОЛНОЕ КРЕЙЗИ МЕНЮ (ВСЕ ТЕКСТЫ НА МЕСТЕ)
# ==========================================
CRAZY_SERVICES = {
    # LEVEL 1
    "candy": {"cat": 1, "price": 0, "name": "🍬 Конфетка", "desc": "Водитель с максимально серьезным лицом (как на государственных похоронах) вручает вам элитную барбариску. Это знак глубочайшего уважения."},
    "nose": {"cat": 1, "price": 300, "name": "👃 Палец в носу", "desc": "Всю поездку (или до первого поста ГАИ) водитель едет с пальцем в носу. Вы платите за его моральные страдания, потерю авторитета и ваш истерический смех."},
    "butler": {"cat": 1, "price": 200, "name": "🤵 Дворецкий", "desc": "Водитель выходит, картинно открывает вам дверь, кланяется в пояс и называет вас 'Сир' или 'Миледи'. Чувство превосходства включено в стоимость."},
    "joke": {"cat": 1, "price": 50, "name": "🤡 Тупой анекдот", "desc": "Анекдот категории 'Б' из золотой коллекции таксиста 90-х. Смеяться не обязательно, но желательно, чтобы не обидеть тонкую творческую натуру водителя."},
    "silence": {"cat": 1, "price": 150, "name": "🤐 Полная тишина", "desc": "Режим 'Ниндзя'. Музыка выключается, водитель молчит как рыба. Даже если вы спросите дорогу — он ответит языком жестов. Идеально для интровертов."},
    # LEVEL 2
    "granny": {"cat": 2, "price": 800, "name": "👵 Бабушка-ворчунья", "desc": "Ролевая игра. Всю дорогу буду бубнить: 'Куда прешь, наркоман?', 'Шапку надень!', 'Вот в наше время такси стоило копейку!'. Полное погружение в детство."},
    "gopnik": {"cat": 2, "price": 500, "name": "🍺 Четкий пацанчик", "desc": "Едем под пацанский рэп, водитель сидит на корточках (шутка, за рулем), называет вас 'Братишка', лузгает семечки и решает вопросики по телефону."},
    "guide": {"cat": 2, "price": 600, "name": "🗣 Ужасный гид", "desc": "Водитель проводит экскурсию, на ходу выдумывая факты. 'Вот этот ларек построил Иван Грозный лично'. Чем бредовее факты, тем лучше."},
    "psych": {"cat": 2, "price": 1000, "name": "🧠 Психолог", "desc": "Вы жалуетесь на жизнь, бывших и начальника. Водитель кивает, говорит 'Угу', вздыхает и дает житейские советы уровня Ошо."},
    # LEVEL 3
    "spy": {"cat": 3, "price": 2000, "name": "🕵️‍♂️ Шпион 007", "desc": "Черные очки, паранойя. Водитель постоянно проверяет 'хвост', говорит по рации кодами ('Орел в гнезде') и прячет лицо от камер."},
    "karaoke": {"cat": 3, "price": 5000, "name": "🎤 Адское Караоке", "desc": "Врубаем 'Рюмку водки' или 'Знаешь ли ты' на полную! Водитель орет песни вместе с вами. Фальшиво, громко, но очень душевно."},
    "dance": {"cat": 3, "price": 15000, "name": "💃 Танцы на капоте", "desc": "На красном свете водитель выбегает из машины и танцует макарену или лезгинку перед капотом. Прохожие снимают, вам стыдно, всем весело!"},
    # LEVEL 4
    "kidnap": {"cat": 4, "price": 30000, "name": "🎭 Дружеское похищение", "desc": "Вас (понарошку, но реалистично) грузят в багажник (или на заднее), надевают мешок на голову и везут в лес... пить элитный чай с баранками."},
    "tarzan": {"cat": 4, "price": 50000, "name": "🦍 Тарзан-Шоу", "desc": "Водитель бьет себя в грудь, издает гортанные звуки, рычит на прохожих и называет другие машины 'железными буйволами'. Санитары уже выехали."},
    "burn": {"cat": 4, "price": 1000000, "name": "🔥 Сжечь машину", "desc": "Финальный аккорд. Едем на пустырь. Вы платите миллион, я даю канистру. Гори оно всё синим пламенем. (Машина реальная, шоу реальное)."},
    # LEVEL 5 (ДЛЯ ДАМ)
    "eyes": {"cat": 5, "price": 0, "name": "👁️ Глаз-алмаз", "desc": "Водитель сделает изысканный, поэтичный комплимент вашим глазам. Возможно, сравнит их с звездами или фарами ксенона."},
    "smile": {"cat": 5, "price": 0, "name": "😁 Улыбка Джоконды", "desc": "Водитель скажет, что ваша улыбка освещает этот старый, пыльный салон лучше, чем аварийка в ночи."},
    "style": {"cat": 5, "price": 0, "name": "👠 Икона стиля", "desc": "Восхищение вашим образом. Водитель поинтересуется, не едете ли вы случайно с показа мод в Париже."},
    "improv": {"cat": 5, "price": 0, "name": "✨ Импровизация", "desc": "Водитель сам найдет, что в вас похвалить. Рискованно, но приятно. Полный фристайл и галантность."},
    "propose": {"cat": 5, "price": 1000, "name": "💍 Сделать предложение", "desc": "Вы делаете предложение руки, сердца или ипотеки водителю. Шанс 50/50. ⚠️ ВНИМАНИЕ: В случае отказа 1000₽ НЕ ВОЗВРАЩАЮТСЯ!"}
}

CATEGORIES = {1: "🟢 ЛАЙТ (До 300₽)", 2: "🟡 МЕДИУМ (Ролевые)", 3: "🔴 ХАРД (Треш)", 4: "☠️ VIP БЕЗУМИЕ", 5: "🌹 ДЛЯ ДАМ (Бесплатно/Риск)"}

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
    [InlineKeyboardButton(text="❌ Я боюсь, выпустите", callback_data="decline_tos")]
])

# ==========================================
# 🛑 СТАРТ И ЮРИДИЧЕСКИЙ БЛОК
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    # ! ВАЖНО: СБРОС СОСТОЯНИЯ ПРИ СТАРТЕ
    await state.clear()
    
    await message.answer(
        "⚠️ <b>CRAZY TAXI: ЗОНА ПОВЫШЕННОГО РИСКА И ВЕСЕЛЬЯ</b>\n\n"
        "Мы не возим скучных людей. Мы продаем эмоции и истории.\n\n"
        "<b>📜 Правила нашего клуба:</b>\n"
        "1. Что происходит в такси — остается в такси.\n"
        "2. Водитель — непризнанный гений и художник, салон — его холст.\n"
        "3. Наш юридический отдел уже выиграл суд у здравого смысла.\n\n"
        "Готовы рискнуть рассудком ради поездки?", 
        reply_markup=tos_kb
    )

@dp.callback_query(F.data == "accept_tos")
async def tos_accepted(callback: types.CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (callback.from_user.id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("🔥 <b>КОНТРАКТ ПОДПИСАН!</b>\nДвери заблокированы (шутка... или нет?).")
    await callback.message.answer("Добро пожаловать в семью. Выбирай свою судьбу в меню ниже 👇", reply_markup=main_kb)

@dp.callback_query(F.data == "decline_tos")
async def tos_declined(callback: types.CallbackQuery):
    await callback.message.edit_text("🚶‍♂️ Очень жаль. Идите пешком, скучный человек.")

async def check_tos(message: types.Message) -> bool:
    if not is_client_accepted(message.from_user.id):
        await message.answer("🛑 <b>ДОСТУП ЗАПРЕЩЕН!</b>\nСначала нажмите /start и примите условия соглашения.")
        return False
    return True

@dp.message(F.text == "⚖️ Вызвать адвоката")
async def lawyer_menu(message: types.Message):
    await message.answer(
        "⚖️ <b>ЮРИДИЧЕСКИЙ ЩИТ 'CRAZY TAXI'</b>\n\n"
        "Чувствуете, что ситуация выходит из-под контроля? Водитель переигрывает? Или вам просто нужен совет, как объяснить жене, почему вы приехали домой на пожарной машине?\n\n"
        "Наш официальный партнер — <b>AI Адвокат</b>. Он знает законы всех стран (даже вымышленных) и готов защищать ваши интересы.\n\n"
        "<i>Нажмите кнопку ниже, чтобы перейти в приемную:</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👨‍⚖️ ПЕРЕЙТИ К АДВОКАТУ", url=LAWYER_LINK)]
        ])
    )

# ==========================================
# 🚀 МОНИТОРИНГ И РАССЫЛКА
# ==========================================
async def update_admins_monitor(client_id, taking_driver_id):
    order = active_orders.get(client_id)
    if not order or 'admin_msg_ids' not in order: return
    
    drv_info = get_driver_info(taking_driver_id)
    drv_name = f"@{drv_info[0]}" if drv_info[0] else "Unknown"
    fio = drv_info[7] if drv_info[7] else "Без ФИО"
    
    taker_role = "👑 БОСС" if taking_driver_id == OWNER_ID else ("👮‍♂️ АДМИН" if is_admin(taking_driver_id) else "🚕 ВОДИТЕЛЬ")
    
    text = (
        f"🚫 <b>ЗАКАЗ ПЕРЕХВАЧЕН!</b>\n"
        f"Кем: <b>{taker_role} {drv_name}</b>\n"
        f"ФИО: {fio}\n"
        f"Авто: {drv_info[1]}\n\n"
        f"<i>{order.get('broadcasting_text','')}</i>"
    )
    
    for admin_id, msg_id in order['admin_msg_ids'].items():
        try: await bot.edit_message_text(chat_id=admin_id, message_id=msg_id, text=text, reply_markup=None)
        except: pass

async def broadcast_order_to_drivers(client_id, order_text, driver_kb, admin_kb):
    admins = get_all_admins_db()
    admin_msg_map = {}
    admin_text = f"🚨 <b>МОНИТОРИНГ СЕТИ (АДМИН)</b>\n\n{order_text}"
    
    for admin_id in admins:
        try:
            msg = await bot.send_message(admin_id, admin_text, reply_markup=admin_kb)
            admin_msg_map[admin_id] = msg.message_id
        except: pass
        
    if client_id in active_orders:
        active_orders[client_id]['admin_msg_ids'] = admin_msg_map
        active_orders[client_id]['broadcasting_text'] = order_text

    search_msg = await bot.send_message(client_id, "📡 <i>Сканируем город в поисках подходящего безумца...</i>")
    await asyncio.sleep(1.5)
    
    all_active = get_active_drivers()
    simple_drivers = [d for d in all_active if d not in admins]
    
    if not simple_drivers and not admins:
        await search_msg.edit_text("😔 <b>Все машины заняты.</b> Администрация уведомлена.")
        return

    tasks = []
    for d_id in simple_drivers:
        tasks.append(bot.send_message(d_id, f"⚡ <b>НОВЫЙ ЗАКАЗ!</b>\n{order_text}", reply_markup=driver_kb))
    
    if tasks: await asyncio.gather(*tasks, return_exceptions=True)
    await search_msg.edit_text("⏳ <b>Запрос отправлен всем пилотам!</b> Ждем реакции...")

# ==========================================
# 📜 МЕНЮ УСЛУГ
# ==========================================
@dp.message(F.text == "📜 CRAZY МЕНЮ (Категории)")
async def show_cats(message: types.Message):
    if not await check_tos(message): return
    if message.from_user.id not in client_driver_link:
        await message.answer("🔒 <b>ДОСТУП ЗАКРЫТ!</b>\nВы должны находиться в машине. Введите код водителя через кнопку '🔐 Ввести КЛЮЧ'.", reply_markup=main_kb)
        return
    btns = [[InlineKeyboardButton(text=n, callback_data=f"cat_{i}")] for i, n in CATEGORIES.items()]
    await message.answer("🔥 <b>ВЫБЕРИТЕ УРОВЕНЬ ЖЕСТКОСТИ:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("cat_"))
async def open_cat(callback: types.CallbackQuery):
    cat_id = int(callback.data.split("_")[1])
    btns = []
    for k, v in CRAZY_SERVICES.items():
        if v["cat"] == cat_id:
            pr = "БЕСПЛАТНО" if v['price']==0 else f"{v['price']}₽"
            btns.append([InlineKeyboardButton(text=f"{v['name']} — {pr}", callback_data=f"csel_{k}")])
    btns.append([InlineKeyboardButton(text="🔙 Назад к категориям", callback_data="back_cats")])
    await callback.message.edit_text(f"📂 <b>{CATEGORIES[cat_id]}</b>\nВыберите услугу:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "back_cats")
async def back_cats(callback: types.CallbackQuery):
    btns = [[InlineKeyboardButton(text=n, callback_data=f"cat_{i}")] for i, n in CATEGORIES.items()]
    await callback.message.edit_text("🔥 <b>УРОВНИ ЖЕСТКОСТИ:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("csel_"))
async def sel_srv(callback: types.CallbackQuery):
    key = callback.data.split("_")[1]
    srv = CRAZY_SERVICES[key]
    did = client_driver_link.get(callback.from_user.id)
    if not did: return
    
    pr_text = "БЕСПЛАТНО" if srv['price'] == 0 else f"{srv['price']}₽"
    text = (
        f"🎭 <b>УСЛУГА: {srv['name']}</b>\n"
        f"💰 <b>Стоимость: {pr_text}</b>\n\n"
        f"📝 <b>Сценарий:</b>\n<i>{srv['desc']}</i>\n\n"
        f"Вы точно хотите это сделать?"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ ЗАКАЗ", callback_data=f"do_order_{key}")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"cat_{srv['cat']}")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("do_order_"))
async def do_order(callback: types.CallbackQuery):
    # Берем ПОСЛЕДНИЙ элемент (ключ), чтобы не было ошибок
    key = callback.data.split("_")[-1] 
    srv = CRAZY_SERVICES[key]
    cid, did = callback.from_user.id, client_driver_link.get(callback.from_user.id)
    
    active_orders[cid] = {"type": "crazy", "status": "direct", "price": str(srv["price"]), "driver_id": did, "service": srv}
    await callback.message.edit_text(f"⏳ <b>Отправляем запрос водителю...</b>\nОн должен морально подготовиться.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ ВЫЗОВ", callback_data=f"drv_acc_{cid}")]])
    await bot.send_message(did, f"🔔 <b>ПЕРСОНАЛЬНЫЙ CRAZY-ЗАКАЗ</b>\n\n🎭 Услуга: <b>{srv['name']}</b>\n💰 Цена: <b>{srv['price']}₽</b>\n📝 Задание: {srv['desc']}", reply_markup=kb)
    await notify_admins(f"👀 <b>СДЕЛКА ВНУТРИ АВТО:</b> Клиент заказал '{srv['name']}' у водителя {did}")

@dp.callback_query(F.data.startswith("drv_acc_"))
async def drv_acc(callback: types.CallbackQuery):
    cid = int(callback.data.split("_")[2])
    order = active_orders.get(cid)
    if not order: return
    
    info = get_driver_info(callback.from_user.id)
    pr = extract_price(order['price'])
    
    if pr == 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ УСЛУГА ПОЛУЧЕНА", callback_data=f"cli_pay_{cid}")]])
        await bot.send_message(cid, "✅ <b>Водитель принял вызов!</b>\n🎁 Эта услуга предоставляется бесплатно. Наслаждайтесь!", reply_markup=kb)
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Я ОПЛАТИЛ", callback_data=f"cli_pay_{cid}")]])
        await bot.send_message(cid, f"✅ <b>Водитель готов!</b>\n💳 Пожалуйста, переведите <b>{pr}₽</b> по реквизитам:\n<code>{info[2]}</code>", reply_markup=kb)
    await callback.message.edit_text("✅ Вы приняли заказ. Ожидайте подтверждения оплаты.")

@dp.callback_query(F.data.startswith("cli_pay_"))
async def cli_pay(callback: types.CallbackQuery):
    cid = callback.from_user.id
    order = active_orders.get(cid)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ДЕНЬГИ ПРИШЛИ / ВЫПОЛНЕНО", callback_data=f"drv_fin_{cid}")]])
    await callback.message.edit_text("⏳ Ожидаем подтверждения от водителя...")
    await bot.send_message(order["driver_id"], "💸 <b>Клиент подтвердил оплату!</b>\nПроверьте баланс и выполните услугу.", reply_markup=kb)

@dp.callback_query(F.data.startswith("drv_fin_"))
async def drv_fin(callback: types.CallbackQuery):
    cid = int(callback.data.split("_")[2])
    did = callback.from_user.id
    order = active_orders.get(cid)
    pr = extract_price(order['price'])
    add_commission(did, pr)
    log_order(did, order['service']['name'], pr)
    await callback.message.edit_text("✅ <b>Заказ закрыт.</b>")
    await bot.send_message(cid, "🎉 <b>Услуга выполнена!</b>\nСпасибо, что выбрали Crazy Taxi.")
    del active_orders[cid]

# ==========================================
# 🚕 ТАКСИ + ТОРГ
# ==========================================
@dp.message(F.text == "🚕 Заказать такси (Поиск)")
async def taxi_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("📍 <b>Откуда вас забрать?</b> (Улица, дом, ориентир)", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(OrderRide.waiting_for_from)

@dp.message(OrderRide.waiting_for_from)
async def taxi_fr(message: types.Message, state: FSMContext):
    await state.update_data(fr=message.text)
    await message.answer("🏁 <b>Куда поедем?</b>")
    await state.set_state(OrderRide.waiting_for_to)

@dp.message(OrderRide.waiting_for_to)
async def taxi_to(message: types.Message, state: FSMContext):
    await state.update_data(to=message.text)
    await message.answer("📞 <b>Ваш номер телефона для связи:</b>")
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
    
    text = (
        f"🚕 <b>НОВЫЙ ЗАКАЗ ТАКСИ</b>\n\n"
        f"📍 Откуда: <b>{data['fr']}</b>\n"
        f"🏁 Куда: <b>{data['to']}</b>\n"
        f"💰 Клиент предлагает: <b>{message.text}</b>"
    )
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
    drv_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ ПОЕЗДКУ", callback_data=f"ask_finish_{cid}")]])
    await callback.message.edit_text(f"✅ <b>Заказ принят!</b>\n📞 Телефон клиента: <b>{order['phone']}</b>\n💰 Цена: <b>{order['price']}</b>", reply_markup=drv_kb)
    
    cli_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ ДОБАВИТЬ ОСТАНОВКУ", callback_data="add_stop")]])
    await bot.send_message(
        cid, 
        f"🚕 <b>ВОДИТЕЛЬ ВЫЕХАЛ!</b>\n\n👤 <b>{info[7]}</b>\n🚘 {info[1]}\n📞 {order['phone']}\n💰 {order['price']}₽\n\n🔐 <b>КОД CRAZY-МЕНЮ:</b> <code>{info[5]}</code>\n"
        f"<i>(Сообщите его водителю, если захотите развлечений)</i>",
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
        [InlineKeyboardButton(text="⭐ 1", callback_data=f"rate_{cid}_1"), InlineKeyboardButton(text="⭐ 3", callback_data=f"rate_{cid}_3"), InlineKeyboardButton(text="⭐ 5", callback_data=f"rate_{cid}_5")],
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
# 💡 ИДЕЯ + ТОРГ
# ==========================================
@dp.message(F.text == "💡 Свой вариант (Идея)")
async def idea_st(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Опишите вашу идею:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(CustomIdea.waiting_for_idea)

@dp.message(CustomIdea.waiting_for_idea)
async def idea_pr(message: types.Message, state: FSMContext):
    await state.update_data(idea=message.text)
    await message.answer("Ваш бюджет (в рублях)?")
    await state.set_state(CustomIdea.waiting_for_price)

@dp.message(CustomIdea.waiting_for_price)
async def idea_snd(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cid = message.from_user.id
    active_orders[cid] = {"type": "crazy", "status": "pending", "price": message.text, "service": {"name": "Идея", "desc": data['idea']}, "driver_offers": {}}
    await message.answer("✅ <b>Идея отправлена водителям!</b>", reply_markup=main_kb)
    await state.clear()
    
    text = f"💡 <b>ИДЕЯ ОТ КЛИЕНТА</b>\n\n📝 Суть: {data['idea']}\n💰 Бюджет: {message.text}"
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
    await bot.send_message(cid, f"✅ <b>ИСПОЛНИТЕЛЬ НАЙДЕН!</b>\n\n👤 {info[0]}\n💳 {info[2]}\n🔐 {info[5]}", reply_markup=kb)

@dp.callback_query(F.data.startswith("cnt_"))
async def start_cnt(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    await state.update_data(cid=int(parts[2]), type=parts[1])
    await callback.message.answer("Ваши условия и цена:")
    await state.set_state(DriverCounterOffer.waiting_for_offer)
    await callback.answer()

@dp.message(DriverCounterOffer.waiting_for_offer)
async def send_cnt(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cid, did = data['cid'], message.from_user.id
    order = active_orders.get(cid)
    if not order: return
    order.setdefault("driver_offers", {})[did] = message.text
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ СОГЛАСЕН", callback_data=f"ok_off_{data['type']}_{cid}_{did}"), InlineKeyboardButton(text="❌ ОТКАЗ", callback_data=f"no_off_{cid}")]])
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
        await bot.send_message(did, f"✅ <b>Клиент согласен!</b>\n📞 {order['phone']}", reply_markup=kb)
        await callback.message.edit_text(f"🚕 <b>Едет: {info[0]}</b>\n🔐 {info[5]}")
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 ОПЛАТИЛ", callback_data=f"cpay_done_{cid}")]])
        await callback.message.edit_text(f"🤝 <b>ОК!</b>\n💳 {info[2]}\n🔐 {info[5]}", reply_markup=kb)
        await bot.send_message(did, "✅ Клиент согласен!")

@dp.callback_query(F.data.startswith("no_off_"))
async def no_off(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Вы отказались.")

# ==========================================
# 🪪 КАБИНЕТ + ПОДРОБНАЯ РЕГИСТРАЦИЯ
# ==========================================
@dp.message(Command("cab"))
async def cab(message: types.Message, state: FSMContext):
    await state.clear()
    info = get_driver_info(message.from_user.id)
    if not info:
        await message.answer("❌ Вы не зарегистрированы. Жмите /drive")
        return
    if info[4] != 'active': 
        await message.answer(f"❌ Ваш статус: <b>{info[4]}</b>. Ожидайте одобрения.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    hist = conn.execute("SELECT service_name, price, rating FROM order_history WHERE driver_id=? ORDER BY id DESC LIMIT 5", (message.from_user.id,)).fetchall()
    conn.close()
    
    roles = {'owner':"👑 БОСС", 'admin':"👮‍♂️ АДМИН", 'driver':"🚕 ВОДИТЕЛЬ"}
    fio = info[7] if info[7] else "Не указано"
    
    text = (
        f"🪪 <b>ЛИЧНЫЙ КАБИНЕТ ПИЛОТА</b>\n\n"
        f"Статус: <b>{roles.get(info[6])}</b>\n"
        f"👤 ФИО: <b>{fio}</b>\n"
        f"🚘 Авто: <b>{info[1]}</b>\n"
        f"🔑 Секретный Код: <code>{info[5]}</code>\n\n"
        f"💰 Баланс (Долг): <b>{info[3]}₽</b>\n"
        f"📊 Всего заработано: <b>{hist[1] or 0}₽</b>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Сменить Код", callback_data="cab_chg")],
        [InlineKeyboardButton(text="💸 Оплатить Долг", callback_data="cab_pay")]
    ])
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "cab_chg")
async def cab_chg(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("⌨️ Введите новый код доступа:")
    await state.set_state(DriverChangeCode.waiting_for_new_code)
    await callback.answer()

@dp.message(DriverChangeCode.waiting_for_new_code)
async def cab_save_code(message: types.Message, state: FSMContext):
    try: update_driver_field(message.from_user.id, "access_code", message.text.upper().strip())
    except: 
        await message.answer("❌ Этот код уже занят.")
        return
    await message.answer("✅ <b>Код успешно изменен!</b>")
    await state.clear()

@dp.callback_query(F.data == "cab_pay")
async def cab_pay(callback: types.CallbackQuery):
    info = get_driver_info(callback.from_user.id)
    boss = get_driver_info(OWNER_ID)
    req = boss[2] if boss else "Уточните у Босса"
    await callback.message.answer(f"💸 Ваш долг: <b>{info[3]}₽</b>\nПереведите на карту Владельца:\n💳 <b>{req}</b>\n\nПришлите скриншот в ЛС Боссу.")
    await callback.answer()

# ✅ РЕГИСТРАЦИЯ (ПОДРОБНАЯ)
@dp.message(Command("driver", "drive"))
async def reg_start(message: types.Message, state: FSMContext):
    await state.clear()
    info = get_driver_info(message.from_user.id)
    if info:
        if info[4]=='active': await message.answer("✅ Вы уже в системе. Жмите /cab")
        else: await message.answer("⏳ Ваша заявка на проверке.")
        return
    await message.answer("📝 <b>АНКЕТА ВОДИТЕЛЯ</b>\n\nШаг 1. Введите ваше <b>ФИО полностью</b>:")
    await state.set_state(DriverRegistration.waiting_for_fio)

@dp.message(DriverRegistration.waiting_for_fio)
async def reg_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await message.answer("🚘 Шаг 2. Опишите машину (Марка, Цвет, Госномер, Год):")
    await state.set_state(DriverRegistration.waiting_for_car)

@dp.message(DriverRegistration.waiting_for_car)
async def reg_car(message: types.Message, state: FSMContext):
    await state.update_data(car=message.text)
    await message.answer("💳 Шаг 3. Ваши реквизиты (Банк + Номер карты/Телефона):")
    await state.set_state(DriverRegistration.waiting_for_payment_info)

@dp.message(DriverRegistration.waiting_for_payment_info)
async def reg_pay(message: types.Message, state: FSMContext):
    await state.update_data(pay=message.text)
    await message.answer("🔑 Шаг 4. Придумайте <b>Секретный Код</b> (например: KING777):")
    await state.set_state(DriverRegistration.waiting_for_code)

@dp.message(DriverRegistration.waiting_for_code)
async def reg_fin(message: types.Message, state: FSMContext):
    code = message.text.upper().strip()
    data = await state.get_data()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')", 
                     (message.from_user.id, message.from_user.username, data['fio'], data['car'], data['pay'], code))
        conn.commit()
        await message.answer("✅ <b>Анкета отправлена!</b> Ожидайте решения администрации.")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ОДОБРИТЬ", callback_data=f"adm_app_{message.from_user.id}")]])
        msg_text = (
            f"🚨 <b>НОВЫЙ ВОДИТЕЛЬ!</b>\n"
            f"👤 @{message.from_user.username}\n"
            f"📝 ФИО: {data['fio']}\n"
            f"🚘 Авто: {data['car']}\n"
            f"💳 Реквизиты: {data['pay']}\n"
            f"🔑 Код: {code}"
        )
        await notify_admins(msg_text, kb)
    except:
        await message.answer("❌ Этот Код уже занят. Придумайте другой.")
        return
    finally: conn.close()
    await state.clear()

# 🔥 VIP РЕГИСТРАЦИЯ
@dp.message(Command("vip"))
async def vip_reg(message: types.Message, state: FSMContext):
    await state.clear()
    try:
        key = message.text.split()[1]
        role = "driver"
        
        if key == VIP_ADMIN_KEY: role = "admin"
        elif key != VIP_DRIVER_KEY:
            await message.answer("❌ Неверный ключ.")
            return
            
        await state.update_data(role=role)
        await message.answer(f"🔑 <b>КЛЮЧ {role.upper()} ПРИНЯТ!</b>\n\nВведите ФИО:")
        await state.set_state(DriverVipRegistration.waiting_for_fio)
    except:
        await message.answer("Используйте: /vip ВАШ_КЛЮЧ")

@dp.message(DriverVipRegistration.waiting_for_fio)
async def vip_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await message.answer("🚘 Машина (Марка, Номер):")
    await state.set_state(DriverVipRegistration.waiting_for_car)

@dp.message(DriverVipRegistration.waiting_for_car)
async def vip_car(message: types.Message, state: FSMContext):
    await state.update_data(car=message.text)
    await message.answer("💳 Реквизиты:")
    await state.set_state(DriverVipRegistration.waiting_for_payment_info)

@dp.message(DriverVipRegistration.waiting_for_payment_info)
async def vip_pay(message: types.Message, state: FSMContext):
    await state.update_data(pay=message.text)
    await message.answer("🔑 Придумайте Код:")
    await state.set_state(DriverVipRegistration.waiting_for_code)

@dp.message(DriverVipRegistration.waiting_for_code)
async def vip_fin(message: types.Message, state: FSMContext):
    code = message.text.upper().strip()
    data = await state.get_data()
    role = data.get('role', 'driver')
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, role) VALUES (?, ?, ?, ?, ?, ?, 'active', ?)", 
                     (message.from_user.id, message.from_user.username, data['fio'], data['car'], data['pay'], code, role))
        conn.commit()
        await message.answer(f"🚀 <b>ВЫ ПРИНЯТЫ КАК {role.upper()}!</b>\nСтатус: ACTIVE. Используйте /cab")
        await notify_admins(f"⭐ <b>VIP РЕГИСТРАЦИЯ</b>\n@{message.from_user.username} ({data['fio']})")
    except:
        await message.answer("❌ Код занят.")
    finally: conn.close()
    await state.clear()

# ==========================================
# 👑 АДМИНКА
# ==========================================
@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id): return
    conn = sqlite3.connect(DB_PATH)
    drs = conn.execute("SELECT user_id, username, balance, role, status, fio FROM drivers").fetchall()
    conn.close()
    txt = "👑 <b>ПАНЕЛЬ УПРАВЛЕНИЯ</b>\n\n"
    for d in drs:
        ic = "🔒" if d[4]=='blocked' else ("👑" if d[3]=='owner' else ("👮" if d[3]=='admin' else "🚕"))
        fio = d[5] if d[5] else "Без имени"
        txt += f"{ic} <b>{fio}</b> (@{d[1]})\n💰 Долг: {d[2]}₽ | ID: /edit_{d[0]}\n\n"
    await message.answer(txt)

@dp.message(Command("setadmin"))
async def set_ad(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    try:
        tid = int(message.text.split()[1])
        update_driver_field(tid, "role", "admin")
        await message.answer("✅ Пользователь назначен Админом.")
        await bot.send_message(tid, "👮‍♂️ <b>Вы назначены Администратором!</b>")
    except: pass

@dp.message(Command("deladmin"))
async def del_ad(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    try:
        tid = int(message.text.split()[1])
        update_driver_field(tid, "role", "driver")
        await message.answer("✅ Разжалован в водители.")
    except: pass

@dp.callback_query(F.data.startswith("adm_app_"))
async def adm_app(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    did = int(callback.data.split("_")[2])
    update_driver_field(did, "status", "active")
    await callback.message.edit_text("✅ <b>Одобрено.</b>")
    try: await bot.send_message(did, "🎉 <b>Ваша анкета одобрена!</b>\nТеперь вы в команде. Жмите /cab")
    except: pass

@dp.message(F.text.startswith("/edit_"))
async def edit_d(message: types.Message):
    if not is_admin(message.from_user.id): return
    try: did = int(message.text.split("_")[1])
    except: return
    info = get_driver_info(did)
    
    if info[6]=='owner' and message.from_user.id!=OWNER_ID: 
        await message.answer("⛔ Нельзя редактировать Босса.")
        return
        
    fio = info[7] if info[7] else "Без имени"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Изм. Баланс", callback_data=f"edt_bal_{did}"), InlineKeyboardButton(text="💸 Выставить Счет", callback_data=f"adm_bill_{did}")],
        [InlineKeyboardButton(text="🔒 Блок / 🔓 Разблок", callback_data=f"adm_block_{did}")]
    ])
    await message.answer(f"✏️ <b>Редактирование:</b>\n{fio} (@{info[0]})", reply_markup=kb)

@dp.callback_query(F.data.startswith("edt_"))
async def edt_st(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.update_data(did=int(callback.data.split("_")[2]), fld="balance")
    await callback.message.answer("⌨️ Введите новый баланс (число):")
    await state.set_state(AdminEditDriver.waiting_for_new_value)
    await callback.answer()

@dp.message(AdminEditDriver.waiting_for_new_value)
async def edt_sv(message: types.Message, state: FSMContext):
    d = await state.get_data()
    update_driver_field(d['did'], d['fld'], message.text)
    await message.answer("✅ Сохранено.")
    await state.clear()

@dp.callback_query(F.data.startswith("adm_"))
async def adm_act(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    parts = callback.data.split("_")
    did = int(parts[2])
    
    if parts[1] == "bill":
        boss = get_driver_info(OWNER_ID)
        info = get_driver_info(did)
        try: await bot.send_message(did, f"⚠️ <b>ТРЕБОВАНИЕ ОПЛАТЫ!</b>\nВаш долг: {info[3]}₽\nРеквизиты: {boss[2]}")
        except: pass
        await callback.answer("Счет отправлен.")
        
    elif parts[1] == "block":
        if get_driver_info(did)[6] == 'owner': return
        cur = get_driver_info(did)[4]
        new_s = "blocked" if cur=="active" else "active"
        update_driver_field(did, "status", new_s)
        await callback.message.edit_text(f"Статус изменен на: <b>{new_s}</b>")

# ==========================================
# 🔐 ВВОД КЛЮЧА
# ==========================================
@dp.message(F.text == "🔐 Ввести КЛЮЧ услуги")
async def ask_key(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    await state.clear()
    await message.answer("🕵️‍♂️ <b>Введите секретный код водителя:</b>")
    await state.set_state(UnlockMenu.waiting_for_key)

@dp.message(UnlockMenu.waiting_for_key)
async def proc_key(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    drv = get_driver_by_code(code)
    if drv:
        client_driver_link[message.from_user.id] = drv[0]
        # drv = (id, username, car_info, fio)
        fio = drv[3] if drv[3] else "Водитель"
        await message.answer(f"🔓 <b>ДОСТУП РАЗРЕШЕН!</b>\n\n👤 {fio}\n🚘 {drv[2]}", reply_markup=main_kb)
        await state.clear()
    else: await message.answer("❌ <b>Неверный ключ.</b> Попробуйте снова.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
