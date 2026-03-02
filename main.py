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

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
active_orders = {} 

# ==========================================
# 📜 ПОЛНЫЙ ПЕРЕЧЕНЬ УСЛУГ
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
    "📜 <b>В программе:</b>\n"
    "• Ямщик-Психолог\n• Пляски на тракте\n• Огненная потеха\n\n"
    "<b>Куда путь держим?</b> 👇"
)

# ==========================================
# 🗄️ ИНИЦИАЛИЗАЦИЯ БАЗЫ
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
    if 'username' not in [c[1] for c in cur.fetchall()]:
        cur.execute("ALTER TABLE drivers ADD COLUMN username TEXT")
    
    cur.execute("CREATE TABLE IF NOT EXISTS driver_services (driver_id INTEGER, service_key TEXT, is_active BOOLEAN DEFAULT 1, PRIMARY KEY (driver_id, service_key))")
    cur.execute("CREATE TABLE IF NOT EXISTS custom_services (id INTEGER PRIMARY KEY AUTOINCREMENT, driver_id INTEGER, name TEXT, description TEXT, price INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER DEFAULT NULL, total_spent INTEGER DEFAULT 0, trips_count INTEGER DEFAULT 0)")
    
    cur.execute("INSERT OR IGNORE INTO drivers (user_id, fio, access_code, status, role) VALUES (?, 'ГЛАВНЫЙ БОЯРИН', 'ADMIN', 'active', 'owner')", (OWNER_ID,))
    cur.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (OWNER_ID,))
    conn.commit(); conn.close()

init_db()

# ==========================================
# 🤖 СОСТОЯНИЯ (FSM)
# ==========================================
class DriverReg(StatesGroup): fio=State(); car=State(); pay=State(); code=State()
class Unlock(StatesGroup): key=State()
class AdminDirectMsg(StatesGroup): text=State()
class CustomServiceAdd(StatesGroup): name=State(); desc=State(); price=State()

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

@dp.message(F.text == "👤 Моя Светлица")
@dp.message(Command("cab"))
async def cabinet(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    drv = get_driver(uid)

    if uid == OWNER_ID:
        kb = [[InlineKeyboardButton(text="📋 Список Ямщиков", callback_data="adm_list")],
              [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_cast")]]
        await message.answer("👑 <b>КАБИНЕТ СТАРОСТЫ</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    if drv and drv[7] == 'active':
        kb = [[InlineKeyboardButton(text="🎛 Репертуар", callback_data="menu_edit")],
              [InlineKeyboardButton(text="➕ Своя услуга", callback_data="add_custom")]]
        await message.answer(f"🪪 <b>ЯМЩИК: {drv[2]}</b>\n💰 Баланс: {drv[9]}₽\n🔑 Код: {drv[5]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    cli = get_client(uid)
    await message.answer(f"👤 <b>КАБИНЕТ КЛИЕНТА</b>\n🎬 Поездок: {cli[3] if cli else 0}")

# --- УПРАВЛЕНИЕ АДМИНОМ ---
@dp.callback_query(F.data == "adm_list")
async def adm_list(call: types.CallbackQuery):
    with sqlite3.connect(DB_PATH) as con:
        drivers = con.execute("SELECT user_id, fio, balance, status FROM drivers WHERE role != 'owner'").fetchall()
    if not drivers: return await call.message.answer("Ямщиков нет.")
    for d in drivers:
        kb = [[InlineKeyboardButton(text="✉️ Написать", callback_data=f"msg_{d[0]}"),
               InlineKeyboardButton(text="🚫 Блок", callback_data=f"blk_{d[0]}"),
               InlineKeyboardButton(text="✅ Разблок", callback_data=f"unl_{d[0]}")]]
        await call.message.answer(f"👤 {d[1]}\nID: {d[0]}\nДолг: {d[2]}₽\nСтатус: {d[3]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("unl_"))
async def adm_unblock(call: types.CallbackQuery):
    did = call.data.split("_")[1]
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE drivers SET status='active' WHERE user_id=?", (did,))
    await call.answer("Разблокирован!"); await safe_send(did, "🎉 Лицензия возвращена!")

@dp.callback_query(F.data.startswith("blk_"))
async def adm_block(call: types.CallbackQuery):
    did = call.data.split("_")[1]
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE drivers SET status='blocked' WHERE user_id=?", (did,))
    await call.answer("Заблокирован"); await safe_send(did, "⛔ Вы заблокированы.")

@dp.callback_query(F.data.startswith("msg_"))
async def adm_msg_start(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(target_did=call.data.split("_")[1])
    await call.message.answer("Введите текст послания:"); await state.set_state(AdminDirectMsg.text)

@dp.message(AdminDirectMsg.text)
async def adm_msg_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await safe_send(data['target_did'], f"✉️ <b>ОТ СТАРОСТЫ:</b>\n\n{message.text}")
    await message.answer("✅ Отправлено."); await state.clear()

# --- СВОИ УСЛУГИ ---
@dp.callback_query(F.data == "add_custom")
async def add_custom_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Название потехи:"); await state.set_state(CustomServiceAdd.name)

@dp.message(CustomServiceAdd.name)
async def add_custom_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text); await message.answer("Описание:"); await state.set_state(CustomServiceAdd.desc)

@dp.message(CustomServiceAdd.desc)
async def add_custom_desc(message: types.Message, state: FSMContext):
    await state.update_data(desc=message.text); await message.answer("Цена:"); await state.set_state(CustomServiceAdd.price)

@dp.message(CustomServiceAdd.price)
async def add_custom_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Цифрами.")
    data = await state.get_data()
    with sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT INTO custom_services (driver_id, name, description, price) VALUES (?, ?, ?, ?)", 
                    (message.from_user.id, data['name'], data['desc'], int(message.text)))
    await message.answer("✅ Добавлено!"); await state.clear()

# ==========================================
# 🚀 ЗАПУСК (ИСПРАВЛЕНО)
# ==========================================
async def on_startup(app):
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))

def main():
    app = web.Application()
    app.router.add_get('/', lambda r: web.FileResponse(HTML_FILE))
    app.router.add_post('/webapp_order', web_order)
    app.on_startup.append(on_startup)
    # Используем фиксированные значения во избежание NameError
    web.run_app(app, host='0.0.0.0', port=8080)

if __name__ == "__main__":
    main()
