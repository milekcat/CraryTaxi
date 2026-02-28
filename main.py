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
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

# ==========================================
# ⚙️ НАСТРОЙКИ
# ==========================================
logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("API_TOKEN")
OWNER_ID_STR = os.getenv("DRIVER_ID") 

if not API_TOKEN or not OWNER_ID_STR:
    exit("⛔ CRITICAL ERROR: Token or ID missing")

OWNER_ID = int(OWNER_ID_STR)
SECOND_ADMIN_ID = 6004764782
SUPER_ADMINS = [OWNER_ID, SECOND_ADMIN_ID]

VIP_DRIVER_KEY = "CRAZY_START"
LAWYER_LINK = "https://t.me/Ai_advokatrobot"

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

active_orders = {} 

# ==========================================
# 📜 ПОЛНЫЕ ТЕКСТЫ И МЕНЮ (БЕЗ СОКРАЩЕНИЙ)
# ==========================================
LEGAL_TEXT = (
    "<b>📜 ПУБЛИЧНАЯ ОФЕРТА (AGENCY AGREEMENT)</b>\n\n"
    "1. <b>Суть сервиса:</b> Бот является агрегатором развлекательных услуг (Event-агентство). Мы помогаем найти Артистов (аниматоров) для создания настроения.\n"
    "2. <b>Транспорт:</b> Сервис НЕ оказывает транспортные услуги. Автомобиль является «подвижной декорацией» для проведения шоу. Перемещение осуществляется Артистом, имеющим соответствующие права, в рамках его личной ответственности или лицензии.\n"
    "3. <b>Оплата:</b> Вы платите за творческую программу (перформанс), общество Артиста и атмосферу.\n"
    "4. <b>Безопасность:</b> Артист вправе прекратить шоу, если Зритель угрожает безопасности движения.\n"
    "5. <b>Согласие:</b> Нажимая «Найти Артиста», вы нанимаете исполнителя для развлечения, а не службу такси."
)

CRAZY_SERVICES = {
    "candy": {"cat": 1, "price": 0, "name": "🍬 Презент", "desc": "Водитель с максимально серьезным лицом (как на государственных похоронах) вручает вам элитную барбариску. Это знак глубочайшего уважения и начала крепкой дружбы."},
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
    "tarzan": {"cat": 4, "price": 50000, "name": "🦍 Тарзан-Шоу", "desc": "Водитель бьет себя в грудь, издает гортанные звуки, рычит на прохожих и называет другие машины 'железными буйволами'. Санитары уже выехали."},
    "burn": {"cat": 4, "price": 1000000, "name": "🔥 Сжечь машину", "desc": "Финальный аккорд. Едем на пустырь. Вы платите миллион, я даю канистру. Гори оно всё огнем. Эпичный финал."},
    "eyes": {"cat": 5, "price": 0, "name": "👁️ Глаз-алмаз", "desc": "Водитель сделает изысканный, поэтичный комплимент вашим глазам. Возможно, сравнит их с звездами или фарами ксенона."},
    "smile": {"cat": 5, "price": 0, "name": "😁 Улыбка Джоконды", "desc": "Водитель скажет, что ваша улыбка освещает этот старый, пыльный салон лучше, чем аварийка в ночи."},
    "style": {"cat": 5, "price": 0, "name": "👠 Икона стиля", "desc": "Восхищение вашим образом. Водитель поинтересуется, не едете ли вы случайно с показа мод в Париже."},
    "improv": {"cat": 5, "price": 0, "name": "✨ Импровизация", "desc": "Водитель сам найдет, что в вас похвалить. Рискованно, но приятно. Полный фристайл и галантность."},
    "propose": {"cat": 5, "price": 1000, "name": "💍 Сделать предложение", "desc": "Вы делаете предложение руки, сердца или ипотеки водителю. Шанс 50/50. ⚠️ ВНИМАНИЕ: В случае отказа 1000₽ НЕ ВОЗВРАЩАЮТСЯ!"}
}

CATEGORIES = {1: "🟢 ЛАЙТ", 2: "🟡 МЕДИУМ", 3: "🔴 ХАРД", 4: "☠️ VIP БЕЗУМИЕ", 5: "🌹 ДЛЯ ДАМ"}

# ==========================================
# 🗄️ БАЗА ДАННЫХ
# ==========================================
DB_PATH = "/data/taxi_db.sqlite" if os.path.exists("/data") else "taxi_db.sqlite"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Артисты
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
    # 2. Услуги
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS driver_services (
            driver_id INTEGER,
            service_key TEXT,
            is_active BOOLEAN DEFAULT 1,
            PRIMARY KEY (driver_id, service_key)
        )
    """)
    # 3. Зрители
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            user_id INTEGER PRIMARY KEY,
            linked_driver_id INTEGER DEFAULT NULL,
            total_spent INTEGER DEFAULT 0
        )
    """)
    # 4. История
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            driver_id INTEGER,
            service_name TEXT,
            price INTEGER,
            rating INTEGER DEFAULT 0,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Админы
    for admin_id in SUPER_ADMINS:
        try:
            cursor.execute("INSERT OR IGNORE INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, role) VALUES (?, 'BOSS', 'Владелец', 'VIP', 'CASH', ?, 'active', 'owner')", (admin_id, f"ADMIN_{admin_id}"))
            cursor.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (admin_id,))
            for key in CRAZY_SERVICES:
                cursor.execute("INSERT OR REPLACE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, 1)", (admin_id, key))
        except: pass
            
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 🛠 УТИЛИТЫ (ВАЖНО: ОНИ ЗДЕСЬ!)
# ==========================================
def is_client_accepted(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT 1 FROM clients WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return bool(res)

async def check_tos(message: types.Message) -> bool:
    if not is_client_accepted(message.from_user.id): 
        await message.answer("🛑 <b>ДОСТУП ЗАПРЕЩЕН!</b>\nНажмите /start.")
        return False
    return True

def get_client_stats(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT total_spent FROM clients WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return res[0] if res else 0

def update_client_spent(user_id, amount):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE clients SET total_spent = total_spent + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

def get_status_name(spent):
    if spent > 100000: return "👹 МЕЦЕНАТ ХАОСА"
    if spent > 50000: return "💀 ПРОДЮСЕР"
    if spent > 10000: return "🤪 ЦЕНИТЕЛЬ"
    return "👶 ЗРИТЕЛЬ"

def init_driver_services_defaults(driver_id):
    conn = sqlite3.connect(DB_PATH)
    for key in CRAZY_SERVICES: 
        conn.execute("INSERT OR IGNORE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, 1)", (driver_id, key))
    conn.commit()
    conn.close()

def get_driver_active_services(driver_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT service_key FROM driver_services WHERE driver_id=? AND is_active=1", (driver_id,)).fetchall()
    conn.close()
    return [r[0] for r in res]

def toggle_driver_service(driver_id, service_key):
    conn = sqlite3.connect(DB_PATH)
    curr = conn.execute("SELECT is_active FROM driver_services WHERE driver_id=? AND service_key=?", (driver_id, service_key)).fetchone()
    new_status = 0 if (curr and curr[0] == 1) else 1
    conn.execute("INSERT OR REPLACE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, ?)", (driver_id, service_key, new_status))
    conn.commit()
    conn.close()

def get_linked_driver(client_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT linked_driver_id FROM clients WHERE user_id=?", (client_id,)).fetchone()
    conn.close()
    return res[0] if res and res[0] else None

def set_linked_driver(client_id, driver_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO clients (user_id, linked_driver_id) VALUES (?, ?)", (client_id, driver_id))
    conn.commit()
    conn.close()

def is_admin(user_id):
    if user_id in SUPER_ADMINS: return True
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT 1 FROM drivers WHERE user_id=? AND role IN ('owner', 'admin') AND status='active'", (user_id,)).fetchone()
    conn.close()
    return bool(res)

def get_all_admins_ids():
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT user_id FROM drivers WHERE role IN ('owner', 'admin') AND status='active'").fetchall()
    conn.close()
    return list(set([r[0] for r in res] + SUPER_ADMINS))

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
    res = conn.execute("SELECT username, car_info, payment_info, balance, status, access_code, role, fio, rating_sum, rating_count, commission FROM drivers WHERE user_id=?", (user_id,)).fetchone()
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

def log_order(client_id, driver_id, service_name, price):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO order_history (client_id, driver_id, service_name, price) VALUES (?, ?, ?, ?)", (client_id, driver_id, service_name, price))
    conn.commit()
    conn.close()

def update_order_rating(rating, driver_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE drivers SET rating_sum = rating_sum + ?, rating_count = rating_count + 1 WHERE user_id = ?", (rating, driver_id))
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

async def safe_send_message(chat_id, text, reply_markup=None):
    try:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)
        return True
    except: return False

# ==========================================
# FSM STATES
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
class ChatState(StatesGroup):
    active = State()

# ==========================================
# ⌨️ UI (МЕНЮ)
# ==========================================
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎭 Найти Артиста (с авто)")],
        [KeyboardButton(text="📜 CRAZY МЕНЮ (Категории)")],
        [KeyboardButton(text="👤 Мой Кабинет"), KeyboardButton(text="⚖️ Вызвать адвоката")]
    ], resize_keyboard=True
)

tos_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ ПРИНИМАЮ ПРАВИЛА ИГРЫ", callback_data="accept_tos")],
    [InlineKeyboardButton(text="❌ Я слишком скучный", callback_data="decline_tos")]
])

# ==========================================
# 🛑 ЛОГИКА СТАРТА
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if is_client_accepted(message.from_user.id):
        await message.answer("⚠️ <b>CRAZY MOOD: С возвращением в клуб!</b>\nШоу должно продолжаться.", reply_markup=main_kb)
    else:
        await message.answer(
            "⚠️ <b>ВНИМАНИЕ! ЭТО НЕ ТАКСИ. ЭТО ТЕАТР НА КОЛЕСАХ.</b>\n\n"
            "Это сервис поиска попутчиков-аниматоров.\n"
            "Мы находим безумцев, готовых превратить вашу скучную дорогу в шоу.\n\n"
            "<b>Готовы к перформансу?</b>", 
            reply_markup=tos_kb
        )

@dp.callback_query(F.data == "accept_tos")
async def tos_accepted(c: types.CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (c.from_user.id,))
    conn.commit()
    conn.close()
    await c.message.edit_text("🔥 <b>ВЫ В ИГРЕ!</b>")
    await c.message.answer("Добро пожаловать. Выбирайте шоу 👇", reply_markup=main_kb)

@dp.callback_query(F.data == "decline_tos")
async def tos_declined(c: types.CallbackQuery):
    await c.message.edit_text("🚶‍♂️ Скучные такси в другом приложении.")

@dp.message(F.text == "📄 ОФЕРТА")
async def show_legal(m: types.Message):
    await m.answer(LEGAL_TEXT)

@dp.message(F.text == "⚖️ Вызвать адвоката")
async def lawyer_menu(m: types.Message):
    await m.answer("⚖️ <b>ЮРИДИЧЕСКИЙ ОТДЕЛ</b>\nНаш партнер:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚨 ПЕРЕЙТИ К АДВОКАТУ", url=LAWYER_LINK)]]))

@dp.message(F.text == "👤 Мой Кабинет")
async def client_cab(m: types.Message):
    if not is_client_accepted(m.from_user.id): return await m.answer("/start")
    spent = get_client_stats(m.from_user.id)
    status = get_status_name(spent)
    conn = sqlite3.connect(DB_PATH)
    hist = conn.execute("SELECT service_name, price FROM order_history WHERE client_id=? ORDER BY id DESC LIMIT 5", (m.from_user.id,)).fetchall()
    conn.close()
    
    h_txt = "\n".join([f"▪ {h[0]} ({h[1]}₽)" for h in hist]) or "Нет истории шоу."
    
    kb = []
    if m.from_user.id in active_orders:
        kb.append([InlineKeyboardButton(text="💬 ЧАТ С АРТИСТОМ", callback_data="enter_chat")])
    
    await m.answer(f"👤 <b>КАБИНЕТ ЗРИТЕЛЯ</b>\n👑 Титул: <b>{status}</b>\n💰 Инвестировано в эмоции: <b>{spent}₽</b>\n\n📜 <b>ИСТОРИЯ ШОУ:</b>\n{h_txt}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb) if kb else None)

@dp.callback_query(F.data == "enter_chat")
async def enter_chat_mode(c: types.CallbackQuery, state: FSMContext):
    uid = c.from_user.id
    pid = None
    if uid in active_orders: pid = active_orders[uid].get('driver_id')
    if not pid:
        for k, v in active_orders.items():
            if v.get('driver_id') == uid: pid = k; break
    if not pid: return await c.answer("❌ Нет связи", show_alert=True)
    
    await state.update_data(chat_partner=pid)
    await state.set_state(ChatState.active)
    await c.message.answer("💬 <b>КАНАЛ СВЯЗИ ОТКРЫТ!</b>\nПишите сообщение, отправляйте фото или голосовые.", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🚪 Конец связи")]], resize_keyboard=True))
    await c.answer()

@dp.message(ChatState.active)
async def chat_relay(m: types.Message, state: FSMContext):
    if m.text == "🚪 Конец связи":
        await state.clear()
        if get_driver_info(m.from_user.id): return await cab(m, state)
        else: return await m.answer("Связь завершена.", reply_markup=main_kb)
    
    d = await state.get_data()
    await m.copy_to(chat_id=d.get('chat_partner'))

# --- TAXI (SEARCH) ---
async def broadcast_to_drivers_func(cid, txt, kb):
    adm = get_all_admins_ids()
    msg_map = {}
    for a in adm:
        try: 
            m = await bot.send_message(a, f"🚨 {txt}", reply_markup=kb)
            msg_map[a] = m.message_id
        except: pass
    
    if cid in active_orders: active_orders[cid]['admin_msg_ids'] = msg_map
    
    await bot.send_message(cid, "📡 <i>Ищем свободного Артиста...</i>")
    await asyncio.sleep(1)
    
    tasks = []
    for d in get_active_drivers():
        if d not in adm:
            tasks.append(safe_send_message(d, f"⚡ {txt}", kb))
    if tasks: await asyncio.gather(*tasks)

@dp.message(F.text == "🎭 Найти Артиста (с авто)")
async def t_s(m: types.Message, s: FSMContext):
    await s.clear()
    await m.answer("📍 <b>Где начинаем шоу?</b> (Адрес подачи)", reply_markup=types.ReplyKeyboardRemove())
    await s.set_state(OrderRide.waiting_for_from)

@dp.message(OrderRide.waiting_for_from)
async def t_f(m: types.Message, s: FSMContext):
    await s.update_data(fr=m.text)
    await m.answer("🏁 <b>Куда едем?</b>")
    await s.set_state(OrderRide.waiting_for_to)

@dp.message(OrderRide.waiting_for_to)
async def t_t(m: types.Message, s: FSMContext):
    await s.update_data(to=m.text)
    await m.answer("📞 <b>Телефон для связи:</b>")
    await s.set_state(OrderRide.waiting_for_phone)

@dp.message(OrderRide.waiting_for_phone)
async def t_p(m: types.Message, s: FSMContext):
    await s.update_data(ph=m.text)
    await m.answer("💰 <b>Предложите гонорар (цена поездки):</b>")
    await s.set_state(OrderRide.waiting_for_price)

@dp.message(OrderRide.waiting_for_price)
async def t_end(m: types.Message, s: FSMContext):
    d = await s.get_data()
    cid = m.from_user.id
    active_orders[cid] = {"type":"taxi", "status":"pending", "price":m.text, "from":d['fr'], "to":d['to'], "phone":d['ph']}
    await m.answer("✅ <b>Заявка в эфире!</b>", reply_markup=main_kb)
    await s.clear()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ РОЛЬ", callback_data=f"t_ok_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"t_bid_{cid}")]])
    await broadcast_to_drivers_func(cid, f"🎭 <b>ЗАПРОС НА ПЕРФОРМАНС</b>\n📍 {d['fr']} -> {d['to']}\n💰 {m.text}", kb)

@dp.callback_query(F.data.startswith("t_ok_"))
async def t_ok(c: types.CallbackQuery, state: FSMContext):
    cid = int(c.data.split("_")[2])
    did = c.from_user.id
    o = active_orders.get(cid)
    
    if not o or o["status"] != "pending": return await c.answer("Роль уже занята!")
    
    o["status"] = "accepted"
    o["driver_id"] = did
    set_linked_driver(cid, did)
    info = get_driver_info(did)
    
    # Update admins
    for aid, mid in o.get('admin_msg_ids', {}).items():
        try: await bot.edit_message_text(chat_id=aid, message_id=mid, text=f"🚫 <b>ЗАКАЗ ПРИНЯЛ: {info[0]}</b>", reply_markup=None)
        except: pass
    
    dkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 ЧАТ", callback_data="enter_chat"), InlineKeyboardButton(text="🏁 ФИНАЛ", callback_data=f"ask_finish_{cid}")]])
    await c.message.edit_text(f"✅ <b>Роль принята!</b>\nЗритель: {o['phone']}", reply_markup=dkb)
    
    ckb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 ЧАТ", callback_data="enter_chat")],
        [InlineKeyboardButton(text="💸 ГОНОРАР ПЕРЕВЕДЕН", callback_data=f"cli_pay_{cid}"), InlineKeyboardButton(text="➕ ЗАЕЗД", callback_data="add_stop")],
        [InlineKeyboardButton(text="🆘 SOS", callback_data=f"sos_{did}")]
    ])
    await bot.send_message(cid, f"🎭 <b>АРТИСТ ВЫЕХАЛ!</b>\n👤 {info[7]}\n🚘 {info[1]}\n📞 {o['phone']}\n💰 {o['price']}₽\n🔐 Код: <code>{info[5]}</code>", reply_markup=ckb)

@dp.callback_query(F.data.startswith("sos_"))
async def sos_btn(c: types.CallbackQuery):
    did = int(c.data.split("_")[1])
    cid = c.from_user.id
    for aid in get_all_admins_ids():
        await safe_send_message(aid, f"🆘 <b>SOS ТРЕВОГА!</b>\nКлиент: {cid}\nВодитель: {did}")
    await c.answer("🚨 SOS ОТПРАВЛЕН АДМИНАМ!", show_alert=True)

@dp.callback_query(F.data.startswith("cli_pay_"))
async def cli_pay(c: types.CallbackQuery):
    did = active_orders[int(c.data.split("_")[2])]['driver_id']
    await bot.send_message(did, "💸 <b>Клиент сообщил об оплате!</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data=f"drv_confirm_{c.data.split('_')[2]}")] ]))
    await c.message.edit_text("⏳ Ждем подтверждения Артиста...")

@dp.callback_query(F.data.startswith("drv_confirm_"))
async def drv_con(c: types.CallbackQuery):
    cid = int(c.data.split("_")[2])
    await bot.send_message(cid, "✅ <b>Оплата принята!</b>")
    await c.message.edit_text("✅ Принято.")

@dp.callback_query(F.data == "add_stop")
async def add_stop(c: types.CallbackQuery, s: FSMContext):
    await c.message.answer("Адрес заезда:")
    await s.set_state(AddStop.waiting_for_address)

@dp.message(AddStop.waiting_for_address)
async def add_stop_p(m: types.Message, s: FSMContext):
    await s.update_data(a=m.text)
    await m.answer("Доплата (руб):")
    await s.set_state(AddStop.waiting_for_price)

@dp.message(AddStop.waiting_for_price)
async def add_stop_f(m: types.Message, s: FSMContext):
    d = await s.get_data()
    cid = m.from_user.id
    did = active_orders[cid]['driver_id']
    await bot.send_message(did, f"📍 <b>Заезд:</b> {d['a']}\n💰 +{m.text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"stop_ok_{cid}_{m.text}")]]))
    await m.answer("⏳ Отправлено Артисту...")
    await s.clear()

@dp.callback_query(F.data.startswith("stop_ok_"))
async def stop_ok(c: types.CallbackQuery):
    cid = int(c.data.split("_")[2])
    pr = int(c.data.split("_")[3])
    active_orders[cid]['price'] = str(extract_price(active_orders[cid]['price']) + pr)
    await bot.send_message(cid, f"✅ <b>Принято!</b> Новая цена: {active_orders[cid]['price']}")
    await c.message.edit_text("✅ Точка добавлена.")

@dp.callback_query(F.data.startswith("ask_finish_"))
async def ask_fin(c: types.CallbackQuery):
    cid = int(c.data.split("_")[2])
    await bot.send_message(cid, "🏁 <b>Шоу окончено! Оценка Артисту:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⭐ 5 (ОТЛИЧНО)", callback_data=f"rate_{cid}_5")]]))
    await c.message.edit_text("✅ Сеанс закрыт.")

@dp.callback_query(F.data.startswith("rate_"))
async def rate(c: types.CallbackQuery):
    cid = int(c.data.split("_")[1])
    o = active_orders.get(cid)
    if o:
        did = o['driver_id']
        pr = extract_price(o['price'])
        log_order(cid, did, "Шоу", pr)
        update_client_spent(cid, pr)
        update_order_rating(5, did)
        add_commission(did, pr)
        await bot.send_message(did, "🎉 <b>Вам поставили 5⭐!</b>")
        del active_orders[cid]
    await c.message.edit_text("Спасибо за участие в шоу!")

# --- ТОРГ ---
@dp.callback_query(F.data.startswith("t_bid_"))
async def cnt_s(c: types.CallbackQuery, s: FSMContext):
    await s.update_data(cid=int(c.data.split("_")[2]))
    await c.message.answer("Ваша цена:")
    await s.set_state(DriverCounterOffer.waiting_for_offer)

@dp.message(DriverCounterOffer.waiting_for_offer)
async def cnt_snd(m: types.Message, s: FSMContext):
    d = await s.get_data()
    cid = d['cid']
    await bot.send_message(cid, f"⚡ <b>Артист предлагает:</b> {m.text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"t_ok_{cid}"), InlineKeyboardButton(text="❌", callback_data="decline_tos")]]))
    await m.answer("Отправлено.")
    await s.clear()

# --- MENU ---
@dp.message(F.text == "📜 CRAZY МЕНЮ (Категории)")
async def show_cats(m: types.Message, s: FSMContext):
    if not await check_tos(m): return
    did = get_linked_driver(m.from_user.id)
    
    # РЕЖИМ ВИТРИНЫ
    if not did:
        return await m.answer("🚖 <b>Вы уже в машине у Артиста?</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ДА (Ввести код)", callback_data="enter_code_dialog")],[InlineKeyboardButton(text="👀 ПРОСТО СМОТРЮ", callback_data="start_showcase")]]))
    
    act = get_driver_active_services(did)
    btns = []
    for i, n in CATEGORIES.items():
        if any(v['cat']==i and k in act for k,v in CRAZY_SERVICES.items()):
            btns.append([InlineKeyboardButton(text=n, callback_data=f"cat_{i}")])
    await m.answer("🔥 <b>ВЫБЕРИТЕ ЖАНР:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "enter_code_dialog")
async def enter_cd(c: types.CallbackQuery, s: FSMContext):
    await c.message.answer("Введите код Артиста:")
    await s.set_state(UnlockMenu.waiting_for_key)

@dp.callback_query(F.data == "start_showcase")
async def start_sc(c: types.CallbackQuery, s: FSMContext):
    await s.update_data(showcase=True)
    btns = [[InlineKeyboardButton(text=n, callback_data=f"cat_{i}")] for i, n in CATEGORIES.items()]
    await c.message.edit_text("👀 <b>РЕЖИМ ВИТРИНЫ</b> (Только просмотр):", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("cat_"))
async def cat_op(c: types.CallbackQuery, s: FSMContext):
    cid = int(c.data.split("_")[1])
    d = await s.get_data()
    showcase = d.get('showcase')
    
    if showcase:
        act = CRAZY_SERVICES.keys()
    else:
        act = get_driver_active_services(get_linked_driver(c.from_user.id))
        
    btns = [[InlineKeyboardButton(text=f"{v['name']} — {v['price']}₽", callback_data=f"srv_{k}")] for k,v in CRAZY_SERVICES.items() if v['cat']==cid and k in act]
    btns.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_c")])
    await c.message.edit_text(f"📂 <b>{CATEGORIES[cid]}</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "back_c")
async def back_c(c: types.CallbackQuery, s: FSMContext):
    await c.message.delete()
    await show_cats(c.message, s)

@dp.callback_query(F.data.startswith("srv_"))
async def srv_sel(c: types.CallbackQuery, s: FSMContext):
    k = c.data.split("_")[1]
    v = CRAZY_SERVICES[k]
    d = await s.get_data()
    
    btn = "✅ ЗАКАЗАТЬ ШОУ" if not d.get('showcase') else "🔒 ДОСТУПНО В ПОЕЗДКЕ"
    cb = f"do_{k}" if not d.get('showcase') else "alert_sc"
    
    await c.message.edit_text(f"🎭 <b>{v['name']}</b>\n💰 {v['price']}₽\n<i>{v['desc']}</i>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn, callback_data=cb)],[InlineKeyboardButton(text="🔙", callback_data=f"cat_{v['cat']}")]]))

@dp.callback_query(F.data == "alert_sc")
async def al_sc(c: types.CallbackQuery):
    await c.answer("Это демо-режим! Сядьте в машину к Артисту.", show_alert=True)

@dp.callback_query(F.data.startswith("do_"))
async def do_ord(c: types.CallbackQuery):
    k = c.data.split("_")[1]
    cid = c.from_user.id
    did = get_linked_driver(cid)
    v = CRAZY_SERVICES[k]
    
    active_orders[cid] = {"type":"crazy", "price":str(v['price']), "driver_id":did}
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"c_acc_{cid}"), InlineKeyboardButton(text="💬 ЧАТ", callback_data="enter_chat")]])
    await bot.send_message(did, f"🔔 <b>ЗАКАЗ ШОУ: {v['name']}</b>\n💰 {v['price']}", reply_markup=kb)
    await c.message.edit_text("⏳ Ждем подтверждения Артиста...")

@dp.callback_query(F.data.startswith("c_acc_"))
async def crazy_acc(c: types.CallbackQuery):
    cid = int(c.data.split("_")[2])
    i = get_driver_info(c.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 ГОНОРАР ПЕРЕВЕДЕН", callback_data=f"cli_pay_{cid}"), InlineKeyboardButton(text="💬 ЧАТ", callback_data="enter_chat")]])
    await bot.send_message(cid, f"✅ Артист готов! Реквизиты: <code>{i[2]}</code>", reply_markup=kb)
    await c.message.edit_text("✅ В работе.")

# --- REGISTRATION & CAB ---
@dp.message(Command("driver", "drive"))
async def reg_s(m: types.Message, s: FSMContext):
    if get_driver_info(m.from_user.id): return await m.answer("Уже зарегистрированы.")
    await s.clear()
    await m.answer("📝 Введите ФИО:")
    await s.set_state(DriverRegistration.waiting_for_fio)

@dp.message(DriverRegistration.waiting_for_fio)
async def reg_f(m: types.Message, s: FSMContext): await s.update_data(fio=m.text); await m.answer("Авто (Сцена):"); await s.set_state(DriverRegistration.waiting_for_car)
@dp.message(DriverRegistration.waiting_for_car)
async def reg_c(m: types.Message, s: FSMContext): await s.update_data(car=m.text); await m.answer("Реквизиты:"); await s.set_state(DriverRegistration.waiting_for_payment_info)
@dp.message(DriverRegistration.waiting_for_payment_info)
async def reg_p(m: types.Message, s: FSMContext): await s.update_data(pay=m.text); await m.answer("Придумайте Код-пароль:"); await s.set_state(DriverRegistration.waiting_for_code)
@dp.message(DriverRegistration.waiting_for_code)
async def reg_fin(m: types.Message, s: FSMContext):
    code = m.text.upper().strip()
    conn = sqlite3.connect(DB_PATH)
    # Check duplicate code by someone else
    exist = conn.execute("SELECT 1 FROM drivers WHERE access_code=? AND user_id != ?", (code, m.from_user.id)).fetchone()
    if exist:
        conn.close()
        return await m.answer("❌ Код занят другим Артистом!")
    
    d = await s.get_data()
    # Правильная регистрация с обновлением
    conn.execute("INSERT OR REPLACE INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, role) VALUES (?, ?, ?, ?, ?, ?, 'pending', 'driver')", 
                 (m.from_user.id, m.from_user.username or "U", d['fio'], d['car'], d['pay'], code))
    conn.commit()
    conn.close()
    
    init_driver_services_defaults(m.from_user.id)
    await m.answer("✅ Заявка отправлена!")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"adm_app_{m.from_user.id}")]])
    for adm in get_all_admins_ids():
        await safe_send_message(adm, f"🚨 <b>НОВЫЙ АРТИСТ:</b> {d['fio']}", kb)
    await s.clear()

@dp.callback_query(F.data.startswith("adm_app_"))
async def adm_app(c: types.CallbackQuery):
    if not is_admin(c.from_user.id): return
    did = int(c.data.split("_")[2])
    update_driver_field(did, "status", "active")
    await c.message.edit_text("✅ Принят")
    await safe_send_message(did, "🎉 Вы в труппе! /cab")

@dp.message(Command("cab"))
async def cab(m: types.Message, s: FSMContext):
    i = get_driver_info(m.from_user.id)
    await s.clear()
    if not i: return await m.answer("❌ Нет регистрации. /drive")
    
    txt = (f"🪪 <b>ГРИМЕРКА</b>\n👤 {i[7]}\n💰 Баланс: {i[3]}₽\n🔑 Код: <code>{i[5]}</code>")
    kb = [
        [InlineKeyboardButton(text="🎛 Репертуар (Меню)", callback_data="driver_menu_edit")],
        [InlineKeyboardButton(text="💸 Оплатить комиссию", callback_data="cab_pay")]
    ]
    await m.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "driver_menu_edit")
async def d_menu(c: types.CallbackQuery):
    act = get_driver_active_services(c.from_user.id)
    btns = []
    for k, v in CRAZY_SERVICES.items():
        status = "✅" if k in act else "❌"
        btns.append([InlineKeyboardButton(text=f"{status} {v['name']}", callback_data=f"tgl_{k}")])
    btns.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_cab")])
    await c.message.edit_text("🎛 <b>НАСТРОЙКА РЕПЕРТУАРА:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("tgl_"))
async def tgl(c: types.CallbackQuery):
    toggle_driver_service(c.from_user.id, c.data.split("_")[1])
    await d_menu(c)

@dp.callback_query(F.data == "back_to_cab")
async def b_cab(c: types.CallbackQuery, s: FSMContext):
    await c.message.delete()
    await cab(c.message, s)

@dp.callback_query(F.data == "cab_pay")
async def cab_pay(c: types.CallbackQuery):
    info = get_driver_info(c.from_user.id)
    boss = get_driver_info(OWNER_ID)
    await c.message.answer(f"💸 Ваш долг: <b>{info[3]}₽</b>\nПеревод Продюсеру: <b>{boss[2]}</b>")
    await c.answer()

@dp.message(UnlockMenu.waiting_for_key)
async def key_fin(m: types.Message, s: FSMContext):
    drv = get_driver_by_code(m.text.strip().upper())
    if drv:
        set_linked_driver(m.from_user.id, drv[0])
        await m.answer(f"🔓 <b>ДОСТУП ОТКРЫТ!</b>\nАртист: {drv[3]}\nАвто: {drv[2]}", reply_markup=main_kb)
        await s.clear()
    else:
        await m.answer("❌ Неверный код.")

# --- ADMINKA ---
@dp.message(Command("admin"))
async def adm(m: types.Message, s: FSMContext):
    await s.clear()
    if not is_admin(m.from_user.id): return await m.answer("⛔")
    
    conn = sqlite3.connect(DB_PATH)
    drs = conn.execute("SELECT user_id, fio, balance FROM drivers").fetchall()
    conn.close()
    
    txt = "👑 <b>ПРОДЮСЕРСКИЙ ЦЕНТР</b>\n" + "\n".join([f"• {d[1]} | {d[2]}₽ | /edit_{d[0]}" for d in drs])
    await m.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 РАССЫЛКА", callback_data="admin_broadcast")]]))

@dp.message(F.text.startswith("/edit_"))
async def ed(m: types.Message, s: FSMContext):
    if not is_admin(m.from_user.id): return
    did = int(m.text.split("_")[1])
    await s.update_data(target_did=did)
    await m.answer("Действие:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Выставить счет", callback_data=f"adm_bill_{did}")]]))

@dp.callback_query(F.data.startswith("adm_bill_"))
async def bl(c: types.CallbackQuery, s: FSMContext):
    await s.update_data(target_did=int(c.data.split("_")[2]))
    await c.message.answer("Введите сумму или текст счета:")
    await s.set_state(AdminBilling.waiting_for_custom_req)

@dp.message(AdminBilling.waiting_for_custom_req)
async def bl_s(m: types.Message, s: FSMContext):
    d = await s.get_data()
    await bot.send_message(d['target_did'], f"⚠️ <b>СЧЕТ ОТ ПРОДЮСЕРА:</b>\n{m.text}")
    await m.answer("✅ Отправлено")
    await s.clear()

@dp.callback_query(F.data == "admin_broadcast")
async def brd(c: types.CallbackQuery, s: FSMContext):
    await c.message.answer("Введите текст рассылки:")
    await s.set_state(AdminBroadcast.waiting_for_text)

@dp.message(AdminBroadcast.waiting_for_text)
async def brd_s(m: types.Message, s: FSMContext):
    count = 0
    for d in get_active_drivers():
        if await safe_send_message(d, f"📢 <b>НОВОСТИ КЛУБА:</b>\n{m.text}"): count += 1
    await m.answer(f"✅ Доставлено: {count}")
    await s.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
