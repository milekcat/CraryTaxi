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
# 📜 КОНСТАНТЫ
# ==========================================
LEGAL_TEXT = (
    "<b>📜 ПУБЛИЧНАЯ ОФЕРТА</b>\n\n"
    "1. <b>Суть:</b> Мы — агрегатор поиска творческих попутчиков (Артистов).\n"
    "2. <b>Транспорт:</b> Перевозка — дело Артиста. Мы продаем шоу.\n"
    "3. <b>Безопасность:</b> Не мешайте водителю вести машину.\n"
)

CRAZY_SERVICES = {
    "candy": {"cat": 1, "price": 0, "name": "🍬 Презент", "desc": "Элитная конфета и уважение."},
    "nose": {"cat": 1, "price": 300, "name": "👃 Палец в носу", "desc": "Артист едет с пальцем в носу."},
    "butler": {"cat": 1, "price": 200, "name": "🤵 Дворецкий", "desc": "Открываем дверь, называем Сир."},
    "joke": {"cat": 1, "price": 50, "name": "🤡 Анекдот", "desc": "Юмор категории Б."},
    "silence": {"cat": 1, "price": 150, "name": "🤐 Ниндзя", "desc": "Полная тишина."},
    "granny": {"cat": 2, "price": 800, "name": "👵 Бабуля", "desc": "Ворчание всю дорогу."},
    "gopnik": {"cat": 2, "price": 500, "name": "🍺 Пацанчик", "desc": "Решаем вопросики."},
    "guide": {"cat": 2, "price": 600, "name": "🗣 Горе-Гид", "desc": "Выдуманные факты о городе."},
    "psych": {"cat": 2, "price": 1000, "name": "🧠 Психолог", "desc": "Слушаем нытье, киваем."},
    "spy": {"cat": 3, "price": 2000, "name": "🕵️‍♂️ 007", "desc": "Паранойя, проверка хвоста."},
    "karaoke": {"cat": 3, "price": 5000, "name": "🎤 Караоке", "desc": "Орем песни дуэтом."},
    "dance": {"cat": 3, "price": 15000, "name": "💃 Танцы", "desc": "Макарена на светофоре."},
    "kidnap": {"cat": 4, "price": 30000, "name": "🎭 Похищение", "desc": "В багажнике в лес (понарошку)."},
    "tarzan": {"cat": 4, "price": 50000, "name": "🦍 Тарзан", "desc": "Рычим на прохожих."},
    "burn": {"cat": 4, "price": 1000000, "name": "🔥 Сжечь авто", "desc": "Эпичный финал на пустыре."},
    "eyes": {"cat": 5, "price": 0, "name": "👁️ Глаз-алмаз", "desc": "Комплимент глазам."},
    "smile": {"cat": 5, "price": 0, "name": "😁 Улыбка", "desc": "Комплимент улыбке."},
    "style": {"cat": 5, "price": 0, "name": "👠 Стиль", "desc": "Восхищение одеждой."},
    "improv": {"cat": 5, "price": 0, "name": "✨ Импровизация", "desc": "Фристайл."},
    "propose": {"cat": 5, "price": 1000, "name": "💍 Предложение", "desc": "Руки и сердца."}
}
CATEGORIES = {1: "🟢 ЛАЙТ", 2: "🟡 МЕДИУМ", 3: "🔴 ХАРД", 4: "☠️ VIP БЕЗУМИЕ", 5: "🌹 ДЛЯ ДАМ"}

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
    cursor.execute("CREATE TABLE IF NOT EXISTS driver_services (driver_id INTEGER, service_key TEXT, is_active BOOLEAN DEFAULT 1, PRIMARY KEY (driver_id, service_key))")
    cursor.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER DEFAULT NULL, total_spent INTEGER DEFAULT 0)")
    cursor.execute("CREATE TABLE IF NOT EXISTS order_history (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, driver_id INTEGER, service_name TEXT, price INTEGER, rating INTEGER DEFAULT 0, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    
    for admin_id in SUPER_ADMINS:
        try:
            cursor.execute("INSERT OR IGNORE INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, role) VALUES (?, 'BOSS', 'Владелец', 'VIP', 'CASH', ?, 'active', 'owner')", (admin_id, f"ADMIN_{admin_id}"))
            cursor.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (admin_id,))
            for key in CRAZY_SERVICES:
                cursor.execute("INSERT OR REPLACE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, 1)", (admin_id, key))
        except: pass
    conn.commit(); conn.close()

init_db()

# ==========================================
# 🛠 ФУНКЦИИ
# ==========================================
def is_client_accepted(user_id):
    conn = sqlite3.connect(DB_PATH); res = conn.execute("SELECT 1 FROM clients WHERE user_id = ?", (user_id,)).fetchone(); conn.close()
    return bool(res)

def get_client_stats(user_id):
    conn = sqlite3.connect(DB_PATH); res = conn.execute("SELECT total_spent FROM clients WHERE user_id=?", (user_id,)).fetchone(); conn.close()
    return res[0] if res else 0

def update_client_spent(user_id, amount):
    conn = sqlite3.connect(DB_PATH); conn.execute("UPDATE clients SET total_spent = total_spent + ? WHERE user_id=?", (amount, user_id)); conn.commit(); conn.close()

def get_status_name(spent):
    if spent > 100000: return "👹 МЕЦЕНАТ"; 
    if spent > 50000: return "💀 ПРОДЮСЕР"; 
    if spent > 10000: return "🤪 ЦЕНИТЕЛЬ"; 
    return "👶 ЗРИТЕЛЬ"

def init_driver_services_defaults(driver_id):
    conn = sqlite3.connect(DB_PATH)
    for key in CRAZY_SERVICES: conn.execute("INSERT OR IGNORE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, 1)", (driver_id, key))
    conn.commit(); conn.close()

def get_driver_active_services(driver_id):
    conn = sqlite3.connect(DB_PATH); res = conn.execute("SELECT service_key FROM driver_services WHERE driver_id=? AND is_active=1", (driver_id,)).fetchall(); conn.close()
    return [r[0] for r in res]

def toggle_driver_service(driver_id, service_key):
    conn = sqlite3.connect(DB_PATH); curr = conn.execute("SELECT is_active FROM driver_services WHERE driver_id=? AND service_key=?", (driver_id, service_key)).fetchone()
    new_status = 0 if (curr and curr[0] == 1) else 1
    conn.execute("INSERT OR REPLACE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, ?)", (driver_id, service_key, new_status)); conn.commit(); conn.close()

def get_linked_driver(client_id):
    conn = sqlite3.connect(DB_PATH); res = conn.execute("SELECT linked_driver_id FROM clients WHERE user_id=?", (client_id,)).fetchone(); conn.close()
    return res[0] if res and res[0] else None

def set_linked_driver(client_id, driver_id):
    conn = sqlite3.connect(DB_PATH); conn.execute("INSERT OR REPLACE INTO clients (user_id, linked_driver_id) VALUES (?, ?)", (client_id, driver_id)); conn.commit(); conn.close()

def is_admin(user_id):
    if user_id in SUPER_ADMINS: return True
    conn = sqlite3.connect(DB_PATH); res = conn.execute("SELECT 1 FROM drivers WHERE user_id=? AND role IN ('owner', 'admin') AND status='active'", (user_id,)).fetchone(); conn.close()
    return bool(res)

def get_all_admins_ids():
    conn = sqlite3.connect(DB_PATH); res = conn.execute("SELECT user_id FROM drivers WHERE role IN ('owner', 'admin') AND status='active'").fetchall(); conn.close()
    return list(set([r[0] for r in res] + SUPER_ADMINS))

def get_active_drivers():
    conn = sqlite3.connect(DB_PATH); res = [d[0] for d in conn.execute("SELECT user_id FROM drivers WHERE status='active'").fetchall()]; conn.close(); return res

def get_driver_by_code(code):
    conn = sqlite3.connect(DB_PATH); res = conn.execute("SELECT user_id, username, car_info, fio FROM drivers WHERE access_code=? AND status='active'", (code,)).fetchone(); conn.close(); return res

def get_driver_info(user_id):
    conn = sqlite3.connect(DB_PATH); res = conn.execute("SELECT username, car_info, payment_info, balance, status, access_code, role, fio, rating_sum, rating_count, commission FROM drivers WHERE user_id=?", (user_id,)).fetchone(); conn.close(); return res

def update_driver_field(user_id, field, value):
    conn = sqlite3.connect(DB_PATH); conn.execute(f"UPDATE drivers SET {field} = ? WHERE user_id = ?", (value, user_id)); conn.commit(); conn.close()

def extract_price(text):
    nums = re.findall(r'\d+', str(text)); return int("".join(nums)) if nums else 0

def log_order(client_id, driver_id, service_name, price):
    conn = sqlite3.connect(DB_PATH); cursor = conn.cursor(); cursor.execute("INSERT INTO order_history (client_id, driver_id, service_name, price) VALUES (?, ?, ?, ?)", (client_id, driver_id, service_name, price)); conn.commit(); conn.close()

def update_order_rating(rating, driver_id):
    conn = sqlite3.connect(DB_PATH); conn.execute("UPDATE drivers SET rating_sum = rating_sum + ?, rating_count = rating_count + 1 WHERE user_id = ?", (rating, driver_id)); conn.commit(); conn.close()

def add_commission(driver_id, amount):
    if is_admin(driver_id): return 
    conn = sqlite3.connect(DB_PATH); row = conn.execute("SELECT commission FROM drivers WHERE user_id=?", (driver_id,)).fetchone(); percent = row[0] if row else 10; val = int(amount * (percent / 100))
    conn.execute("UPDATE drivers SET balance = balance + ? WHERE user_id=?", (val, driver_id)); conn.commit(); conn.close()

async def safe_send_message(chat_id, text, reply_markup=None):
    try: await bot.send_message(chat_id, text, reply_markup=reply_markup); return True
    except: return False

async def check_tos(message: types.Message) -> bool:
    if not is_client_accepted(message.from_user.id): await message.answer("🛑 <b>ДОСТУП ЗАПРЕЩЕН!</b>\nНажмите /start."); return False
    return True

# ==========================================
# FSM
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
# UI
# ==========================================
main_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🎭 Найти Артиста (с авто)")],[KeyboardButton(text="📜 CRAZY МЕНЮ (Категории)")],[KeyboardButton(text="👤 Мой Кабинет"), KeyboardButton(text="📄 ОФЕРТА")]], resize_keyboard=True)
tos_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНИМАЮ", callback_data="accept_tos")],[InlineKeyboardButton(text="❌ Ухожу", callback_data="decline_tos")]])

# ==========================================
# ЛОГИКА
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if is_client_accepted(message.from_user.id): await message.answer("⚠️ <b>CRAZY MOOD:</b> Мы ждали тебя.", reply_markup=main_kb)
    else: await message.answer("⚠️ <b>ЭТО НЕ ТАКСИ. ЭТО ШОУ.</b>\nГотовы?", reply_markup=tos_kb)

@dp.callback_query(F.data == "accept_tos")
async def tos_accepted(c: types.CallbackQuery):
    conn = sqlite3.connect(DB_PATH); conn.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (c.from_user.id,)); conn.commit(); conn.close()
    await c.message.edit_text("🔥"); await c.message.answer("Добро пожаловать.", reply_markup=main_kb)

@dp.callback_query(F.data == "decline_tos")
async def tos_declined(c: types.CallbackQuery): await c.message.edit_text("🚶‍♂️")

@dp.message(F.text == "📄 ОФЕРТА")
async def show_legal(m: types.Message): await m.answer(LEGAL_TEXT)

@dp.message(F.text == "👤 Мой Кабинет")
async def client_cab(m: types.Message):
    if not is_client_accepted(m.from_user.id): return await m.answer("/start")
    spent = get_client_stats(m.from_user.id); status = get_status_name(spent)
    conn = sqlite3.connect(DB_PATH); hist = conn.execute("SELECT service_name, price FROM order_history WHERE client_id=? ORDER BY id DESC LIMIT 5", (m.from_user.id,)).fetchall(); conn.close()
    h_txt = "\n".join([f"▪ {h[0]} ({h[1]}₽)" for h in hist]) or "-"
    kb = [[InlineKeyboardButton(text="💬 ЧАТ", callback_data="enter_chat")]] if m.from_user.id in active_orders else None
    await m.answer(f"👤 <b>ЗРИТЕЛЬ</b>\n👑 {status}\n💰 {spent}₽\n\n{h_txt}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb) if kb else None)

@dp.callback_query(F.data == "enter_chat")
async def enter_chat_mode(c: types.CallbackQuery, state: FSMContext):
    uid = c.from_user.id; pid = None
    if uid in active_orders: pid = active_orders[uid].get('driver_id')
    if not pid:
        for k, v in active_orders.items():
            if v.get('driver_id') == uid: pid = k; break
    if not pid: return await c.answer("Нет связи", show_alert=True)
    await state.update_data(chat_partner=pid); await state.set_state(ChatState.active)
    await c.message.answer("💬 <b>ЧАТ</b>", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🚪 Выход")]], resize_keyboard=True)); await c.answer()

@dp.message(ChatState.active)
async def chat_relay(m: types.Message, state: FSMContext):
    if m.text == "🚪 Выход":
        await state.clear()
        if get_driver_info(m.from_user.id): return await cab(m, state)
        else: return await m.answer("Ок.", reply_markup=main_kb)
    d = await state.get_data(); await m.copy_to(chat_id=d.get('chat_partner'))

# --- TAXI ---
async def brd_drv(cid, txt, kb):
    adm = get_all_admins_ids(); msg_map = {}
    for a in adm:
        try: m = await bot.send_message(a, f"🚨 {txt}", reply_markup=kb); msg_map[a] = m.message_id
        except: pass
    if cid in active_orders: active_orders[cid]['admin_msg_ids'] = msg_map
    await bot.send_message(cid, "📡 <i>Поиск Артиста...</i>"); await asyncio.sleep(1)
    tasks = [safe_send_message(d, f"⚡ {txt}", kb) for d in get_active_drivers() if d not in adm]
    if tasks: await asyncio.gather(*tasks)

@dp.message(F.text == "🎭 Найти Артиста (с авто)")
async def t_s(m: types.Message, s: FSMContext): await s.clear(); await m.answer("📍 Где вы?"); await s.set_state(OrderRide.waiting_for_from)
@dp.message(OrderRide.waiting_for_from)
async def t_f(m: types.Message, s: FSMContext): await s.update_data(fr=m.text); await m.answer("🏁 Куда?"); await s.set_state(OrderRide.waiting_for_to)
@dp.message(OrderRide.waiting_for_to)
async def t_t(m: types.Message, s: FSMContext): await s.update_data(to=m.text); await m.answer("📞 Телефон:"); await s.set_state(OrderRide.waiting_for_phone)
@dp.message(OrderRide.waiting_for_phone)
async def t_p(m: types.Message, s: FSMContext): await s.update_data(ph=m.text); await m.answer("💰 Цена?"); await s.set_state(OrderRide.waiting_for_price)
@dp.message(OrderRide.waiting_for_price)
async def t_end(m: types.Message, s: FSMContext):
    d = await s.get_data(); cid = m.from_user.id
    active_orders[cid] = {"type":"taxi", "status":"pending", "price":m.text, "from":d['fr'], "to":d['to'], "phone":d['ph']}
    await m.answer("✅", reply_markup=main_kb); await s.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"t_ok_{cid}"), InlineKeyboardButton(text="💰", callback_data=f"t_bid_{cid}")]])
    await brd_drv(cid, f"ЗАКАЗ\n{d['fr']} -> {d['to']}\n💰 {m.text}", kb)

@dp.callback_query(F.data.startswith("t_ok_"))
async def t_ok(c: types.CallbackQuery, state: FSMContext):
    cid = int(c.data.split("_")[2]); did = c.from_user.id; o = active_orders.get(cid)
    if not o or o["status"] != "pending": return await c.answer("Занято")
    o["status"] = "accepted"; o["driver_id"] = did; set_linked_driver(cid, did)
    info = get_driver_info(did)
    for aid, mid in o.get('admin_msg_ids', {}).items():
        try: await bot.edit_message_text(chat_id=aid, message_id=mid, text=f"🚫 ВЗЯЛ: {info[0]}", reply_markup=None)
        except: pass
    
    dkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬", callback_data="enter_chat"), InlineKeyboardButton(text="🏁", callback_data=f"ask_finish_{cid}")]])
    await c.message.edit_text(f"✅ Взято. Клиент: {o['phone']}", reply_markup=dkb)
    ckb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬", callback_data="enter_chat"), InlineKeyboardButton(text="💸", callback_data=f"cli_pay_{cid}"), InlineKeyboardButton(text="➕", callback_data="add_stop")]])
    await bot.send_message(cid, f"🎭 <b>Едет: {info[7]}</b>\n🚘 {info[1]}\n📞 {o['phone']}\n💰 {o['price']}", reply_markup=ckb)

@dp.callback_query(F.data.startswith("cli_pay_"))
async def cli_pay(c: types.CallbackQuery):
    did = active_orders[int(c.data.split("_")[2])]['driver_id']
    await bot.send_message(did, "💸 Клиент оплатил!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"drv_confirm_{c.data.split('_')[2]}")] ])) # <-- ИСПРАВЛЕНО
    await c.message.edit_text("⏳")

@dp.callback_query(F.data.startswith("drv_confirm_"))
async def drv_con(c: types.CallbackQuery): await bot.send_message(int(c.data.split("_")[2]), "✅ Оплата принята"); await c.message.edit_text("✅")

@dp.callback_query(F.data == "add_stop")
async def add_stop(c: types.CallbackQuery, s: FSMContext): await c.message.answer("Адрес:"); await s.set_state(AddStop.waiting_for_address)
@dp.message(AddStop.waiting_for_address)
async def add_stop_p(m: types.Message, s: FSMContext): await s.update_data(a=m.text); await m.answer("Доплата:"); await s.set_state(AddStop.waiting_for_price)
@dp.message(AddStop.waiting_for_price)
async def add_stop_f(m: types.Message, s: FSMContext):
    d = await s.get_data(); cid = m.from_user.id; did = active_orders[cid]['driver_id']
    await bot.send_message(did, f"📍 {d['a']}\n💰 +{m.text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"stop_ok_{cid}_{m.text}")]]))
    await m.answer("⏳"); await s.clear()

@dp.callback_query(F.data.startswith("stop_ok_"))
async def stop_ok(c: types.CallbackQuery):
    cid = int(c.data.split("_")[2]); pr = int(c.data.split("_")[3])
    active_orders[cid]['price'] = str(extract_price(active_orders[cid]['price']) + pr)
    await bot.send_message(cid, f"✅ Новая цена: {active_orders[cid]['price']}"); await c.message.edit_text("✅")

@dp.callback_query(F.data.startswith("ask_finish_"))
async def ask_fin(c: types.CallbackQuery):
    cid = int(c.data.split("_")[2])
    await bot.send_message(cid, "🏁 Оценка:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⭐ 5", callback_data=f"rate_{cid}_5")]]))
    await c.message.edit_text("✅")

@dp.callback_query(F.data.startswith("rate_"))
async def rate(c: types.CallbackQuery):
    cid = int(c.data.split("_")[1]); o = active_orders.get(cid)
    if o:
        did = o['driver_id']; pr = extract_price(o['price'])
        log_order(cid, did, "Шоу", pr); update_client_spent(cid, pr); update_order_rating(5, did); add_commission(did, pr)
        await bot.send_message(did, "🎉 5⭐"); del active_orders[cid]
    await c.message.edit_text("🙏")

# --- MENU ---
@dp.message(F.text == "📜 CRAZY МЕНЮ (Категории)")
async def show_cats(m: types.Message, s: FSMContext):
    if not await check_tos(m): return
    did = get_linked_driver(m.from_user.id)
    if not did:
        return await m.answer("🚖 Вы в машине?", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ДА (Ввести код)", callback_data="enter_code_dialog")],[InlineKeyboardButton(text="👀 НЕТ (Витрина)", callback_data="start_showcase")]]))
    
    act = get_driver_active_services(did); btns = []
    for i, n in CATEGORIES.items():
        if any(v['cat']==i and k in act for k,v in CRAZY_SERVICES.items()): btns.append([InlineKeyboardButton(text=n, callback_data=f"cat_{i}")])
    await m.answer("🔥", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "enter_code_dialog")
async def enter_cd(c: types.CallbackQuery, s: FSMContext): await c.message.answer("Код:"); await s.set_state(UnlockMenu.waiting_for_key)

@dp.callback_query(F.data == "start_showcase")
async def start_sc(c: types.CallbackQuery, s: FSMContext):
    await s.update_data(showcase=True); btns = [[InlineKeyboardButton(text=n, callback_data=f"cat_{i}")] for i, n in CATEGORIES.items()]
    await c.message.edit_text("👀 ВИТРИНА:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("cat_"))
async def cat_op(c: types.CallbackQuery, s: FSMContext):
    cid = int(c.data.split("_")[1]); d = await s.get_data(); showcase = d.get('showcase')
    act = get_driver_active_services(get_linked_driver(c.from_user.id)) if not showcase else CRAZY_SERVICES.keys()
    btns = [[InlineKeyboardButton(text=f"{v['name']} {v['price']}", callback_data=f"srv_{k}")] for k,v in CRAZY_SERVICES.items() if v['cat']==cid and k in act]
    btns.append([InlineKeyboardButton(text="🔙", callback_data="back_c")])
    await c.message.edit_text(CATEGORIES[cid], reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "back_c")
async def back_c(c: types.CallbackQuery, s: FSMContext): await c.message.delete(); await show_cats(c.message, s)

@dp.callback_query(F.data.startswith("srv_"))
async def srv_sel(c: types.CallbackQuery, s: FSMContext):
    k = c.data.split("_")[1]; v = CRAZY_SERVICES[k]; d = await s.get_data()
    btn = "✅ ЗАКАЗАТЬ" if not d.get('showcase') else "🔒 ТОЛЬКО В ПОЕЗДКЕ"
    cb = f"do_{k}" if not d.get('showcase') else "alert_sc"
    await c.message.edit_text(f"🎭 {v['name']}\n💰 {v['price']}\n{v['desc']}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn, callback_data=cb)],[InlineKeyboardButton(text="🔙", callback_data=f"cat_{v['cat']}")]]))

@dp.callback_query(F.data == "alert_sc")
async def al_sc(c: types.CallbackQuery): await c.answer("Это демо! Сядьте в машину.", show_alert=True)

@dp.callback_query(F.data.startswith("do_"))
async def do_ord(c: types.CallbackQuery):
    k = c.data.split("_")[1]; cid = c.from_user.id; did = get_linked_driver(cid); v = CRAZY_SERVICES[k]
    active_orders[cid] = {"type":"crazy", "price":str(v['price']), "driver_id":did}
    await bot.send_message(did, f"🔔 {v['name']} - {v['price']}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"c_acc_{cid}")]]))
    await c.message.edit_text("⏳")

@dp.callback_query(F.data.startswith("c_acc_"))
async def crazy_acc(c: types.CallbackQuery):
    cid = int(c.data.split("_")[2]); i = get_driver_info(c.from_user.id)
    await bot.send_message(cid, f"✅ Готово! Перевод: {i[2]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸", callback_data=f"cli_pay_{cid}")]]))
    await c.message.edit_text("✅")

# --- REGISTRATION ---
@dp.message(Command("driver", "drive"))
async def reg_s(m: types.Message, s: FSMContext):
    if get_driver_info(m.from_user.id): return await m.answer("Уже есть.")
    await s.clear(); await m.answer("ФИО:"); await s.set_state(DriverRegistration.waiting_for_fio)

@dp.message(DriverRegistration.waiting_for_fio)
async def reg_f(m: types.Message, s: FSMContext): await s.update_data(fio=m.text); await m.answer("Авто:"); await s.set_state(DriverRegistration.waiting_for_car)
@dp.message(DriverRegistration.waiting_for_car)
async def reg_c(m: types.Message, s: FSMContext): await s.update_data(car=m.text); await m.answer("Реквизиты:"); await s.set_state(DriverRegistration.waiting_for_payment_info)
@dp.message(DriverRegistration.waiting_for_payment_info)
async def reg_p(m: types.Message, s: FSMContext): await s.update_data(pay=m.text); await m.answer("Придумайте Код:"); await s.set_state(DriverRegistration.waiting_for_code)
@dp.message(DriverRegistration.waiting_for_code)
async def reg_fin(m: types.Message, s: FSMContext):
    code = m.text.upper().strip()
    conn = sqlite3.connect(DB_PATH)
    exist = conn.execute("SELECT 1 FROM drivers WHERE access_code=?", (code,)).fetchone()
    if exist: 
        conn.close()
        return await m.answer("❌ Код занят! Придумайте другой.")
    
    d = await s.get_data()
    # Фикс уникальности: REPLACE
    conn.execute("INSERT OR REPLACE INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, role) VALUES (?, ?, ?, ?, ?, ?, 'pending', 'driver')", 
                 (m.from_user.id, m.from_user.username or "U", d['fio'], d['car'], d['pay'], code))
    conn.commit()
    conn.close()
    
    init_driver_services_defaults(m.from_user.id)
    await m.answer("✅ Заявка отправлена!")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"adm_app_{m.from_user.id}")]])
    for adm in get_all_admins_ids():
        await safe_send_message(adm, f"🚨 <b>НОВЫЙ:</b> {d['fio']}", kb)
    await s.clear()

@dp.callback_query(F.data.startswith("adm_app_"))
async def adm_app(c: types.CallbackQuery):
    if not is_admin(c.from_user.id): return
    did = int(c.data.split("_")[2]); update_driver_field(did, "status", "active")
    await c.message.edit_text("✅ Принят"); await safe_send_message(did, "🎉 Вы приняты! /cab")

@dp.message(Command("cab"))
async def cab(m: types.Message, s: FSMContext):
    i = get_driver_info(m.from_user.id); await s.clear()
    if not i: return await m.answer("❌ /drive")
    await m.answer(f"🪪 <b>{i[7]}</b>\n💰 {i[3]}₽\n🔑 {i[5]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎛 Меню", callback_data="driver_menu_edit")]]))

@dp.callback_query(F.data == "driver_menu_edit")
async def d_menu(c: types.CallbackQuery):
    act = get_driver_active_services(c.from_user.id)
    btns = [[InlineKeyboardButton(text=f"{'✅' if k in act else '❌'} {v['name']}", callback_data=f"tgl_{k}")] for k,v in CRAZY_SERVICES.items()]
    btns.append([InlineKeyboardButton(text="🔙", callback_data="back_to_cab")])
    await c.message.edit_text("🎛", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("tgl_"))
async def tgl(c: types.CallbackQuery): toggle_driver_service(c.from_user.id, c.data.split("_")[1]); await d_menu(c)
@dp.callback_query(F.data == "back_to_cab")
async def b_cab(c: types.CallbackQuery, s: FSMContext): await c.message.delete(); await cab(c.message, s)

@dp.message(UnlockMenu.waiting_for_key)
async def key_fin(m: types.Message, s: FSMContext):
    drv = get_driver_by_code(m.text.strip().upper())
    if drv: set_linked_driver(m.from_user.id, drv[0]); await m.answer(f"🔓 {drv[3]}", reply_markup=main_kb); await s.clear()
    else: await m.answer("❌")

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
