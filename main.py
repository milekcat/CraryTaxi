import asyncio
import logging
import os
import sqlite3
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
# ⚙️ НАСТРОЙКИ (С ПРОВЕРКОЙ)
# ==========================================
logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("API_TOKEN")
OWNER_ID_STR = os.getenv("DRIVER_ID")
APP_URL = os.getenv("APP_URL")

# Проверка переменных при старте
if not API_TOKEN: logging.critical("❌ ОШИБКА: Нет API_TOKEN")
if not OWNER_ID_STR: logging.critical("❌ ОШИБКА: Нет DRIVER_ID")
if not APP_URL: logging.warning("⚠️ ПРЕДУПРЕЖДЕНИЕ: Нет APP_URL, кнопка может не работать")

try:
    OWNER_ID = int(OWNER_ID_STR)
except:
    logging.critical(f"❌ ОШИБКА: DRIVER_ID должен быть числом, а не '{OWNER_ID_STR}'")
    OWNER_ID = 0

SUPER_ADMINS = [OWNER_ID]

# Пути
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(BASE_DIR, 'index.html')
DB_PATH = "/data/taxi_db.sqlite" if os.path.exists("/data") else os.path.join(BASE_DIR, "taxi_db.sqlite")

# Проверка наличия HTML
if os.path.exists(HTML_FILE):
    logging.info(f"✅ Файл index.html НАЙДЕН по пути: {HTML_FILE}")
else:
    logging.critical(f"❌ ОШИБКА: Файл index.html НЕ НАЙДЕН по пути: {HTML_FILE}. Проверьте GitHub!")

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
active_orders = {}

# ==========================================
# 🗄️ БАЗА ДАННЫХ
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Создаем таблицы (упрощенно для надежности)
    cur.execute("CREATE TABLE IF NOT EXISTS drivers (user_id INTEGER PRIMARY KEY, fio TEXT, access_code TEXT, vip_code TEXT, status TEXT, role TEXT, commission INTEGER DEFAULT 10, balance INTEGER DEFAULT 0, promo_end_date TIMESTAMP)")
    cur.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER, total_spent INTEGER DEFAULT 0, trips_count INTEGER DEFAULT 0, vip_unlocked INTEGER DEFAULT 0)")
    cur.execute("CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, commission INTEGER, duration INTEGER)")
    
    # Гарантируем админа
    cur.execute("INSERT OR REPLACE INTO drivers (user_id, fio, access_code, status, role) VALUES (?, 'Староста', 'ADMIN', 'active', 'owner')", (OWNER_ID,))
    conn.commit()
    conn.close()
    logging.info("✅ База данных инициализирована.")

init_db()

# ==========================================
# 🛠 УТИЛИТЫ
# ==========================================
def get_driver(uid):
    with sqlite3.connect(DB_PATH) as con:
        return con.execute("SELECT * FROM drivers WHERE user_id=?", (uid,)).fetchone()

def get_client(uid):
    with sqlite3.connect(DB_PATH) as con:
        return con.execute("SELECT * FROM clients WHERE user_id=?", (uid,)).fetchone()

# ==========================================
# 📡 WEB SERVER
# ==========================================
async def main_page(request):
    logging.info(f"🌍 WEB: Запрос главной страницы от {request.remote}")
    try:
        with open(HTML_FILE, 'r', encoding='utf-8') as f:
            return web.Response(text=f.read(), content_type='text/html')
    except FileNotFoundError:
        return web.Response(text="<h1>ERROR: index.html missing</h1>", status=404, content_type='text/html')

async def web_order(request):
    try:
        data = await request.json()
        logging.info(f"🌍 WEB: Пришел заказ: {data}")
        
        uid = data.get('user_id')
        if not uid: return web.json_response({"error": "no_id"})
        
        # Проверка привязки
        cli = get_client(uid)
        did = cli[1] if cli else None # linked_driver_id is 2nd column
        
        if not did:
            await bot.send_message(uid, "🚫 <b>Сначала введите код Ямщика в боте!</b>")
            return web.json_response({"status": "no_driver"})
            
        active_orders[uid] = data
        
        # Уведомление водителю
        await bot.send_message(did, f"🔥 <b>НОВЫЙ ЗАКАЗ!</b>\n{data['service']}\n💰 {data['price']} руб.", 
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"ok_{uid}")]]))
        
        await bot.send_message(uid, "⏳ <b>Гонец отправлен Ямщику...</b>")
        return web.json_response({"status": "ok"})
    except Exception as e:
        logging.error(f"WEB ERROR: {e}")
        return web.json_response({"status": "error"})

# ==========================================
# 🤖 BOT HANDLERS
# ==========================================
@dp.message(Command("start"))
async def start(message: types.Message):
    # Регистрируем клиента
    with sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (message.from_user.id,))
    
    url = APP_URL if APP_URL else "https://google.com"
    logging.info(f"Start pressed by {message.from_user.id}. Web App URL: {url}")
    
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🚖 ЗАКАЗАТЬ (WEB)", web_app=WebAppInfo(url=url))],
        [KeyboardButton(text="👤 Личный кабинет"), KeyboardButton(text="🔑 Ввести код")]
    ], resize_keyboard=True)
    
    await message.answer("🐎 <b>ВЕСЁЛЫЙ ИЗВОЗЧИК</b>\n\nЕсли кнопка «ЗАКАЗАТЬ» не работает — значит ссылка APP_URL указана неверно.", reply_markup=kb)

# КАБИНЕТ (С ДИАГНОСТИКОЙ)
@dp.message(F.text == "👤 Личный кабинет")
@dp.message(Command("cab"))
async def cabinet(message: types.Message):
    uid = message.from_user.id
    logging.info(f"Cabinet requested by {uid}")
    
    # 1. Это Админ/Водитель?
    drv = get_driver(uid)
    if drv:
        role = drv[5] # role column
        await message.answer(f"🪪 <b>КАБИНЕТ ЯМЩИКА</b>\nРоль: {role}\nID: {uid}\n\nКоманды:\n/admin - Админка")
        return

    # 2. Это Клиент?
    cli = get_client(uid)
    if cli:
        link = cli[1] # linked_driver
        link_txt = f"Привязан к {link}" if link else "❌ Нет ямщика (введите код)"
        await message.answer(f"👤 <b>КАБИНЕТ БОЯРИНА</b>\n{link_txt}\nПотрачено: {cli[2]}₽")
    else:
        await message.answer("❌ Ошибка: Вас нет в базе. Нажмите /start")

# АДМИНКА (С ПРОВЕРКОЙ ПРАВ)
@dp.message(Command("admin"))
async def admin(message: types.Message):
    uid = message.from_user.id
    if uid == OWNER_ID:
        await message.answer(f"👑 <b>АДМИН-ПАНЕЛЬ</b>\nТвой ID: {uid} (Совпадает с Главным)\n\nКоманды:\n/promo - Создать промокод")
    else:
        await message.answer(f"⛔ <b>ДОСТУП ЗАПРЕЩЕН</b>\nТвой ID: {uid}\nID Главного: {OWNER_ID}\n\nЕсли это ты, проверь переменную DRIVER_ID в Amvera!")

# ВВОД КОДА
@dp.message(F.text == "🔑 Ввести код")
async def ask_code(message: types.Message, state: FSMContext):
    await message.answer("Введи код Ямщика:")
    await state.set_state(UnlockState.code)

class UnlockState(StatesGroup): code = State()

@dp.message(UnlockState.code)
async def check_code(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    with sqlite3.connect(DB_PATH) as con:
        drv = con.execute("SELECT user_id, fio FROM drivers WHERE access_code=?", (code,)).fetchone()
    
    if drv:
        with sqlite3.connect(DB_PATH) as con:
            con.execute("UPDATE clients SET linked_driver_id=? WHERE user_id=?", (drv[0], message.from_user.id))
        await message.answer(f"✅ Успех! Ямщик: {drv[1]}")
    else:
        await message.answer("❌ Неверный код.")
    await state.clear()

@dp.callback_query(F.data.startswith("ok_"))
async def ok_order(call: types.CallbackQuery):
    uid = int(call.data.split("_")[1])
    await call.message.edit_text("✅ Заказ принят!")
    await bot.send_message(uid, "✅ Ямщик выехал!")

# ==========================================
# 🚀 ЗАПУСК
# ==========================================
async def on_startup(app):
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))
    logging.info(f"🚀 БОТ ЗАПУЩЕН. Порт: 8080. HTML: {HTML_FILE}")

def main():
    app = web.Application()
    app.router.add_get('/', main_page)
    app.router.add_post('/webapp_order', web_order)
    app.on_startup.append(on_startup)
    web.run_app(app, host='0.0.0.0', port=8080)

if __name__ == "__main__":
    main()
