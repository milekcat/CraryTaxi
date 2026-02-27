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
OWNER_ID = os.getenv("DRIVER_ID") 

if not API_TOKEN or not OWNER_ID:
    exit("⛔ Error: API_TOKEN or DRIVER_ID missing")

OWNER_ID = int(OWNER_ID)
SECOND_ADMIN_ID = 6004764782
SUPER_ADMINS = [OWNER_ID, SECOND_ADMIN_ID]

VIP_DRIVER_KEY = "CRAZY_START"
VIP_ADMIN_KEY = "BIG_BOSS_777"
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
    
    # Водители
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
    
    # Регистрация админов
    for admin_id in SUPER_ADMINS:
        cursor.execute("SELECT 1 FROM drivers WHERE user_id = ?", (admin_id,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, role, commission) VALUES (?, ?, ?, ?, ?, ?, 'active', 'owner', 0)",
                (admin_id, "BOSS", "Владелец Сети", "Black Volga VIP", "CASH", f"ADMIN_{admin_id}")
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
    # 0:username, 1:car, 2:payment, 3:balance, 4:status, 5:code, 6:role, 7:fio, 8:r_sum, 9:r_count, 10:commission
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

def is_client_accepted(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT 1 FROM clients WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return bool(res)

async def notify_admins(text, markup=None):
    admins = get_all_admins_ids()
    for admin_id in admins:
        try: await bot.send_message(admin_id, text, reply_markup=markup)
        except: pass

def extract_price(text):
    nums = re.findall(r'\d+', str(text))
    return int("".join(nums)) if nums else 0

# ==========================================
# 📜 ПОЛНОЕ МЕНЮ (ВСЕ ТЕКСТЫ)
# ==========================================
CRAZY_SERVICES = {
    "candy": {"cat": 1, "price": 0, "name": "🍬 Конфетка", "desc": "Водитель с максимально серьезным лицом вручает вам элитную конфету."},
    "nose": {"cat": 1, "price": 300, "name": "👃 Палец в носу", "desc": "Водитель едет с пальцем в носу ВСЮ поездку. Вы платите за его страдания."},
    "butler": {"cat": 1, "price": 200, "name": "🤵 Дворецкий", "desc": "Водитель открывает вам дверь, кланяется и называет 'Сир'."},
    "joke": {"cat": 1, "price": 50, "name": "🤡 Тупой анекдот", "desc": "Анекдот категории 'Б'. Смеяться не обязательно."},
    "silence": {"cat": 1, "price": 150, "name": "🤐 Полная тишина", "desc": "Режим 'Ниндзя'. Музыка выкл, водитель молчит как рыба."},
    "granny": {"cat": 2, "price": 800, "name": "👵 Бабушка-ворчунья", "desc": "Ролевая игра. Всю дорогу буду бубнить: 'Куда прешь, наркоман!'."},
    "gopnik": {"cat": 2, "price": 500, "name": "🍺 Четкий пацанчик", "desc": "Пацанский рэп, 'братишка', решение вопросиков по телефону."},
    "guide": {"cat": 2, "price": 600, "name": "🗣 Ужасный гид", "desc": "Экскурсия с выдуманными фактами."},
    "psych": {"cat": 2, "price": 1000, "name": "🧠 Психолог", "desc": "Вы жалуетесь на жизнь, водитель кивает."},
    "spy": {"cat": 3, "price": 2000, "name": "🕵️‍♂️ Шпион 007", "desc": "Черные очки, паранойя, проверка 'хвоста'."},
    "karaoke": {"cat": 3, "price": 5000, "name": "🎤 Адское Караоке", "desc": "Орем песни на полную! Фальшиво, но душевно."},
    "dance": {"cat": 3, "price": 15000, "name": "💃 Танцы на капоте", "desc": "Водитель танцует макарену перед капотом на светофоре."},
    "kidnap": {"cat": 4, "price": 30000, "name": "🎭 Дружеское похищение", "desc": "Вас (понарошку) грузят в багажник и везем в лес."},
    "tarzan": {"cat": 4, "price": 50000, "name": "🦍 Тарзан-Шоу", "desc": "Крики, удары в грудь, рычание на прохожих."},
    "burn": {"cat": 4, "price": 1000000, "name": "🔥 Сжечь машину", "desc": "Едем на пустырь. Вы платите лям, я даю канистру."},
    "eyes": {"cat": 5, "price": 0, "name": "👁️ Глаз-алмаз", "desc": "Изысканный комплимент вашим глазам."},
    "smile": {"cat": 5, "price": 0, "name": "😁 Улыбка", "desc": "Водитель скажет, что ваша улыбка освещает салон."},
    "style": {"cat": 5, "price": 0, "name": "👠 Икона стиля", "desc": "Восхищение вашим образом."},
    "improv": {"cat": 5, "price": 0, "name": "✨ Импровизация", "desc": "Водитель сам найдет, что в вас похвалить."},
    "propose": {"cat": 5, "price": 1000, "name": "💍 Сделать предложение", "desc": "Вы делаете предложение водителю. ⚠️ ПРИ ОТКАЗЕ 1000₽ НЕ ВОЗВРАЩАЮТСЯ!"}
}

CATEGORIES = {1: "🟢 ЛАЙТ", 2: "🟡 МЕДИУМ", 3: "🔴 ХАРД", 4: "☠️ VIP БЕЗУМИЕ", 5: "🌹 ДЛЯ ДАМ"}

# ==========================================
# 🛠 FSM STATES
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
    waiting_for_fio = State(); waiting_for_car = State(); waiting_for_payment_info = State(); waiting_for_code = State(); waiting_for_role = State()
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
    if is_client_accepted(message.from_user.id):
        await message.answer("⚠️ <b>CRAZY TAXI: С возвращением!</b>", reply_markup=main_kb)
    else:
        await message.answer(
            "⚠️ <b>CRAZY TAXI: ЗОНА ПОВЫШЕННОГО РИСКА</b>\n\n"
            "Мы не возим скучных людей. Мы продаем эмоции.\n\n"
            "<b>Правила:</b>\n1. Что в такси — остается в такси.\n2. Водитель — художник.\n3. Юристы бессильны.\n\nГотовы?",
            reply_markup=tos_kb
        )

@dp.callback_query(F.data == "accept_tos")
async def tos_accepted(callback: types.CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (callback.from_user.id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("🔥 <b>КОНТРАКТ ПОДПИСАН!</b>")
    await callback.message.answer("Добро пожаловать в семью.", reply_markup=main_kb)

@dp.callback_query(F.data == "decline_tos")
async def tos_declined(callback: types.CallbackQuery):
    await callback.message.edit_text("🚶‍♂️ Выход там.")

async def check_tos(message: types.Message) -> bool:
    if not is_client_accepted(message.from_user.id):
        await message.answer("🛑 <b>ДОСТУП ЗАПРЕЩЕН!</b>\nНажмите /start.")
        return False
    return True

@dp.message(F.text == "⚖️ Вызвать адвоката")
async def lawyer_menu(message: types.Message):
    await message.answer("⚖️ <b>ЮРИДИЧЕСКИЙ ОТДЕЛ</b>\nПартнер — цифровой юрист:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚨 ПЕРЕЙТИ", url=LAWYER_LINK)]]))

# ==========================================
# 🚀 МОНИТОРИНГ
# ==========================================
async def update_admins_monitor(client_id, taking_driver_id):
    order = active_orders.get(client_id)
    if not order or 'admin_msg_ids' not in order: return
    drv_info = get_driver_info(taking_driver_id)
    role = "АДМИН" if is_admin(taking_driver_id) else "ВОДИТЕЛЬ"
    text = f"🚫 <b>ЗАКАЗ ЗАБРАЛ: {role} {drv_info[0]}</b>\nФИО: {drv_info[7]}\nАвто: {drv_info[1]}\n\n{order.get('broadcasting_text','')}"
    for admin_id, msg_id in order['admin_msg_ids'].items():
        try: await bot.edit_message_text(chat_id=admin_id, message_id=msg_id, text=text, reply_markup=None)
        except: pass

async def broadcast_order_to_drivers(client_id, order_text, driver_kb, admin_kb):
    admins = get_all_admins_ids()
    admin_msg_map = {}
    admin_text = f"🚨 <b>МОНИТОРИНГ</b>\n\n{order_text}"
    for admin_id in admins:
        try:
            msg = await bot.send_message(admin_id, admin_text, reply_markup=admin_kb)
            admin_msg_map[admin_id] = msg.message_id
        except: pass
    if client_id in active_orders:
        active_orders[client_id]['admin_msg_ids'] = admin_msg_map
        active_orders[client_id]['broadcasting_text'] = order_text
    
    search_msg = await bot.send_message(client_id, "📡 <i>Ищем водителей...</i>")
    await asyncio.sleep(1.5)
    
    all_active = get_active_drivers()
    simple_drivers = [d for d in all_active if d not in admins]
    if not simple_drivers and not admins:
        await search_msg.edit_text("😔 <b>Все машины заняты.</b>")
        return
    tasks = []
    for d_id in simple_drivers:
        tasks.append(bot.send_message(d_id, f"⚡ <b>ЗАКАЗ!</b>\n{order_text}", reply_markup=driver_kb))
    if tasks: await asyncio.gather(*tasks, return_exceptions=True)
    await search_msg.edit_text("⏳ <b>Запрос отправлен!</b>")

# ==========================================
# 🚕 ТАКСИ + ТОРГ
# ==========================================
@dp.message(F.text == "🚕 Заказать такси (Поиск)")
async def taxi_start(m: types.Message, state: FSMContext):
    await state.clear(); await m.answer("📍 Откуда забрать?", reply_markup=types.ReplyKeyboardRemove()); await state.set_state(OrderRide.waiting_for_from)

@dp.message(OrderRide.waiting_for_from)
async def taxi_fr(m: types.Message, s: FSMContext):
    await s.update_data(fr=m.text); await m.answer("🏁 Куда едем?"); await s.set_state(OrderRide.waiting_for_to)

@dp.message(OrderRide.waiting_for_to)
async def taxi_to(m: types.Message, s: FSMContext):
    await s.update_data(to=m.text); await m.answer("📞 Телефон:"); await s.set_state(OrderRide.waiting_for_phone)

@dp.message(OrderRide.waiting_for_phone)
async def taxi_ph(m: types.Message, s: FSMContext):
    await s.update_data(ph=m.text); await m.answer("💰 Цена (руб):"); await s.set_state(OrderRide.waiting_for_price)

@dp.message(OrderRide.waiting_for_price)
async def taxi_send(m: types.Message, s: FSMContext):
    data = await s.get_data(); cid = m.from_user.id
    active_orders[cid] = {"type": "taxi", "status": "pending", "price": m.text, "from": data['fr'], "to": data['to'], "phone": data['ph']}
    await m.answer("✅ Заявка создана!", reply_markup=main_kb); await s.clear()
    txt = f"🚕 <b>ЗАКАЗ</b>\n📍 {data['fr']} -> {data['to']}\n💰 {m.text}"
    dkb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ БЕРУ", callback_data=f"t_ok_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"t_bid_{cid}")]])
    await broadcast_order_to_drivers(cid, txt, dkb, dkb)

@dp.callback_query(F.data.startswith("t_ok_"))
async def taxi_take(c: types.CallbackQuery):
    cid = int(c.data.split("_")[2]); did = c.from_user.id; order = active_orders.get(cid)
    if not order or order["status"]!="pending": return await c.answer("Занято!")
    order["status"]="accepted"; order["driver_id"]=did; client_driver_link[cid]=did
    await update_admins_monitor(cid, did)
    info = get_driver_info(did)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ", callback_data=f"fin_{cid}")]])
    await c.message.edit_text(f"✅ <b>Взято!</b>\n📞 {order['phone']}\n💰 {order['price']}", reply_markup=kb)
    cli_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ ТОЧКА", callback_data="add_s")]])
    await bot.send_message(cid, f"🚕 <b>Едет: {info[7]}</b>\n🚘 {info[1]}\n📞 {order['phone']}\n💰 {order['price']}\n🔐 Код: <code>{info[5]}</code>", reply_markup=cli_kb)

# --- ТОРГ ---
@dp.callback_query(F.data.startswith("t_bid_"))
async def bid_start(c: types.CallbackQuery, s: FSMContext):
    await s.clear(); await s.update_data(cid=int(c.data.split("_")[2]))
    await c.message.answer("Твоя цена:"); await s.set_state(DriverCounterOffer.waiting_for_offer); await c.answer()

@dp.message(DriverCounterOffer.waiting_for_offer)
async def bid_send(m: types.Message, s: FSMContext):
    d = await s.get_data(); cid, did = d['cid'], m.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ДА", callback_data=f"bid_y_{cid}_{did}"), InlineKeyboardButton(text="❌ НЕТ", callback_data=f"bid_n_{cid}")]])
    await bot.send_message(cid, f"⚡ <b>Водитель предлагает:</b> {m.text}", reply_markup=kb)
    await m.answer("Отправлено."); await s.clear()

@dp.callback_query(F.data.startswith("bid_y_"))
async def bid_yes(c: types.CallbackQuery):
    parts = c.data.split("_"); cid, did = int(parts[2]), int(parts[3])
    active_orders[cid]['driver_id']=did; active_orders[cid]['status']='accepted'; client_driver_link[cid]=did
    await update_admins_monitor(cid, did); info = get_driver_info(did)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ", callback_data=f"fin_{cid}")]])
    await bot.send_message(did, f"✅ Клиент согласен!\n📞 {active_orders[cid]['phone']}", reply_markup=kb)
    await c.message.edit_text(f"🚕 <b>Едет: {info[7]}</b>\n🔐 {info[5]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ ТОЧКА", callback_data="add_s")]]))

@dp.callback_query(F.data.startswith("bid_n_"))
async def bid_no(c: types.CallbackQuery): await c.message.edit_text("❌ Отказ.")

# --- ДОП. ТОЧКИ ---
@dp.callback_query(F.data == "add_s")
async def stop_start(c: types.CallbackQuery, s: FSMContext):
    await c.message.answer("📍 Куда заехать?"); await s.set_state(AddStop.waiting_for_address); await c.answer()

@dp.message(AddStop.waiting_for_address)
async def stop_pr(m: types.Message, s: FSMContext):
    await s.update_data(addr=m.text); await m.answer("💰 Доплата:"); await s.set_state(AddStop.waiting_for_price)

@dp.message(AddStop.waiting_for_price)
async def stop_snd(m: types.Message, s: FSMContext):
    d = await s.get_data(); cid = m.from_user.id; order = active_orders.get(cid)
    if not order: return await m.answer("❌ Ошибка")
    did = order['driver_id']
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ БЕРЕМ", callback_data=f"s_ok_{cid}_{m.text}"), InlineKeyboardButton(text="❌ ОТКАЗ", callback_data=f"s_no_{cid}")]])
    await bot.send_message(did, f"🔔 <b>ТОЧКА:</b> {d['addr']}\n💰 +{m.text}", reply_markup=kb)
    await m.answer("⏳ Отправлено..."); await s.clear()

@dp.callback_query(F.data.startswith("s_ok_"))
async def s_ok(c: types.CallbackQuery):
    p = c.data.split("_"); cid, extra = int(p[2]), int(p[3]); order = active_orders.get(cid)
    new_price = extract_price(order['price']) + extra; order['price'] = str(new_price)
    await bot.send_message(cid, f"✅ <b>Принято!</b> Новая цена: {new_price}"); await c.message.edit_text(f"✅ Добавлено. Итого: {new_price}")

# --- ФИНИШ ---
@dp.callback_query(F.data.startswith("fin_"))
async def finish(c: types.CallbackQuery):
    cid = int(c.data.split("_")[1]); kb = [[InlineKeyboardButton(text=f"⭐ {i}", callback_data=f"rt_{cid}_{i}") for i in [1,3,5]]]
    await bot.send_message(cid, "🏁 <b>Приехали! Оценка:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await c.message.edit_text("✅ Закрыто.")

@dp.callback_query(F.data.startswith("rt_"))
async def rate(c: types.CallbackQuery):
    p = c.data.split("_"); cid, r = int(p[1]), int(p[2]); order = active_orders.get(cid)
    if not order: return await c.message.delete()
    did = order['driver_id']; pr = extract_price(order['price'])
    lid = log_order(did, order.get('service',{}).get('name','Такси'), pr)
    update_order_rating(lid, r, did); add_commission(did, pr)
    await c.message.edit_text("🙏 Спасибо!"); await bot.send_message(did, f"🎉 Оценка: {r}⭐"); del active_orders[cid]

# ==========================================
# 📜 CRAZY МЕНЮ
# ==========================================
@dp.message(F.text == "📜 CRAZY МЕНЮ (Категории)")
async def show_cats(m: types.Message):
    if not await check_tos(m): return
    if m.from_user.id not in client_driver_link: return await m.answer("🔒 Введи код водителя!")
    btns = [[InlineKeyboardButton(text=v, callback_data=f"cat_{k}")] for k,v in CATEGORIES.items()]
    await m.answer("🔥 <b>КАТЕГОРИИ:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("cat_"))
async def open_cat(c: types.CallbackQuery):
    cat_id = int(c.data.split("_")[1]); btns = [[InlineKeyboardButton(text=f"{v['name']} - {v['price']}", callback_data=f"sv_{k}")] for k,v in CRAZY_SERVICES.items() if v['cat']==cat_id]
    btns.append([InlineKeyboardButton(text="🔙", callback_data="back_c")]); await c.message.edit_text(f"📂 {CATEGORIES[cat_id]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "back_c")
async def back_c(c: types.CallbackQuery):
    btns = [[InlineKeyboardButton(text=v, callback_data=f"cat_{k}")] for k,v in CATEGORIES.items()]
    await c.message.edit_text("🔥 <b>КАТЕГОРИИ:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("sv_"))
async def sel_s(c: types.CallbackQuery):
    k = c.data.split("_")[1]; s = CRAZY_SERVICES[k]
    kb = [[InlineKeyboardButton(text="✅ ЗАКАЗАТЬ", callback_data=f"do_{k}")], [InlineKeyboardButton(text="🔙", callback_data=f"cat_{s['cat']}")]]
    await c.message.edit_text(f"🎭 {s['name']}\n💰 {s['price']}\n<i>{s['desc']}</i>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("do_"))
async def do_ord(c: types.CallbackQuery):
    k = c.data.split("_")[-1]; s = CRAZY_SERVICES[k]; cid = c.from_user.id; did = client_driver_link.get(cid)
    active_orders[cid] = {"type":"crazy", "price":str(s["price"]), "driver_id":did, "service":s}
    await bot.send_message(did, f"🔔 <b>ЗАКАЗ: {s['name']}</b>\n💰 {s['price']}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"d_acc_{cid}")]]))
    await c.message.edit_text("⏳ Ждем...")

@dp.callback_query(F.data.startswith("d_acc_"))
async def d_acc(c: types.CallbackQuery):
    cid = int(c.data.split("_")[2]); info = get_driver_info(c.from_user.id)
    await bot.send_message(cid, f"✅ Принято! Перевод: <code>{info[2]}</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ГОТОВО", callback_data=f"fin_{cid}")]]))
    await c.message.edit_text("✅ В работе.")

@dp.message(F.text == "💡 Свой вариант (Идея)")
async def idea_h(m: types.Message, s: FSMContext): await s.clear(); await m.answer("Идея:"); await s.set_state(CustomIdea.waiting_for_idea)
@dp.message(CustomIdea.waiting_for_idea)
async def idea_p(m: types.Message, s: FSMContext): await s.update_data(idea=m.text); await m.answer("Бюджет:"); await s.set_state(CustomIdea.waiting_for_price)
@dp.message(CustomIdea.waiting_for_price)
async def idea_s(m: types.Message, s: FSMContext):
    d = await s.get_data(); cid = m.from_user.id
    active_orders[cid] = {"type":"crazy", "price":m.text, "service":{"name":"Идея", "desc":d['idea']}}
    await m.answer("✅"); await s.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"t_ok_{cid}"), InlineKeyboardButton(text="💰", callback_data=f"t_bid_{cid}")]])
    await broadcast_order_to_drivers(cid, f"💡 <b>ИДЕЯ:</b> {d['idea']}\n💰 {m.text}", kb, kb)

# ==========================================
# 🪪 КАБИНЕТ + РЕГИСТРАЦИЯ
# ==========================================
@dp.message(Command("cab"))
async def cab(m: types.Message, s: FSMContext):
    await s.clear(); info = get_driver_info(m.from_user.id)
    if not info: return await m.answer("❌ Нет регистрации.")
    r_val = round(info[8]/info[9], 1) if info[9]>0 else 0.0
    txt = f"🪪 <b>КАБИНЕТ</b>\n👤 {info[7]}\n⭐ {r_val}\n💰 Баланс: {info[3]}₽\n📊 Комиссия: {info[10]}%\n🔑 {info[5]}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Оплатить", callback_data="pay_d"), InlineKeyboardButton(text="🔄 Код", callback_data="chg_c")]])
    await m.answer(txt, reply_markup=kb)

@dp.callback_query(F.data == "pay_d")
async def pay_d(c: types.CallbackQuery):
    boss = get_driver_info(OWNER_ID); info = get_driver_info(c.from_user.id)
    await c.message.answer(f"💸 Долг: {info[3]}₽\nПеревод: {boss[2]}")

@dp.callback_query(F.data == "chg_c")
async def chg_c(c: types.CallbackQuery, s: FSMContext): await c.message.answer("Новый код:"); await s.set_state(DriverChangeCode.waiting_for_new_code)
@dp.message(DriverChangeCode.waiting_for_new_code)
async def sv_c(m: types.Message, s: FSMContext):
    try: update_driver_field(m.from_user.id, "access_code", m.text.upper().strip()); await m.answer("✅")
    except: await m.answer("❌ Занят")
    await s.clear()

@dp.message(Command("vip"))
async def vip(m: types.Message, s: FSMContext):
    await s.clear(); k = m.text.split()[1] if len(m.text.split())>1 else ""
    role = "admin" if k==VIP_ADMIN_KEY else ("driver" if k==VIP_DRIVER_KEY else None)
    if not role: return await m.answer("❌")
    await s.update_data(role=role); await m.answer(f"🔑 VIP {role.upper()}! ФИО:"); await s.set_state(DriverVipRegistration.waiting_for_fio)

@dp.message(DriverVipRegistration.waiting_for_fio)
async def v_fio(m: types.Message, s: FSMContext): await s.update_data(fio=m.text); await m.answer("🚘 Авто:"); await s.set_state(DriverVipRegistration.waiting_for_car)
@dp.message(DriverVipRegistration.waiting_for_car)
async def v_car(m: types.Message, s: FSMContext): await s.update_data(car=m.text); await m.answer("💳 Реквизиты:"); await s.set_state(DriverVipRegistration.waiting_for_payment_info)
@dp.message(DriverVipRegistration.waiting_for_payment_info)
async def v_pay(m: types.Message, s: FSMContext): await s.update_data(pay=m.text); await m.answer("🔑 Код:"); await s.set_state(DriverVipRegistration.waiting_for_code)
@dp.message(DriverVipRegistration.waiting_for_code)
async def v_fin(m: types.Message, s: FSMContext):
    d = await s.get_data(); role = d.get('role','driver')
    conn = sqlite3.connect(DB_PATH)
    try: 
        conn.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, role, commission) VALUES (?,?,?,?,?,?,'active',?,10)", 
                     (m.from_user.id, m.from_user.username, d['fio'], d['car'], d['pay'], m.text.upper(), role))
        conn.commit(); await m.answer("🚀 Готово! /cab")
    except: await m.answer("❌ Код занят")
    conn.close(); await s.clear()

@dp.message(Command("driver", "drive"))
async def reg(m: types.Message, s: FSMContext):
    await s.clear(); i = get_driver_info(m.from_user.id)
    if i: return await m.answer("Уже есть." if i[4]=='active' else "Жди.")
    await m.answer("📝 ФИО:"); await s.set_state(DriverRegistration.waiting_for_fio)

@dp.message(DriverRegistration.waiting_for_fio)
async def r1(m: types.Message, s: FSMContext): await s.update_data(fio=m.text); await m.answer("🚘 Авто:"); await s.set_state(DriverRegistration.waiting_for_car)
@dp.message(DriverRegistration.waiting_for_car)
async def r2(m: types.Message, s: FSMContext): await s.update_data(car=m.text); await m.answer("💳 Реквизиты:"); await s.set_state(DriverRegistration.waiting_for_payment_info)
@dp.message(DriverRegistration.waiting_for_payment_info)
async def r3(m: types.Message, s: FSMContext): await s.update_data(pay=m.text); await m.answer("🔑 Код:"); await s.set_state(DriverRegistration.waiting_for_code)
@dp.message(DriverRegistration.waiting_for_code)
async def r4(m: types.Message, s: FSMContext):
    d = await s.get_data(); conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, commission) VALUES (?,?,?,?,?,?,'pending',10)", 
                     (m.from_user.id, m.from_user.username, d['fio'], d['car'], d['pay'], m.text.upper()))
        conn.commit(); await m.answer("📝 Жди."); await notify_admins(f"🚨 <b>НОВЫЙ:</b> {d['fio']}", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"adm_app_{m.from_user.id}")]]))
    except: await m.answer("❌ Занят")
    conn.close(); await s.clear()

# ==========================================
# 👑 АДМИНКА
# ==========================================
@dp.message(Command("admin"))
async def adm(m: types.Message, s: FSMContext):
    await s.clear()
    if not is_admin(m.from_user.id): return await m.answer("⛔")
    conn = sqlite3.connect(DB_PATH); drs = conn.execute("SELECT user_id, fio, balance, commission FROM drivers").fetchall(); conn.close()
    txt = "👑 <b>АДМИНКА</b>\n"
    for d in drs: txt += f"• {d[1]} | {d[2]}₽ | {d[3]}% | /edit_{d[0]}\n"
    await m.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 РАССЫЛКА", callback_data="brd")]]))

@dp.callback_query(F.data.startswith("adm_app_"))
async def adm_app(c: types.CallbackQuery):
    if not is_admin(c.from_user.id): return
    did = int(c.data.split("_")[2]); update_driver_field(did, "status", "active"); await c.message.edit_text("✅")
    try: await bot.send_message(did, "🎉 Принят! /cab")
    except: pass

@dp.message(F.text.startswith("/edit_"))
async def ed_d(m: types.Message):
    if not is_admin(m.from_user.id): return
    did = int(m.text.split("_")[1]); info = get_driver_info(did)
    kb = [[InlineKeyboardButton(text="💰 Баланс", callback_data=f"eb_{did}"), InlineKeyboardButton(text="📊 %", callback_data=f"ec_{did}")],
          [InlineKeyboardButton(text="💸 Счет", callback_data=f"bl_{did}"), InlineKeyboardButton(text="🔒 Блок", callback_data=f"bk_{did}")]]
    await m.answer(f"Ред: {info[7]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "brd")
async def brd(c: types.CallbackQuery, s: FSMContext): await c.message.answer("Текст:"); await s.set_state(AdminBroadcast.waiting_for_text)
@dp.message(AdminBroadcast.waiting_for_text)
async def brd_snd(m: types.Message, s: FSMContext):
    for d in get_active_drivers():
        try: await bot.send_message(d, f"📢 <b>ВАЖНО:</b>\n{m.text}")
        except: pass
    await m.answer("✅"); await s.clear()

@dp.callback_query(F.data.startswith("eb_") | F.data.startswith("ec_"))
async def ed_val(c: types.CallbackQuery, s: FSMContext):
    p = c.data.split("_"); await s.update_data(did=int(p[1]), fld="balance" if "eb" in p[0] else "commission")
    await c.message.answer("Новое значение:"); await s.set_state(AdminEditDriver.waiting_for_new_value)

@dp.message(AdminEditDriver.waiting_for_new_value)
async def ed_sav(m: types.Message, s: FSMContext):
    d = await s.get_data(); update_driver_field(d['did'], d['fld'], m.text); await m.answer("✅"); await s.clear()

@dp.callback_query(F.data.startswith("bl_"))
async def bill_st(c: types.CallbackQuery, s: FSMContext):
    await s.update_data(did=int(c.data.split("_")[1]))
    await c.message.answer("Как?", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Босс", callback_data="b_d"), InlineKeyboardButton(text="✏️ Свои", callback_data="b_c")]]))

@dp.callback_query(F.data == "b_d")
async def b_def(c: types.CallbackQuery, s: FSMContext):
    d = await s.get_data(); b = get_driver_info(OWNER_ID); info = get_driver_info(d['did'])
    await bot.send_message(d['did'], f"⚠️ <b>ОПЛАТА:</b> {info[3]}₽\n{b[2]}"); await c.message.edit_text("✅"); await s.clear()

@dp.callback_query(F.data == "b_c")
async def b_cust(c: types.CallbackQuery, s: FSMContext): await c.message.edit_text("Текст:"); await s.set_state(AdminBilling.waiting_for_custom_req)
@dp.message(AdminBilling.waiting_for_custom_req)
async def b_snd(m: types.Message, s: FSMContext):
    d = await s.get_data(); await bot.send_message(d['did'], f"⚠️ <b>СЧЕТ:</b>\n{m.text}"); await m.answer("✅"); await s.clear()

@dp.callback_query(F.data.startswith("bk_"))
async def blk(c: types.CallbackQuery):
    did = int(c.data.split("_")[1]); i = get_driver_info(did)
    if i[6]=='owner': return
    update_driver_field(did, "status", "blocked" if i[4]=="active" else "active"); await c.message.edit_text("🔄")

@dp.message(F.text == "🔐 Ввести КЛЮЧ услуги")
async def key_st(m: types.Message, s: FSMContext): await s.clear(); await m.answer("Код:"); await s.set_state(UnlockMenu.waiting_for_key)
@dp.message(UnlockMenu.waiting_for_key)
async def key_pr(m: types.Message, s: FSMContext):
    drv = get_driver_by_code(m.text.strip().upper())
    if drv: client_driver_link[m.from_user.id]=drv[0]; await m.answer(f"🔓 OK: {drv[3]}", reply_markup=main_kb); await s.clear()
    else: await m.answer("❌")

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
