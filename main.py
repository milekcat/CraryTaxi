import asyncio
import logging
import os
import sqlite3
import random
import string
import json
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.client.default import DefaultBotProperties

# ==========================================
# ⚙️ НАСТРОЙКИ
# ==========================================
logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("API_TOKEN")
OWNER_ID = 6004764782  # Ваш подтвержденный ID
APP_URL = "https://tazyy-milekcat.amvera.io"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(BASE_DIR, 'index.html')
DB_PATH = "/data/taxi_db.sqlite" if os.path.exists("/data") else os.path.join(BASE_DIR, "taxi_db.sqlite")

VIP_LIMIT = 10          
DEFAULT_COMMISSION = 10 
LAWYER_LINK = "https://t.me/Ai_advokatrobot"

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
active_orders = {} 

# ==========================================
# 📜 ПОЛНЫЙ ПЕРЕЧЕНЬ СТАНДАРТНЫХ УСЛУГ
# ==========================================
CRAZY_SERVICES = {
    "candy": {"cat": 1, "name": "🍬 Сладкий гостинец", "desc": "Ямщик с поклоном вручает леденец."},
    "nose": {"cat": 1, "name": "👃 Перст в носу", "desc": "Ямщик всю дорогу в носу ковыряет."},
    "butler": {"cat": 1, "name": "🤵 Дворецкий", "desc": "Открываем дверь, кланяемся, величаем Барином."},
    "joke": {"cat": 1, "name": "🤡 Скоморох", "desc": "Шутка юмора. Смеяться обязательно."},
    "silence": {"cat": 1, "name": "🤐 Обет молчания", "desc": "Едем молча, как в монастыре."},
    "granny": {"cat": 2, "name": "👵 Ворчливая бабка", "desc": "Ролевая игра: Куда прешь, окаянный!"},
    "gopnik": {"cat": 2, "name": "🍺 Разбойник", "desc": "Шансон, семки, решение вопросиков."},
    "guide": {"cat": 2, "name": "🗣 Горе-Гид", "desc": "Небылицы о каждом столбе."},
    "psych": {"cat": 2, "name": "🧠 Душеприказчик", "desc": "Слушаем кручину, даем советы."},
    "spy": {"cat": 3, "name": "🕵️ Опричник (007)", "desc": "Тайная слежка и уход от погони."},
    "karaoke": {"cat": 3, "name": "🎤 Застольные песни", "desc": "Орем песни дуэтом на всю улицу."},
    "dance": {"cat": 3, "name": "🐻 Медвежьи пляски", "desc": "Танцы на капоте на светофоре."},
    "kidnap": {"cat": 4, "name": "🎭 Похищение", "desc": "В мешок и в лес (понарошку)."},
    "tarzan": {"cat": 4, "name": "🦍 Леший", "desc": "Рычим на прохожих, пугаем девок."},
    "burn": {"cat": 4, "name": "🔥 Огненная колесница", "desc": "Сжигаем повозку на пустыре."},
    "eyes": {"cat": 5, "name": "👁️ Очи чёрные", "desc": "Комплимент вашим глазам."},
    "smile": {"cat": 5, "name": "😁 Улыбка", "desc": "Комплимент вашей улыбке."},
    "style": {"cat": 5, "name": "👠 Модный приговор", "desc": "Восхищение нарядом."},
    "improv": {"cat": 5, "name": "✨ Импровизация", "desc": "Ямщик сам придумает потеху."},
    "propose": {"cat": 5, "name": "💍 Сватовство", "desc": "Предложение руки и сердца."}
}

WELCOME_TEXT = (
    "🐎 <b>Здравия желаю, Барин!</b>\n\n"
    "Добро пожаловать в артель <b>«Весёлый Извозчик»</b>!\n"
    "У нас не просто телега с мотором, у нас — душа нараспашку.\n\n"
    "📜 <b>В программе:</b>\n"
    "• Ямщик-Психолог (выслушает кручину)\n"
    "• Пляски на тракте\n"
    "• Огненная потеха (сжигание повозки)\n\n"
    "⚖️ <i>Защита от опричников — <a href='https://t.me/Ai_advokatrobot'>Казённый Стряпчий</a>.</i>\n\n"
    "<b>Куда путь держим?</b> 👇"
)

# ==========================================
# 🗄️ ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS drivers (
        user_id INTEGER PRIMARY KEY, username TEXT, fio TEXT, car_info TEXT, payment_info TEXT, access_code TEXT UNIQUE, 
        vip_code TEXT UNIQUE, status TEXT DEFAULT 'pending', role TEXT DEFAULT 'driver', 
        balance INTEGER DEFAULT 0, rating_sum INTEGER DEFAULT 0, rating_count INTEGER DEFAULT 0, 
        commission INTEGER DEFAULT 10, referred_by INTEGER, promo_end_date TIMESTAMP)""")
    
    cur.execute("PRAGMA table_info(drivers)")
    columns = [column[1] for column in cur.fetchall()]
    if 'username' not in columns:
        cur.execute("ALTER TABLE drivers ADD COLUMN username TEXT")
    
    cur.execute("CREATE TABLE IF NOT EXISTS driver_services (driver_id INTEGER, service_key TEXT, is_active BOOLEAN DEFAULT 1, PRIMARY KEY (driver_id, service_key))")
    cur.execute("CREATE TABLE IF NOT EXISTS custom_services (id INTEGER PRIMARY KEY AUTOINCREMENT, driver_id INTEGER, name TEXT, description TEXT, price INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, commission INTEGER, duration INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER DEFAULT NULL, total_spent INTEGER DEFAULT 0, trips_count INTEGER DEFAULT 0, vip_unlocked BOOLEAN DEFAULT 0)")
    cur.execute("CREATE TABLE IF NOT EXISTS order_history (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, driver_id INTEGER, service_name TEXT, price INTEGER, rating INTEGER DEFAULT 0, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    
    cur.execute("INSERT OR IGNORE INTO drivers (user_id, fio, access_code, status, role) VALUES (?, 'ГЛАВНЫЙ БОЯРИН', 'ADMIN', 'active', 'owner')", (OWNER_ID,))
    cur.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (OWNER_ID,))
    conn.commit(); conn.close()

init_db()

# ==========================================
# 🤖 СОСТОЯНИЯ (FSM)
# ==========================================
class DriverReg(StatesGroup): fio=State(); car=State(); pay=State(); ref=State(); code=State()
class Unlock(StatesGroup): key=State()
class AdminManage(StatesGroup): target_id=State(); action_data=State()
class CustomServiceAdd(StatesGroup): name=State(); desc=State(); price=State()
class AdminBroadcast(StatesGroup): text=State()

# ==========================================
# 📡 WEB SERVER
# ==========================================
async def web_order(request):
    try:
        data = await request.json()
        uid, srv, price = data.get('user_id'), data.get('service'), data.get('price')
        cli = get_client(uid)
        did = cli[1] if cli else None
        if not did: return web.json_response({"status": "no_driver"})
        active_orders[uid] = {"driver_id": did, "price": price, "service": srv}
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"ok_{uid}")]])
        await bot.send_message(did, f"🔔 <b>НОВЫЙ ЗАКАЗ:</b>\n🎭 {srv}\n💰 {price}₽", reply_markup=kb)
        return web.json_response({"status": "ok"})
    except: return web.json_response({"status": "error"})

# ==========================================
# 🛠 УТИЛИТЫ
# ==========================================
def get_driver(uid):
    with sqlite3.connect(DB_PATH) as con: return con.execute("SELECT * FROM drivers WHERE user_id=?", (uid,)).fetchone()

def get_client(uid):
    with sqlite3.connect(DB_PATH) as con: return con.execute("SELECT * FROM clients WHERE user_id=?", (uid,)).fetchone()

async def safe_send(chat_id, text, kb=None):
    try: await bot.send_message(chat_id, text, reply_markup=kb); return True
    except: return False

# ==========================================
# 🤖 BOT HANDLERS
# ==========================================

@dp.message(Command("start"))
async def start(message: types.Message):
    with sqlite3.connect(DB_PATH) as con: con.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (message.from_user.id,))
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🚖 ЗАКАЗАТЬ ПОТЕХУ", web_app=WebAppInfo(url=APP_URL))],
        [KeyboardButton(text="👤 Моя Светлица"), KeyboardButton(text="🔑 Ввести код Ямщика")]
    ], resize_keyboard=True)
    await message.answer(WELCOME_TEXT, reply_markup=kb)

# --- УНИВЕРСАЛЬНЫЙ КАБИНЕТ ---
@dp.message(F.text == "👤 Моя Светлица")
@dp.message(Command("cab"))
async def cabinet(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    drv = get_driver(uid)

    # 1. АДМИН
    if uid == OWNER_ID:
        kb = [
            [InlineKeyboardButton(text="📋 Список Ямщиков", callback_data="adm_list")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_cast")],
            [InlineKeyboardButton(text="🎟 Промокоды", callback_data="adm_promo")]
        ]
        await message.answer("👑 <b>ПАНЕЛЬ СТАРОСТЫ</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    # 2. ВОДИТЕЛЬ
    if drv and drv[7] == 'active':
        kb = [
            [InlineKeyboardButton(text="🎛 Мой Репертуар", callback_data="menu_edit")],
            [InlineKeyboardButton(text="➕ Своя услуга", callback_data="add_custom")],
            [InlineKeyboardButton(text="🤝 Рефералка", callback_data="ref_prog")]
        ]
        # Проверка активного заказа
        status = "🟢 На линии"
        for cid, o in active_orders.items():
            if o.get('driver_id') == uid:
                status = f"🔥 В ДЕЛЕ (Клиент {cid})"
                kb.insert(0, [InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ", callback_data=f"fin_{cid}")])
                break
        
        await message.answer(f"🪪 <b>ЯМЩИК: {drv[2]}</b>\n💰 Баланс: {drv[9]}₽\n🔑 Код: <code>{drv[5]}</code>\n{status}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    # 3. КЛИЕНТ
    cli = get_client(uid)
    if cli:
        await message.answer(f"👤 <b>КАБИНЕТ БОЯРИНА</b>\n🎬 Поездок: {cli[3]}\n💰 Потрачено: {cli[2]}₽")
    else:
        await message.answer("Нажмите /start")

# --- ЛОГИКА СВОИХ УСЛУГ ---
@dp.callback_query(F.data == "add_custom")
async def add_custom_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Введите название потехи:"); await state.set_state(CustomServiceAdd.name)

@dp.message(CustomServiceAdd.name)
async def add_custom_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text); await message.answer("Описание потехи:"); await state.set_state(CustomServiceAdd.desc)

@dp.message(CustomServiceAdd.desc)
async def add_custom_desc(message: types.Message, state: FSMContext):
    await state.update_data(desc=message.text); await message.answer("Цена (золотых):"); await state.set_state(CustomServiceAdd.price)

@dp.message(CustomServiceAdd.price)
async def add_custom_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Только цифры!")
    data = await state.get_data()
    with sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT INTO custom_services (driver_id, name, description, price) VALUES (?, ?, ?, ?)", 
                    (message.from_user.id, data['name'], data['desc'], int(message.text)))
    await message.answer("✅ Услуга добавлена в ваш личный список!"); await state.clear()

# --- УПРАВЛЕНИЕ ЯМЩИКАМИ (АДМИН) ---
@dp.callback_query(F.data == "adm_list")
async def adm_list(call: types.CallbackQuery):
    with sqlite3.connect(DB_PATH) as con:
        drivers = con.execute("SELECT user_id, fio, balance, status FROM drivers WHERE role != 'owner'").fetchall()
    for d in drivers:
        kb = [[InlineKeyboardButton(text="🚫 Блок", callback_data=f"adm_block_{d[0]}"), InlineKeyboardButton(text="💰 Счёт", callback_data=f"adm_bill_{d[0]}")] ]
        await call.message.answer(f"👤 {d[1]}\nДолг: {d[2]}₽\nСтатус: {d[3]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("adm_block_"))
async def adm_block(call: types.CallbackQuery):
    did = call.data.split("_")[2]
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE drivers SET status='blocked' WHERE user_id=?", (did,))
    await call.answer("Заблокирован"); await safe_send(did, "⛔ Ваша лицензия отозвана.")

# --- РЕГИСТРАЦИЯ И КОДЫ ---
@dp.message(F.text == "🔑 Ввести код Ямщика")
async def ask_key(message: types.Message, state: FSMContext):
    await message.answer("Введи код:"); await state.set_state(Unlock.key)

@dp.message(Unlock.key)
async def check_key(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    with sqlite3.connect(DB_PATH) as con:
        drv = con.execute("SELECT user_id, fio FROM drivers WHERE access_code=? AND status='active'", (code,)).fetchone()
    if drv:
        with sqlite3.connect(DB_PATH) as con:
            con.execute("UPDATE clients SET linked_driver_id=? WHERE user_id=?", (drv[0], message.from_user.id))
        await message.answer(f"✅ Привязан к: {drv[1]}")
    else: await message.answer("❌ Нет такого кода.")
    await state.clear()

# ==========================================
# 🚀 ЗАПУСК
# ==========================================
async def on_startup(app):
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))

def main():
    app = web.Application()
    app.router.add_get('/', lambda r: web.FileResponse(HTML_FILE))
    app.router.add_post('/webapp_order', web_order)
    app.on_startup.append(on_startup)
    web.run_app(app, host='0.0.0.0', port=8080)

if __name__ == "__main__":
    main()
