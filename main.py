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

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
active_orders = {} 

# ==========================================
# 📜 СОСТОЯНИЯ (FSM)
# ==========================================
class DriverReg(StatesGroup): fio=State(); car=State(); pay=State(); ref=State(); code=State()
class Unlock(StatesGroup): key=State()
class AdminManage(StatesGroup): target_id=State(); action_data=State()
class CustomService(StatesGroup): name=State(); desc=State(); price=State()
class AdminBroadcast(StatesGroup): text=State()

# ==========================================
# 🗄️ ИНИЦИАЛИЗАЦИЯ БАЗЫ (С ПОЛНОЙ СТРУКТУРОЙ)
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS drivers (
        user_id INTEGER PRIMARY KEY, username TEXT, fio TEXT, car_info TEXT, payment_info TEXT, access_code TEXT UNIQUE, 
        vip_code TEXT UNIQUE, status TEXT DEFAULT 'pending', role TEXT DEFAULT 'driver', 
        balance INTEGER DEFAULT 0, rating_sum INTEGER DEFAULT 0, rating_count INTEGER DEFAULT 0, 
        commission INTEGER DEFAULT 10, referred_by INTEGER, promo_end_date TIMESTAMP)""")
    
    # Добавляем колонку username если её нет
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
# 📡 WEB SERVER (С ПОДДЕРЖКОЙ ЛИЧНЫХ УСЛУГ)
# ==========================================
async def get_services_json(request):
    uid = request.query.get('user_id')
    # Логика подгрузки общих + личных услуг для конкретного водителя
    # (Для реализации в index.html)
    return web.json_response({"status": "ok"})

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
# 🛠 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
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
    await message.answer("🐎 <b>ВЕСЁЛЫЙ ИЗВОЗЧИК</b>\nЖми кнопку заказа или заходи в кабинет!", reply_markup=kb)

# --- ЕДИНЫЙ КАБИНЕТ (С ПЕРЕКЛЮЧЕНИЕМ РОЛЕЙ) ---
@dp.message(F.text == "👤 Моя Светлица")
@dp.message(Command("cab"))
async def cabinet(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    drv = get_driver(uid)

    # 1. КАБИНЕТ АДМИНИСТРАТОРА (СТАРОСТЫ)
    if uid == OWNER_ID or (drv and drv[8] == 'owner'):
        kb = [
            [InlineKeyboardButton(text="📋 Список Ямщиков", callback_data="adm_list_drivers")],
            [InlineKeyboardButton(text="📢 Рассылка Артели", callback_data="adm_cast")],
            [InlineKeyboardButton(text="🎟 Промокоды", callback_data="adm_promos")]
        ]
        await message.answer("👑 <b>ПАНЕЛЬ СТАРОСТЫ</b>\nВы управляете всей артелью.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    # 2. КАБИНЕТ ВОДИТЕЛЯ (ЯМЩИКА)
    if drv and drv[7] == 'active':
        kb = [
            [InlineKeyboardButton(text="🎛 Мой Репертуар", callback_data="menu_edit")],
            [InlineKeyboardButton(text="➕ Добавить свою услугу", callback_data="add_custom")],
            [InlineKeyboardButton(text="🤝 Рефералка", callback_data="ref_prog")]
        ]
        status = "🟢 На линии"
        for cid, o in active_orders.items():
            if o.get('driver_id') == uid:
                status = f"🔥 В ДЕЛЕ (Клиент {cid})"
                kb.insert(0, [InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ", callback_data=f"fin_{cid}")])
                break
        
        await message.answer(f"🪪 <b>ЯМЩИК: {drv[2]}</b>\n💰 Долг Артели: {drv[9]}₽\n🔑 Код: <code>{drv[5]}</code>\nСтатус: {status}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    # 3. КАБИНЕТ КЛИЕНТА
    cli = get_client(uid)
    if cli:
        await message.answer(f"👤 <b>КАБИНЕТ БОЯРИНА</b>\n🎬 Поездок: {cli[3]}\n💰 Потрачено: {cli[2]}₽")
    else:
        await message.answer("Нажмите /start для регистрации.")

# --- ФУНКЦИИ ЯМЩИКА: СВОИ УСЛУГИ ---
@dp.callback_query(F.data == "add_custom")
async def start_custom(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Введите название вашей услуги:"); await state.set_state(CustomService.name)

@dp.message(CustomService.name)
async def cust_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text); await message.answer("Введите описание:"); await state.set_state(CustomService.desc)

@dp.message(CustomService.desc)
async def cust_desc(message: types.Message, state: FSMContext):
    await state.update_data(desc=message.text); await message.answer("Введите цену (числом):"); await state.set_state(CustomService.price)

@dp.message(CustomService.price)
async def cust_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Нужно число!")
    data = await state.get_data()
    with sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT INTO custom_services (driver_id, name, description, price) VALUES (?, ?, ?, ?)", 
                    (message.from_user.id, data['name'], data['desc'], int(message.text)))
    await message.answer("✅ Услуга добавлена в ваш личный репертуар!"); await state.clear()

# --- ФУНКЦИИ АДМИНА: УПРАВЛЕНИЕ ВОДИТЕЛЯМИ ---
@dp.callback_query(F.data == "adm_list_drivers")
async def list_drivers(call: types.CallbackQuery):
    with sqlite3.connect(DB_PATH) as con:
        drivers = con.execute("SELECT user_id, fio, balance, status FROM drivers WHERE role != 'owner'").fetchall()
    
    if not drivers: return await call.message.answer("Ямщиков пока нет.")
    
    for d in drivers:
        kb = [[InlineKeyboardButton(text="✉️ Написать", callback_data=f"adm_msg_{d[0]}"),
               InlineKeyboardButton(text="💰 Счёт", callback_data=f"adm_bill_{d[0]}")],
              [InlineKeyboardButton(text="🚫 Блок", callback_data=f"adm_block_{d[0]}"),
               InlineKeyboardButton(text="✅ Разблок", callback_data=f"adm_unblock_{d[0]}")]]
        await call.message.answer(f"👤 {d[1]}\nID: <code>{d[0]}</code>\nДолг: {d[2]}₽\nСтатус: {d[3]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("adm_block_"))
async def block_driver(call: types.CallbackQuery):
    did = call.data.split("_")[2]
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE drivers SET status='blocked' WHERE user_id=?", (did,))
    await call.answer("Заблокирован"); await safe_send(did, "⛔ Ваша лицензия ямщика отозвана Старостой.")

@dp.callback_query(F.data.startswith("adm_bill_"))
async def bill_driver(call: types.CallbackQuery):
    did = call.data.split("_")[2]
    drv = get_driver(did)
    await safe_send(did, f"⚠️ <b>ВНИМАНИЕ!</b>\nСтароста требует оплатить долг Артели: <b>{drv[9]}₽</b>\nРеквизиты: {OWNER_ID}")
    await call.answer("Счёт выслан")

# --- ПРОЧИЙ ФУНКЦИОНАЛ (РЕГИСТРАЦИЯ, ЗАКАЗЫ) ---
@dp.message(Command("drive"))
async def reg_start(message: types.Message, state: FSMContext):
    if get_driver(message.from_user.id): return await message.answer("Вы уже в Артели!")
    await message.answer("Как вас величать? (ФИО)"); await state.set_state(DriverReg.fio)

@dp.message(DriverReg.fio)
async def reg_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text); await message.answer("На чем скачете?"); await state.set_state(DriverReg.car)

@dp.message(DriverReg.car)
async def reg_car(message: types.Message, state: FSMContext):
    await state.update_data(car=message.text); await message.answer("Реквизиты для оплаты?"); await state.set_state(DriverReg.pay)

@dp.message(DriverReg.pay)
async def reg_pay(message: types.Message, state: FSMContext):
    await state.update_data(pay=message.text); await message.answer("Придумайте свой секретный код (латиница):"); await state.set_state(DriverReg.code)

@dp.message(DriverReg.code)
async def reg_fin(message: types.Message, state: FSMContext):
    d = await state.get_data(); code = message.text.upper().strip()
    try:
        with sqlite3.connect(DB_PATH) as con:
            con.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status) VALUES (?,?,?,?,?,?, 'active')",
                        (message.from_user.id, message.from_user.username, d['fio'], d['car'], d['pay'], code))
        await message.answer(f"✅ <b>Добро пожаловать в Артель!</b>\nТвой код: <code>{code}</code>")
    except: await message.answer("❌ Ошибка (возможно код занят)")
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
