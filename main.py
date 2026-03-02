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

# ==========================================
# 📜 ПОЛНЫЙ ПЕРЕЧЕНЬ УСЛУГ (20 ШТ)
# ==========================================
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
    # Полная структура таблицы водителей
    cur.execute("""CREATE TABLE IF NOT EXISTS drivers (
        user_id INTEGER PRIMARY KEY, username TEXT, fio TEXT, car_info TEXT, payment_info TEXT, access_code TEXT UNIQUE, 
        status TEXT DEFAULT 'pending', role TEXT DEFAULT 'driver', balance INTEGER DEFAULT 0, lat REAL, lon REAL)""")
    
    # Проверка на наличие колонок (миграция)
    cur.execute("PRAGMA table_info(drivers)")
    cols = [c[1] for c in cur.fetchall()]
    if 'username' not in cols: cur.execute("ALTER TABLE drivers ADD COLUMN username TEXT")
    if 'lat' not in cols: cur.execute("ALTER TABLE drivers ADD COLUMN lat REAL")
    if 'lon' not in cols: cur.execute("ALTER TABLE drivers ADD COLUMN lon REAL")

    cur.execute("CREATE TABLE IF NOT EXISTS custom_services (id INTEGER PRIMARY KEY AUTOINCREMENT, driver_id INTEGER, name TEXT, description TEXT, price INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER DEFAULT NULL)")
    
    # Гарантируем админа
    cur.execute("INSERT OR IGNORE INTO drivers (user_id, fio, access_code, status, role) VALUES (?, 'СТАРОСТА', 'ADMIN', 'active', 'owner')", (OWNER_ID,))
    cur.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (OWNER_ID,))
    
    conn.commit(); conn.close()

init_db()

# ==========================================
# 📡 WEB API (АГРЕГАТОР + GPS)
# ==========================================
async def get_services(request):
    uid = int(request.query.get('user_id', 0))
    with sqlite3.connect(DB_PATH) as con:
        # Проверка привязки
        cli = con.execute("SELECT linked_driver_id FROM clients WHERE user_id=?", (uid,)).fetchone()
        if not cli or not cli[0]: return web.json_response({"error": "no_driver"})
        
        did = cli[0]
        # Личные услуги
        customs = con.execute("SELECT name, description, price FROM custom_services WHERE driver_id=?", (did,)).fetchall()
    
    # Собираем общий список
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
    
    if not cli or not cli[0]: return web.json_response({"status": "no_driver"})
    
    active_orders[uid] = {"driver_id": cli[0]}
    
    # Ссылка на карту
    map_url = f"https://www.google.com/maps?q={lat},{lon}"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"ok_{uid}"),
         InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"fin_{uid}")]
    ])
    
    await bot.send_message(cli[0], f"🔔 <b>ЗАКАЗ!</b>\n🎭 {srv}\n💰 {price}₽\n📍 <a href='{map_url}'>ОТКРЫТЬ КАРТУ</a>", reply_markup=kb)
    return web.json_response({"status": "ok"})

# ==========================================
# 🤖 BOT HANDLERS (FSM & LOGIC)
# ==========================================
class DriverReg(StatesGroup): fio=State(); car=State(); pay=State(); code=State()
class AdminHR(StatesGroup): interview_text=State()
class AdminMsg(StatesGroup): text=State()
class CustomSrv(StatesGroup): name=State(); desc=State(); price=State()

# --- УТИЛИТЫ ---
def get_driver(uid):
    with sqlite3.connect(DB_
