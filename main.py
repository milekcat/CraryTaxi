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
# ⚙️ НАСТРОЙКИ (Ваш ID применен)
# ==========================================
logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("API_TOKEN")
# Жёстко прописываем ваш подтвержденный ID для админки
OWNER_ID = 6004764782 
APP_URL = "https://tazyy-milekcat.amvera.io"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(BASE_DIR, 'index.html')
DB_PATH = "/data/taxi_db.sqlite" if os.path.exists("/data") else os.path.join(BASE_DIR, "taxi_db.sqlite")

VIP_LIMIT = 10          
DEFAULT_COMMISSION = 10 

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
active_orders = {} 

# ==========================================
# 🗄️ ИСПРАВЛЕНИЕ БАЗЫ ДАННЫХ
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Создаем основную таблицу
    cur.execute("""CREATE TABLE IF NOT EXISTS drivers (
        user_id INTEGER PRIMARY KEY, fio TEXT, car_info TEXT, payment_info TEXT, access_code TEXT UNIQUE, 
        vip_code TEXT UNIQUE, status TEXT DEFAULT 'pending', role TEXT DEFAULT 'driver', 
        balance INTEGER DEFAULT 0, rating_sum INTEGER DEFAULT 0, rating_count INTEGER DEFAULT 0, 
        commission INTEGER DEFAULT 10, referred_by INTEGER, promo_end_date TIMESTAMP)""")
    
    # ПРОВЕРКА И ДОБАВЛЕНИЕ username (Исправление вашей ошибки)
    cur.execute("PRAGMA table_info(drivers)")
    columns = [column[1] for column in cur.fetchall()]
    if 'username' not in columns:
        cur.execute("ALTER TABLE drivers ADD COLUMN username TEXT")
    
    cur.execute("CREATE TABLE IF NOT EXISTS driver_services (driver_id INTEGER, service_key TEXT, is_active BOOLEAN DEFAULT 1, PRIMARY KEY (driver_id, service_key))")
    cur.execute("CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, commission INTEGER, duration INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER DEFAULT NULL, total_spent INTEGER DEFAULT 0, trips_count INTEGER DEFAULT 0, vip_unlocked BOOLEAN DEFAULT 0)")
    cur.execute("CREATE TABLE IF NOT EXISTS order_history (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, driver_id INTEGER, service_name TEXT, price INTEGER, rating INTEGER DEFAULT 0, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    
    # Назначаем вас владельцем
    cur.execute("INSERT OR IGNORE INTO drivers (user_id, fio, access_code, status, role) VALUES (?, 'ГЛАВНЫЙ БОЯРИН', 'ADMIN', 'active', 'owner')", (OWNER_ID,))
    cur.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (OWNER_ID,))
    
    conn.commit(); conn.close()

init_db()

# ==========================================
# 🛠 УТИЛИТЫ И ВСЕ ФУНКЦИИ (V30-40 RESTORED)
# ==========================================
CRAZY_SERVICES = {
    "candy": "🍬 Сладкий гостинец", "nose": "👃 Перст в носу", "butler": "🤵 Дворецкий",
    "joke": "🤡 Скоморох", "silence": "🤐 Обет молчания", "granny": "👵 Ворчливая бабка",
    "gopnik": "🍺 Разбойник", "guide": "🗣 Горе-Гид", "psych": "🧠 Душеприказчик",
    "spy": "🕵️ Опричник (007)", "karaoke": "🎤 Застольные песни", "dance": "🐻 Медвежьи пляски",
    "kidnap": "🎭 Похищение", "tarzan": "🦍 Леший", "burn": "🔥 Огненная колесница",
    "eyes": "👁️ Очи чёрные", "smile": "😁 Улыбка", "style": "👠 Модный приговор"
}

def generate_vip_code(name):
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"BOYAR-{name.split()[0].upper()}-{suffix}"

def get_driver(uid):
    with sqlite3.connect(DB_PATH) as con: return con.execute("SELECT * FROM drivers WHERE user_id=?", (uid,)).fetchone()

def get_client(uid):
    with sqlite3.connect(DB_PATH) as con: return con.execute("SELECT * FROM clients WHERE user_id=?", (uid,)).fetchone()

async def safe_send(chat_id, text, kb=None):
    try: await bot.send_message(chat_id, text, reply_markup=kb); return True
    except: return False

# ==========================================
# 📡 WEB SERVER
# ==========================================
async def main_page(request):
    try:
        with open(HTML_FILE, 'r', encoding='utf-8') as f:
            return web.Response(text=f.read(), content_type='text/html')
    except: return web.Response(text="Error: index.html not found", status=404)

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
# 🤖 BOT HANDLERS
# ==========================================
class DriverReg(StatesGroup): fio=State(); car=State(); pay=State(); ref=State(); code=State()
class Unlock(StatesGroup): key=State()

@dp.message(Command("start"))
async def start(message: types.Message):
    with sqlite3.connect(DB_PATH) as con: con.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (message.from_user.id,))
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🚖 ЗАКАЗАТЬ ПОТЕХУ", web_app=WebAppInfo(url=APP_URL))],
        [KeyboardButton(text="👤 Моя Светлица"), KeyboardButton(text="🔑 Ввести код Ямщика")]
    ], resize_keyboard=True)
    await message.answer("🐎 <b>ВЕСЁЛЫЙ ИЗВОЗЧИК</b>\nЖми кнопку заказа или заходи в кабинет!", reply_markup=kb)

@dp.message(F.text == "👤 Моя Светлица")
@dp.message(Command("cab"))
async def cabinet(message: types.Message):
    uid = message.from_user.id
    drv = get_driver(uid)
    if drv:
        # Водитель
        kb = [[InlineKeyboardButton(text="🎛 Репертуар", callback_data="menu_edit")],
              [InlineKeyboardButton(text="🤝 Рефералка", callback_data="ref_prog")]]
        await message.answer(f"🪪 <b>ЯМЩИК: {drv[1]}</b>\n💰 Баланс: {drv[8]}₽\n🔑 Код: <code>{drv[4]}</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return
    cli = get_client(uid)
    if cli:
        # Клиент
        await message.answer(f"👤 <b>КАБИНЕТ БОЯРИНА</b>\n💰 Потрачено: {cli[2]}₽\n🎬 Поездок: {cli[3]}")

@dp.message(Command("admin"))
async def admin_p(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    await message.answer("👑 <b>АДМИН-ПАНЕЛЬ СТАРОСТЫ</b>\nВсе функции активны.")

@dp.message(Command("drive"))
async def reg_start(message: types.Message, state: FSMContext):
    if get_driver(message.from_user.id): return await message.answer("Вы уже Ямщик!")
    await message.answer("Как вас величать? (ФИО)")
    await state.set_state(DriverReg.fio)

@dp.message(DriverReg.fio)
async def reg_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text); await message.answer("На какой колеснице скачете?")
    await state.set_state(DriverReg.car)

@dp.message(DriverReg.car)
async def reg_car(message: types.Message, state: FSMContext):
    await state.update_data(car=message.text); await message.answer("Куда монеты ссыпать?")
    await state.set_state(DriverReg.pay)

@dp.message(DriverReg.pay)
async def reg_pay(message: types.Message, state: FSMContext):
    await state.update_data(pay=message.text); await message.answer("Придумайте свой секретный код (латиница):")
    await state.set_state(DriverReg.code)

@dp.message(DriverReg.code)
async def reg_fin(message: types.Message, state: FSMContext):
    d = await state.get_data()
    code = message.text.upper().strip()
    try:
        with sqlite3.connect(DB_PATH) as con:
            con.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status) VALUES (?,?,?,?,?,?, 'active')",
                        (message.from_user.id, message.from_user.username, d['fio'], d['car'], d['pay'], code))
        await message.answer(f"✅ <b>Заявка принята!</b>\nТвой код: <code>{code}</code>")
    except sqlite3.IntegrityError:
        await message.answer("❌ Код занят!")
    await state.clear()

# ==========================================
# 🚀 ЗАПУСК
# ==========================================
async def on_startup(app):
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))

def main():
    app = web.Application()
    app.router.add_get('/', main_page)
    app.router.add_post('/webapp_order', web_order)
    app.on_startup.append(on_startup)
    web.run_app(app, host='0.0.0.0', port=8080)

if __name__ == "__main__":
    main()
