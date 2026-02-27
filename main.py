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
OWNER_ID = os.getenv("DRIVER_ID") 

if not API_TOKEN or not OWNER_ID:
    logging.error("⛔ КРИТИЧЕСКАЯ ОШИБКА: Токены не найдены!")
    exit()

OWNER_ID = int(OWNER_ID)
SECOND_ADMIN_ID = 6004764782
SUPER_ADMINS = [OWNER_ID, SECOND_ADMIN_ID]

# 🔑 СЕКРЕТНЫЙ КЛЮЧ ВОДИТЕЛЯ
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
                "INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status, role, commission) VALUES (?, ?, ?, ?, ?, ?, 'active', 'owner', 0)",
                (admin_id, "BOSS", "Владелец Сети", "⚫ ЧЕРНАЯ ВОЛГА (БОСС)", "Сбер: +70000000000", f"ADMIN_{admin_id}", 0)
            )
        else:
            cursor.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (admin_id,))
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 🛠 УТИЛИТЫ
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

def extract_price(text):
    nums = re.findall(r'\d+', str(text))
    return int("".join(nums)) if nums else 0

# ==========================================
# 📜 ПОЛНОЕ КРЕЙЗИ МЕНЮ
# ==========================================
CRAZY_SERVICES = {
    "candy": {"cat": 1, "price": 0, "name": "🍬 Конфетка", "desc": "Водитель с максимально серьезным лицом (как на государственных похоронах) вручает вам элитную барбариску. Это знак глубочайшего уважения и начала крепкой дружбы."},
    "nose": {"cat": 1, "price": 300, "name": "👃 Палец в носу", "desc": "Всю поездку водитель едет с пальцем в носу. Вы платите за его моральные страдания и потерю авторитета."},
    "butler": {"cat": 1, "price": 200, "name": "🤵 Дворецкий", "desc": "Водитель выходит, картинно открывает дверь, кланяется в пояс и называет вас 'Сир' или 'Миледи'."},
    "joke": {"cat": 1, "price": 50, "name": "🤡 Тупой анекдот", "desc": "Анекдот категории 'Б' из коллекции таксиста 90-х. Смеяться обязательно!"},
    "silence": {"cat": 1, "price": 150, "name": "🤐 Полная тишина", "desc": "Режим 'Ниндзя'. Музыка выкл, водитель молчит как рыба. На вопросы отвечает жестами."},
    "granny": {"cat": 2, "price": 800, "name": "👵 Бабушка-ворчунья", "desc": "Всю дорогу водитель будет бубнить: 'Куда прешь, наркоман?', 'Шапку надень!', 'Вот в наше время...'."},
    "gopnik": {"cat": 2, "price": 500, "name": "🍺 Четкий пацанчик", "desc": "Пацанский рэп, водитель называет вас 'Братишка', лузгает семечки и решает вопросики по телефону."},
    "guide": {"cat": 2, "price": 600, "name": "🗣 Ужасный гид", "desc": "Водитель придумывает бред на ходу: 'Вот этот ларек построил лично Иван Грозный'."},
    "psych": {"cat": 2, "price": 1000, "name": "🧠 Психолог", "desc": "Вы жалуетесь на жизнь, водитель кивает, вздыхает и дает житейские советы уровня Ошо."},
    "spy": {"cat": 3, "price": 2000, "name": "🕵️‍♂️ Шпион 007", "desc": "Черные очки, паранойя. Проверяем хвост, говорим кодами: 'Орел в гнезде'."},
    "karaoke": {"cat": 3, "price": 5000, "name": "🎤 Адское Караоке", "desc": "Орем 'Рюмку водки' на полную! Водитель подпевает фальшиво, но очень громко."},
    "dance": {"cat": 3, "price": 15000, "name": "💃 Танцы на капоте", "desc": "На красном свете водитель выбегает и танцует макарену. Прохожие снимают, вам стыдно."},
    "kidnap": {"cat": 4, "price": 30000, "name": "🎭 Дружеское похищение", "desc": "Вас пакуют в багажник (понарошку), надевают мешок и везут в лес... пить чай с баранками."},
    "tarzan": {"cat": 4, "price": 50000, "name": "🦍 Тарзан-Шоу", "desc": "Водитель бьет себя в грудь, рычит на прохожих и называет машины 'железными буйволами'."},
    "burn": {"cat": 4, "price": 1000000, "name": "🔥 Сжечь машину", "desc": "Едем на пустырь, вы платите лям, я даю канистру. Гори оно всё огнем!"},
    "eyes": {"cat": 5, "price": 0, "name": "👁️ Глаз-алмаз", "desc": "Изысканный комплимент вашим глазам. Сравним их с ксеноном или звездами."},
    "smile": {"cat": 5, "price": 0, "name": "😁 Улыбка Джоконды", "desc": "Ваша улыбка освещает салон лучше, чем аварийка в ночи."},
    "style": {"cat": 5, "price": 0, "name": "👠 Икона стиля", "desc": "Восхищение образом. 'Вы с показа мод в Милане?'"},
    "improv": {"cat": 5, "price": 0, "name": "✨ Импровизация", "desc": "Водитель сам найдет, что в вас похвалить. Полный фристайл."},
    "propose": {"cat": 5, "price": 1000, "name": "💍 Сделать предложение", "desc": "Вы делаете предложение водителю. Шанс 50/50. ⚠️ ПРИ ОТКАЗЕ ДЕНЬГИ НЕ ВОЗВРАЩАЮТСЯ!"}
}

CATEGORIES = {1: "🟢 ЛАЙТ", 2: "🟡 МЕДИУМ", 3: "🔴 ХАРД", 4: "☠️ VIP БЕЗУМИЕ", 5: "🌹 ДЛЯ ДАМ"}

# ==========================================
# 🛠 СОСТОЯНИЯ (FSM)
# ==========================================
class OrderRide(StatesGroup):
    waiting_for_from = State(); waiting_for_to = State(); waiting_for_phone = State(); waiting_for_price = State()
class AddStop(StatesGroup):
    waiting_for_address = State(); waiting_for_price = State()
class DriverRegistration(StatesGroup):
    waiting_for_fio = State(); waiting_for_car = State(); waiting_for_payment_info = State(); waiting_for_code = State()
class DriverChangeCode(StatesGroup):
    waiting_for_new_code = State()
class UnlockMenu(StatesGroup):
    waiting_for_key = State()
class AdminActions(StatesGroup):
    waiting_for_new_value = State(); waiting_for_broadcast = State(); waiting_for_custom_bill = State()

# ==========================================
# ⌨️ КЛАВИАТУРЫ
# ==========================================
main_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🚕 Заказать такси (Поиск)")],
    [KeyboardButton(text="🔐 Ввести КЛЮЧ услуги")],
    [KeyboardButton(text="📜 CRAZY МЕНЮ (Категории)")],
    [KeyboardButton(text="💡 Свой вариант (Идея)")],
    [KeyboardButton(text="⚖️ Вызвать адвоката")]
], resize_keyboard=True)

tos_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ ПОДПИСАТЬ КРОВЬЮ", callback_data="accept_tos")],
    [InlineKeyboardButton(text="❌ Я боюсь", callback_data="decline_tos")]
])

# ==========================================
# 🛑 ОБРАБОТЧИКИ
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
            "⚠️ <b>CRAZY TAXI: ЗОНА ПОВЫШЕННОГО РИСКА</b>\n\nМы не возим скучных людей. Мы продаем эмоции.\n\n"
            "<b>📜 Правила:</b>\n1. Что в такси — остается в такси.\n2. Водитель — художник, салон — холст.\n3. Юристы бессильны.\n\nГотов рискнуть?",
            reply_markup=tos_kb
        )

@dp.callback_query(F.data == "accept_tos")
async def tos_accepted(callback: types.CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (callback.from_user.id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("🔥 <b>КОНТРАКТ ПОДПИСАН!</b>")
    await callback.message.answer("Добро пожаловать в семью. Выбирай судьбу 👇", reply_markup=main_kb)

@dp.message(F.text == "⚖️ Вызвать адвоката")
async def lawyer_menu(message: types.Message):
    await message.answer("⚖️ <b>ЮРИДИЧЕСКИЙ ЩИТ</b>\nСитуация вышла из-под контроля? Наш партнер защитит тебя:", 
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👨‍⚖️ К АДВОКАТУ", url=LAWYER_LINK)]]))

# --- ТАКСИ + ТОРГ ---
@dp.message(F.text == "🚕 Заказать такси (Поиск)")
async def taxi_start(message: types.Message, state: FSMContext):
    await state.clear(); await message.answer("📍 Откуда тебя забрать?", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(OrderRide.waiting_for_from)

@dp.message(OrderRide.waiting_for_from)
async def taxi_fr(m: types.Message, state: FSMContext):
    await state.update_data(fr=m.text); await m.answer("🏁 Куда летим?"); await state.set_state(OrderRide.waiting_for_to)

@dp.message(OrderRide.waiting_for_to)
async def taxi_to(m: types.Message, state: FSMContext):
    await state.update_data(to=m.text); await m.answer("📞 Твой номер:"); await state.set_state(OrderRide.waiting_for_phone)

@dp.message(OrderRide.waiting_for_phone)
async def taxi_ph(m: types.Message, state: FSMContext):
    await state.update_data(ph=m.text); await m.answer("💰 Твоя цена?"); await state.set_state(OrderRide.waiting_for_price)

@dp.message(OrderRide.waiting_for_price)
async def taxi_send(m: types.Message, state: FSMContext):
    data = await state.get_data(); cid = m.from_user.id
    active_orders[cid] = {"status": "pending", "price": m.text, "from": data['fr'], "to": data['to'], "phone": data['ph']}
    await m.answer("📡 Ищем подходящего безумца...", reply_markup=main_kb)
    txt = f"🚕 <b>ЗАКАЗ!</b>\n📍 {data['fr']} -> {data['to']}\n💰 {m.text}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ВЗЯТЬ", callback_data=f"t_acc_{cid}"), InlineKeyboardButton(text="💰 ТОРГ", callback_data=f"t_bid_{cid}")]])
    for adm in get_all_admins_ids(): await bot.send_message(adm, f"🚨 <b>МОНИТОРИНГ</b>\n{txt}", reply_markup=kb)
    for drv in get_active_drivers_ids(): 
        if drv not in SUPER_ADMINS: await bot.send_message(drv, txt, reply_markup=kb)
    await state.clear()

def get_active_drivers_ids():
    conn = sqlite3.connect(DB_PATH); res = [d[0] for d in conn.execute("SELECT user_id FROM drivers WHERE status='active'").fetchall()]; conn.close(); return res

@dp.callback_query(F.data.startswith("t_bid_"))
async def bid_start(c: types.CallbackQuery, state: FSMContext):
    await state.clear(); cid = c.data.split("_")[2]
    await state.update_data(target_cid=cid); await c.message.answer("Твоя цена за этот заказ:")
    await state.set_state(AdminActions.waiting_for_custom_bill) # Используем как поле для цены

@dp.callback_query(F.data.startswith("t_acc_"))
async def taxi_accept(c: types.CallbackQuery):
    cid = int(c.data.split("_")[2]); order = active_orders.get(cid)
    if not order or order["status"] != "pending": return await c.answer("Занято!")
    order["status"] = "accepted"; order["driver_id"] = c.from_user.id; client_driver_link[cid] = c.from_user.id
    info = get_driver_info(c.from_user.id)
    await c.message.edit_text(f"✅ Взято! Клиент: {order['phone']}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ", callback_data=f"ask_f_{cid}")]]))
    await bot.send_message(cid, f"🚕 <b>ВОДИТЕЛЬ В ПУТИ!</b>\n👤 {info[7]}\n🚘 {info[1]}\n🔐 Код: <code>{info[5]}</code>", 
                           reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ ОСТАНОВКА", callback_data="add_s")]]))

# --- КРЕЙЗИ МЕНЮ ---
@dp.message(F.text == "📜 CRAZY МЕНЮ (Категории)")
async def cats(m: types.Message):
    if m.from_user.id not in client_driver_link: return await m.answer("🔒 Сначала введи код водителя!")
    btns = [[InlineKeyboardButton(text=v, callback_data=f"cat_{k}")] for k,v in CATEGORIES.items()]
    await m.answer("🔥 <b>ВЫБЕРИ УРОВЕНЬ ЖЕСТКОСТИ:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("cat_"))
async def open_cat(c: types.CallbackQuery):
    cat_id = int(c.data.split("_")[1])
    btns = [[InlineKeyboardButton(text=f"{v['name']} - {v['price']}₽", callback_data=f"srv_{k}")] for k,v in CRAZY_SERVICES.items() if v['cat']==cat_id]
    btns.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_c")])
    await c.message.edit_text(f"📂 <b>{CATEGORIES[cat_id]}</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("srv_"))
async def show_srv(c: types.CallbackQuery):
    key = c.data.split("_")[1]; srv = CRAZY_SERVICES[key]
    txt = f"🎭 <b>{srv['name']}</b>\n💰 <b>{srv['price']}₽</b>\n\n<i>{srv['desc']}</i>"
    kb = [[InlineKeyboardButton(text="✅ ЗАКАЗАТЬ", callback_data=f"do_{key}")], [InlineKeyboardButton(text="🔙 Назад", callback_data=f"cat_{srv['cat']}")]]
    await c.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("do_"))
async def do_srv(c: types.CallbackQuery):
    key = c.data.split("_")[1]; srv = CRAZY_SERVICES[key]; cid = c.from_user.id; did = client_driver_link.get(cid)
    active_orders[cid] = {"type": "crazy", "price": str(srv["price"]), "driver_id": did, "service": srv}
    await bot.send_message(did, f"🔔 <b>ЗАКАЗ: {srv['name']}</b>\n💰 {srv['price']}₽", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"c_acc_{cid}")]]))
    await c.message.edit_text("⏳ Ждем пилота...")

@dp.callback_query(F.data.startswith("c_acc_"))
async def c_acc(c: types.CallbackQuery):
    cid = int(c.data.split("_")[2]); info = get_driver_info(c.from_user.id)
    await bot.send_message(cid, f"✅ Принято! Перевод: <code>{info[2]}</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ГОТОВО", callback_data=f"ask_f_{cid}")]]))
    await c.message.edit_text("✅ В работе.")

# --- ЗАВЕРШЕНИЕ И РЕЙТИНГ ---
@dp.callback_query(F.data.startswith("ask_f_"))
async def ask_f(c: types.CallbackQuery):
    cid = int(c.data.split("_")[2])
    kb = [[InlineKeyboardButton(text="⭐ 1", callback_data=f"r_{cid}_1"), InlineKeyboardButton(text="⭐ 3", callback_data=f"r_{cid}_3"), InlineKeyboardButton(text="⭐ 5", callback_data=f"r_{cid}_5")]]
    await bot.send_message(cid, "🏁 Финиш! Оцени пилота:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await c.message.edit_text("✅ Закрыто. Ждем оценку.")

@dp.callback_query(F.data.startswith("r_"))
async def set_r(c: types.CallbackQuery):
    p = c.data.split("_"); cid, rating = int(p[1]), int(p[2]); o = active_orders.get(cid)
    if not o: return
    pr = extract_price(o['price']); did = o['driver_id']
    last_id = log_order(did, o.get('service', {'name': 'Такси'})['name'], pr)
    update_order_rating(last_id, rating, did); add_commission(did, pr)
    await c.message.edit_text("🙏 Спасибо!"); await bot.send_message(did, f"🎉 Оценка: {rating}⭐"); del active_orders[cid]

# --- КАБИНЕТ ---
@dp.message(Command("cab"), F.chat.type == "private")
async def cab(m: types.Message, state: FSMContext):
    await state.clear(); info = get_driver_info(m.from_user.id)
    if not info: return await m.answer("❌ Нет регистрации. /drive")
    rating = round(info[8]/info[9], 1) if info[9]>0 else 0.0
    txt = (f"🪪 <b>КАБИНЕТ</b>\n👤 {info[7]}\n⭐ Рейтинг: {rating}\n💰 Долг: {info[3]}₽\n📊 Комиссия: {info[10]}%\n🔑 Код: <code>{info[5]}</code>")
    kb = [[InlineKeyboardButton(text="🔄 Сменить код", callback_data="c_code")], [InlineKeyboardButton(text="💸 Оплатить долг", callback_data="c_pay")]]
    await m.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "c_code")
async def c_code(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введи новый секретный код:"); await state.set_state(DriverChangeCode.waiting_for_new_code)

@dp.message(DriverChangeCode.waiting_for_new_code)
async def save_code(m: types.Message, state: FSMContext):
    try: update_driver_field(m.from_user.id, "access_code", m.text.upper().strip()); await m.answer("✅ Готово!")
    except: await m.answer("❌ Занят.")
    await state.clear()

# --- АДМИНКА ---
@dp.message(Command("admin"))
async def admin_p(m: types.Message, state: FSMContext):
    await state.clear()
    if not is_admin(m.from_user.id): return await m.answer("⛔")
    conn = sqlite3.connect(DB_PATH); drs = conn.execute("SELECT user_id, fio, balance FROM drivers").fetchall(); conn.close()
    txt = "👑 <b>АДМИНКА</b>\n"
    for d in drs: txt += f"• {d[1]} | {d[2]}₽ | /edit_{d[0]}\n"
    await m.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 РАССЫЛКА", callback_data="a_br")]]))

@dp.message(F.text.startswith("/edit_"))
async def ed_drv(m: types.Message):
    if not is_admin(m.from_user.id): return
    did = m.text.split("_")[1]; info = get_driver_info(did)
    kb = [[InlineKeyboardButton(text="💰 Баланс", callback_data=f"e_b_{did}"), InlineKeyboardButton(text="📊 %", callback_data=f"e_c_{did}")],
          [InlineKeyboardButton(text="💸 Счет", callback_data=f"e_bill_{did}"), InlineKeyboardButton(text="🔒 Блок", callback_data=f"e_l_{did}")]]
    await m.answer(f"Ред: {info[7]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("e_bill_"))
async def bill_ch(c: types.CallbackQuery, state: FSMContext):
    did = c.data.split("_")[2]; await state.update_data(did=did)
    kb = [[InlineKeyboardButton(text="💳 Реквизиты Босса", callback_data="b_def")], [InlineKeyboardButton(text="✏️ Свои", callback_data="b_cust")]]
    await c.message.edit_text("Как шлем счет?", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "b_cust")
async def b_cust(c: types.CallbackQuery, state: FSMContext):
    await c.message.edit_text("Введи текст счета:"); await state.set_state(AdminActions.waiting_for_custom_bill)

@dp.message(AdminActions.waiting_for_custom_bill)
async def b_send_cust(m: types.Message, state: FSMContext):
    d = await state.get_data(); await bot.send_message(d['did'], f"⚠️ <b>СЧЕТ:</b>\n{m.text}"); await m.answer("✅"); await state.clear()

@dp.callback_query(F.data == "b_def")
async def b_def(c: types.CallbackQuery, state: FSMContext):
    d = await state.get_data(); b = get_driver_info(OWNER_ID); i = get_driver_info(d['did'])
    await bot.send_message(d['did'], f"⚠️ <b>ОПЛАТА:</b> {i[3]}₽\n{b[2]}"); await c.message.edit_text("✅"); await state.clear()

# --- РЕГИСТРАЦИЯ ВОДИТЕЛЕЙ ---
@dp.message(Command("vip"))
async def vip(m: types.Message, state: FSMContext):
    await state.clear(); k = m.text.split()[1] if len(m.text.split())>1 else ""
    if k == VIP_DRIVER_KEY: await m.answer("🔑 VIP! Введи ФИО:"); await state.set_state(DriverRegistration.waiting_for_fio)
    else: await m.answer("❌")

@dp.message(Command("driver", "drive"))
async def reg(m: types.Message, state: FSMContext):
    await state.clear(); await m.answer("📝 Твое ФИО:"); await state.set_state(DriverRegistration.waiting_for_fio)

@dp.message(DriverRegistration.waiting_for_fio)
async def r1(m: types.Message, state: FSMContext): await state.update_data(fio=m.text); await m.answer("🚘 Авто:"); await state.set_state(DriverRegistration.waiting_for_car)
@dp.message(DriverRegistration.waiting_for_car)
async def r2(m: types.Message, state: FSMContext): await state.update_data(car=m.text); await m.answer("💳 Реквизиты:"); await state.set_state(DriverRegistration.waiting_for_payment_info)
@dp.message(DriverRegistration.waiting_for_payment_info)
async def r3(m: types.Message, state: FSMContext): await state.update_data(pay=m.text); await m.answer("🔑 Код-пароль:"); await state.set_state(DriverRegistration.waiting_for_code)
@dp.message(DriverRegistration.waiting_for_code)
async def r4(m: types.Message, state: FSMContext):
    d = await state.get_data(); code = m.text.upper().strip(); conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code) VALUES (?,?,?,?,?,?)", (m.from_user.id, m.from_user.username, d['fio'], d['car'], d['pay'], code))
        conn.commit(); await m.answer("✅ Жди одобрения.")
        await notify_admins(f"🚨 <b>НОВЫЙ:</b> {d['fio']}")
    except: await m.answer("❌ Код занят.")
    conn.close(); await state.clear()

# --- КЛЮЧ ---
@dp.message(F.text == "🔐 Ввести КЛЮЧ услуги")
async def k_st(m: types.Message, state: FSMContext): await state.clear(); await m.answer("Код пилота:"); await state.set_state(UnlockMenu.waiting_for_key)
@dp.message(UnlockMenu.waiting_for_key)
async def k_pr(m: types.Message, state: FSMContext):
    drv = get_driver_by_code(m.text.strip().upper())
    if drv: client_driver_link[m.from_user.id] = drv[0]; await m.answer(f"🔓 OK: {drv[3]}", reply_markup=main_kb); await state.clear()
    else: await m.answer("❌")

# --- ПРОЧЕЕ ---
@dp.message(F.text == "💡 Свой вариант (Идея)")
async def idea(m: types.Message, state: FSMContext):
    await state.clear(); await m.answer("Идея:"); await state.set_state(CustomIdea.waiting_for_idea)
@dp.message(CustomIdea.waiting_for_idea)
async def id1(m: types.Message, state: FSMContext): await state.update_data(id=m.text); await m.answer("Бюджет:"); await state.set_state(CustomIdea.waiting_for_price)
@dp.message(CustomIdea.waiting_for_price)
async def id2(m: types.Message, state: FSMContext):
    d = await state.get_data(); cid = m.from_user.id; active_orders[cid] = {"price": m.text, "service": {"name": "Идея", "desc": d['id']}}
    await m.answer("✅"); await broadcast_order_to_drivers(cid, f"💡 {d['id']}\n💰 {m.text}", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="ВЗЯТЬ", callback_data=f"t_acc_{cid}")]]), InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="ВЗЯТЬ", callback_data=f"t_acc_{cid}")]]))
    await state.clear()

@dp.callback_query(F.data == "a_br")
async def br_st(c: types.CallbackQuery, state: FSMContext): await c.message.answer("Текст рассылки:"); await state.set_state(AdminActions.waiting_for_broadcast)
@dp.message(AdminActions.waiting_for_broadcast)
async def br_snd(m: types.Message, state: FSMContext):
    drvs = get_active_drivers(); c = 0
    for d in drvs: 
        try: await bot.send_message(d, f"📢 <b>ОБЪЯВЛЕНИЕ:</b>\n{m.text}"); c += 1
        except: pass
    await m.answer(f"✅ {c}"); await state.clear()

@dp.callback_query(F.data.startswith("e_b_") | F.data.startswith("e_c_"))
async def ed_val(c: types.CallbackQuery, state: FSMContext):
    p = c.data.split("_"); field = "balance" if p[1]=="b" else "commission"
    await state.update_data(did=p[2], fld=field); await c.message.answer(f"Новое значение {field}:"); await state.set_state(AdminActions.waiting_for_new_value)

@dp.message(AdminActions.waiting_for_new_value)
async def ed_save(m: types.Message, state: FSMContext):
    d = await state.get_data(); update_driver_field(d['did'], d['fld'], m.text); await m.answer("✅"); await state.clear()

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
