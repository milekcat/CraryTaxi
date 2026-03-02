import asyncio
import logging
import os
import sqlite3
import json
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
OWNER_ID = 6004764782 
APP_URL = "https://tazyy-milekcat.amvera.io"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(BASE_DIR, 'index.html')
DB_PATH = "/data/taxi_db.sqlite" if os.path.exists("/data") else os.path.join(BASE_DIR, "taxi_db.sqlite")

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
active_orders = {} 

# --- ПОЛНЫЙ ПЕРЕЧЕНЬ УСЛУГ (20 ШТ) ---
CRAZY_SERVICES = {
    "candy": {"cat": "Малые", "name": "🍬 Сладкий гостинец", "desc": "Ямщик с поклоном вручает леденец.", "price": 100},
    "nose": {"cat": "Малые", "name": "👃 Перст в носу", "desc": "Ямщик всю дорогу в носу ковыряет.", "price": 150},
    "butler": {"cat": "Малые", "name": "🤵 Дворецкий", "desc": "Открываем дверь, величаем Барином.", "price": 300},
    "joke": {"cat": "Малые", "name": "🤡 Скоморох", "desc": "Шутка юмора. Смеяться обязательно.", "price": 200},
    "silence": {"cat": "Малые", "name": "🤐 Обет молчания", "desc": "Едем молча, как в монастыре.", "price": 500},
    "granny": {"cat": "Средние", "name": "👵 Ворчливая бабка", "desc": "Ролевая игра: Куда прешь, окаянный!", "price": 400},
    "gopnik": {"cat": "Средние", "name": "🍺 Разбойник", "desc": "Шансон, семки, решение вопросиков.", "price": 600},
    "guide": {"cat": "Средние", "name": "🗣 Горе-Гид", "desc": "Небылицы о каждом столбе.", "price": 350},
    "psych": {"cat": "Средние", "name": "🧠 Душеприказчик", "desc": "Слушаем кручину, даем советы.", "price": 1000},
    "spy": {"cat": "Большие", "name": "🕵️ Опричник (007)", "desc": "Тайная слежка и уход от погони.", "price": 1500},
    "karaoke": {"cat": "Большие", "name": "🎤 Застольные песни", "desc": "Орем песни дуэтом на всю улицу.", "price": 800},
    "dance": {"cat": "Большие", "name": "🐻 Медвежьи пляски", "desc": "Танцы на капоте на светофоре.", "price": 1200},
    "kidnap": {"cat": "Дикие", "name": "🎭 Похищение", "desc": "В мешок и в лес (понарошку).", "price": 3000},
    "tarzan": {"cat": "Дикие", "name": "🦍 Леший", "desc": "Рычим на прохожих, пугаем девок.", "price": 2000},
    "burn": {"cat": "Дикие", "name": "🔥 Огненная колесница", "desc": "Сжигаем повозку на пустыре.", "price": 50000},
    "eyes": {"cat": "Светские", "name": "👁️ Очи чёрные", "desc": "Комплимент вашим глазам.", "price": 50},
    "smile": {"cat": "Светские", "name": "😁 Улыбка", "desc": "Комплимент вашей улыбке.", "price": 50},
    "style": {"cat": "Светские", "name": "👠 Модный приговор", "desc": "Восхищение нарядом.", "price": 100},
    "improv": {"cat": "Светские", "name": "✨ Импровизация", "desc": "Ямщик сам придумает потеху.", "price": 500},
    "propose": {"cat": "Светские", "name": "💍 Сватовство", "desc": "Предложение руки и сердца.", "price": 10000}
}

# ==========================================
# 🗄️ БАЗА ДАННЫХ
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS drivers (
        user_id INTEGER PRIMARY KEY, username TEXT, fio TEXT, car_info TEXT, payment_info TEXT, access_code TEXT UNIQUE, 
        status TEXT DEFAULT 'pending', role TEXT DEFAULT 'driver', balance INTEGER DEFAULT 0, lat REAL, lon REAL)""")
    cur.execute("CREATE TABLE IF NOT EXISTS custom_services (id INTEGER PRIMARY KEY AUTOINCREMENT, driver_id INTEGER, name TEXT, description TEXT, price INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER DEFAULT NULL)")
    cur.execute("INSERT OR IGNORE INTO drivers (user_id, fio, access_code, status, role) VALUES (?, 'СТАРОСТА', 'ADMIN', 'active', 'owner')", (OWNER_ID,))
    conn.commit(); conn.close()

init_db()

# ==========================================
# 📡 WEB API (ДИНАМИКА)
# ==========================================
async def get_services(request):
    uid = int(request.query.get('user_id', 0))
    with sqlite3.connect(DB_PATH) as con:
        cli = con.execute("SELECT linked_driver_id FROM clients WHERE user_id=?", (uid,)).fetchone()
        if not cli or not cli[0]: return web.json_response({"error": "no_driver"})
        did = cli[0]
        customs = con.execute("SELECT name, description, price FROM custom_services WHERE driver_id=?", (did,)).fetchall()
    
    # Формируем список: стандарт + личные
    res = []
    for k, v in CRAZY_SERVICES.items():
        res.append({"name": v['name'], "desc": v['desc'], "price": v['price'], "cat": v['cat']})
    for c in customs:
        res.append({"name": c[0], "desc": c[1], "price": c[2], "cat": "ЛИЧНЫЕ"})
    return web.json_response(res)

async def web_order(request):
    data = await request.json()
    uid, srv, price, lat, lon = data.get('user_id'), data.get('service'), data.get('price'), data.get('lat'), data.get('lon')
    with sqlite3.connect(DB_PATH) as con:
        cli = con.execute("SELECT linked_driver_id FROM clients WHERE user_id=?", (uid,)).fetchone()
    if not cli: return web.json_response({"status": "error"})
    
    map_url = f"https://www.google.com/maps?q={lat},{lon}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"ok_{uid}")]])
    await bot.send_message(cli[0], f"🔔 <b>ЗАКАЗ!</b>\n🎭 {srv}\n💰 {price}₽\n📍 <a href='{map_url}'>МЕСТО ВСТРЕЧИ</a>", reply_markup=kb)
    return web.json_response({"status": "ok"})

# ==========================================
# 🤖 BOT LOGIC (HR + МОДЕРАЦИЯ)
# ==========================================
class DriverReg(StatesGroup): fio=State(); car=State(); pay=State(); code=State()
class AdminMsg(StatesGroup): text=State()
class CustomSrv(StatesGroup): name=State(); desc=State(); price=State()

@dp.message(Command("start"))
async def start(m: types.Message):
    with sqlite3.connect(DB_PATH) as con: con.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (m.from_user.id,))
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🚖 ЗАКАЗАТЬ ПОТЕХУ", web_app=WebAppInfo(url=APP_URL))],
                                       [KeyboardButton(text="👤 Моя Светлица"), KeyboardButton(text="🔑 Код Ямщика")]], resize_keyboard=True)
    await m.answer("🐎 <b>Артель приветствует!</b>", reply_markup=kb)

@dp.message(F.text == "🔑 Код Ямщика")
async def link_code(m: types.Message, state: FSMContext):
    await m.answer("Введите секретный код вашего Ямщика:"); await state.set_state("waiting_code")

@dp.message(F.state == "waiting_code")
async def process_code(m: types.Message, state: FSMContext):
    with sqlite3.connect(DB_PATH) as con:
        drv = con.execute("SELECT user_id FROM drivers WHERE access_code=? AND status='active'", (m.text.upper(),)).fetchone()
        if drv:
            con.execute("UPDATE clients SET linked_driver_id=? WHERE user_id=?", (drv[0], m.from_user.id))
            await m.answer("✅ Ямщик привязан! Можете заказывать.")
        else: await m.answer("❌ Код не найден или ямщик не одобрен.")
    await state.clear()

# (Здесь остаются все Handlers из v67.0: Регистрация /drive, Админка adm_requests, одобрение и т.д.)

# ==========================================
# 🚀 ЗАПУСК
# ==========================================
async def on_startup(app):
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))

def main():
    app = web.Application()
    app.router.add_get('/', lambda r: web.FileResponse(HTML_FILE))
    app.router.add_get('/get_services', get_services)
    app.router.add_post('/webapp_order', web_order)
    app.on_startup.append(on_startup)
    web.run_app(app, host='0.0.0.0', port=8080)

if __name__ == "__main__": main()
