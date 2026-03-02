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
# 📜 ПОЛНЫЙ КОНТЕНТ УСЛУГ
# ==========================================
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

# ==========================================
# 🗄️ ИСПРАВЛЕНИЕ И ИНИЦИАЛИЗАЦИЯ БАЗЫ
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS drivers (
        user_id INTEGER PRIMARY KEY, fio TEXT, car_info TEXT, payment_info TEXT, access_code TEXT UNIQUE, 
        vip_code TEXT UNIQUE, status TEXT DEFAULT 'pending', role TEXT DEFAULT 'driver', 
        balance INTEGER DEFAULT 0, rating_sum INTEGER DEFAULT 0, rating_count INTEGER DEFAULT 0, 
        commission INTEGER DEFAULT 10, referred_by INTEGER, promo_end_date TIMESTAMP)""")
    
    # ПРОВЕРКА И ДОБАВЛЕНИЕ username (Fix OperationalError)
    cur.execute("PRAGMA table_info(drivers)")
    columns = [column[1] for column in cur.fetchall()]
    if 'username' not in columns:
        cur.execute("ALTER TABLE drivers ADD COLUMN username TEXT")
    
    cur.execute("CREATE TABLE IF NOT EXISTS driver_services (driver_id INTEGER, service_key TEXT, is_active BOOLEAN DEFAULT 1, PRIMARY KEY (driver_id, service_key))")
    cur.execute("CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, commission INTEGER, duration INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER DEFAULT NULL, total_spent INTEGER DEFAULT 0, trips_count INTEGER DEFAULT 0, vip_unlocked BOOLEAN DEFAULT 0)")
    cur.execute("CREATE TABLE IF NOT EXISTS order_history (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, driver_id INTEGER, service_name TEXT, price INTEGER, rating INTEGER DEFAULT 0, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    
    # Назначаем вас владельцем принудительно
    cur.execute("INSERT OR IGNORE INTO drivers (user_id, fio, access_code, status, role) VALUES (?, 'ГЛАВНЫЙ БОЯРИН', 'ADMIN', 'active', 'owner')", (OWNER_ID,))
    cur.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (OWNER_ID,))
    
    conn.commit(); conn.close()

init_db()

# ==========================================
# 🛠 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def generate_vip_code(name):
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"BOYAR-{name.split()[0].upper()}-{suffix}"

def get_driver(uid):
    with sqlite3.connect(DB_PATH) as con: return con.execute("SELECT * FROM drivers WHERE user_id=?", (uid,)).fetchone()

def get_client(uid):
    with sqlite3.connect(DB_PATH) as con: return con.execute("SELECT * FROM clients WHERE user_id=?", (uid,)).fetchone()

def set_link(client_id, driver_id):
    with sqlite3.connect(DB_PATH) as con:
        old = con.execute("SELECT total_spent, trips_count, vip_unlocked FROM clients WHERE user_id=?", (client_id,)).fetchone()
        s, t, v = old if old else (0, 0, 0)
        con.execute("INSERT OR REPLACE INTO clients (user_id, linked_driver_id, total_spent, trips_count, vip_unlocked) VALUES (?, ?, ?, ?, ?)", (client_id, driver_id, s, t, v))

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
        await bot.send_message(uid, "⏳ <b>Гонец отправлен Ямщику...</b>")
        return web.json_response({"status": "ok"})
    except: return web.json_response({"status": "error"})

# ==========================================
# 🤖 BOT HANDLERS
# ==========================================
class DriverReg(StatesGroup): fio=State(); car=State(); pay=State(); ref=State(); code=State()
class Unlock(StatesGroup): key=State()
class AdminBroadcast(StatesGroup): text=State()
class AdminPromo(StatesGroup): code=State(); comm=State(); dur=State()

@dp.message(Command("start"))
async def start(message: types.Message):
    with sqlite3.connect(DB_PATH) as con: con.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (message.from_user.id,))
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🚖 ЗАКАЗАТЬ ПОТЕХУ", web_app=WebAppInfo(url=APP_URL))],
        [KeyboardButton(text="👤 Моя Светлица"), KeyboardButton(text="🔑 Ввести код Ямщика")],
        [KeyboardButton(text="⚖️ Казённый Стряпчий")]
    ], resize_keyboard=True)
    await message.answer(WELCOME_TEXT, reply_markup=kb)

# --- ЛИЧНЫЕ КАБИНЕТЫ ---
@dp.message(F.text == "👤 Моя Светлица")
@dp.message(Command("cab"))
async def cabinet(message: types.Message):
    uid = message.from_user.id
    drv = get_driver(uid)
    if drv:
        # Водитель. drv: 1=fio, 4=code, 8=balance, 11=commission
        kb = [[InlineKeyboardButton(text="🎛 Репертуар", callback_data="menu_edit")],
              [InlineKeyboardButton(text="🤝 Реферальная программа", callback_data="ref_prog")],
              [InlineKeyboardButton(text="📊 История заказов", callback_data="drv_hist")]]
        
        status = "🟢 Свободен"
        for cid, o in active_orders.items():
            if o.get('driver_id') == uid:
                status = f"🔥 В ДЕЛЕ (Клиент {cid})"
                kb.insert(0, [InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ", callback_data=f"fin_{cid}")])
                break
        
        await message.answer(f"🪪 <b>ЯМЩИК: {drv[1]}</b>\n💰 Баланс: {drv[8]}₽\n🔑 Код: <code>{drv[4]}</code>\n📉 Оброк: {drv[11]}%\n\n{status}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    cli = get_client(uid)
    if cli:
        # Клиент. cli: 1=linked, 2=spent, 3=trips
        link_txt = "❌ Нет ямщика"
        if cli[1]:
            d = get_driver(cli[1])
            if d: link_txt = f"✅ Ваш Ямщик: <b>{d[1]}</b>"
        
        await message.answer(f"👤 <b>СВЕТЛИЦА БОЯРИНА</b>\n{link_txt}\n💰 Потрачено: {cli[2]}₽\n🎬 Поездок: {cli[3]}")
    else:
        await message.answer("Вас нет в списках. Жмите /start")

# --- УПРАВЛЕНИЕ РЕПЕРТУАРОМ ---
@dp.callback_query(F.data == "menu_edit")
async def menu_edit(call: types.CallbackQuery):
    uid = call.from_user.id
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute("SELECT service_key FROM driver_services WHERE driver_id=? AND is_active=0", (uid,)).fetchall()
        disabled = [r[0] for r in rows]
    
    kb = []
    for k, v in CRAZY_SERVICES.items():
        st = "❌" if k in disabled else "✅"
        kb.append([InlineKeyboardButton(text=f"{st} {v['name']}", callback_data=f"tgl_{k}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_cab")])
    await call.message.edit_text("🎛 <b>ВАШ РЕПЕРТУАР:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("tgl_"))
async def tgl_service(call: types.CallbackQuery):
    key = call.data.split("_")[1]
    uid = call.from_user.id
    with sqlite3.connect(DB_PATH) as con:
        curr = con.execute("SELECT is_active FROM driver_services WHERE driver_id=? AND service_key=?", (uid, key)).fetchone()
        new_s = 1 if curr and curr[0] == 0 else 0
        con.execute("INSERT OR REPLACE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, ?)", (uid, key, new_s))
    await menu_edit(call)

# --- ЛОГИКА ЗАКАЗОВ ---
@dp.callback_query(F.data.startswith("ok_"))
async def accept_order(call: types.CallbackQuery):
    cid = int(call.data.split("_")[1])
    await call.message.edit_text("✅ <b>Вы приняли заказ!</b>")
    await bot.send_message(cid, "✅ <b>Ямщик принял заказ!</b> Ждите карету.")

@dp.callback_query(F.data.startswith("fin_"))
async def finish_order(call: types.CallbackQuery):
    cid = int(call.data.split("_")[1])
    o = active_orders.get(cid)
    if o:
        did, price = o['driver_id'], int(o['price'])
        with sqlite3.connect(DB_PATH) as con:
            con.execute("UPDATE clients SET total_spent=total_spent+?, trips_count=trips_count+1 WHERE user_id=?", (price, cid))
            d_info = con.execute("SELECT commission FROM drivers WHERE user_id=?", (did,)).fetchone()
            comm = int(price * (d_info[0]/100))
            con.execute("UPDATE drivers SET balance=balance+?, rating_count=rating_count+1, rating_sum=rating_sum+5 WHERE user_id=?", (comm, did))
            con.execute("INSERT INTO order_history (client_id, driver_id, service_name, price) VALUES (?,?,?,?)", (cid, did, o['service'], price))
        del active_orders[cid]
    await call.message.edit_text("💰 <b>Мзда получена!</b>")
    await bot.send_message(cid, "🙏 Поездка завершена! Ждем вас снова.")

# --- РЕГИСТРАЦИЯ ВОДИТЕЛЯ (V30-40) ---
@dp.message(Command("drive"))
async def reg_start(message: types.Message, state: FSMContext):
    if get_driver(message.from_user.id): return await message.answer("Вы уже Ямщик!")
    await message.answer("📝 <b>АНКЕТА ЯМЩИКА</b>\n\nКак вас величать? (ФИО)")
    await state.set_state(DriverReg.fio)

@dp.message(DriverReg.fio)
async def reg_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text); await message.answer("На какой колеснице скачете? (Марка, Цвет, Номер)")
    await state.set_state(DriverReg.car)

@dp.message(DriverReg.car)
async def reg_car(message: types.Message, state: FSMContext):
    await state.update_data(car=message.text); await message.answer("Куда монеты ссыпать? (Карта/Телефон)")
    await state.set_state(DriverReg.pay)

@dp.message(DriverReg.pay)
async def reg_pay(message: types.Message, state: FSMContext):
    await state.update_data(pay=message.text); await message.answer("Придумайте свой секретный код (ENGLISH):")
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
    except: await message.answer("❌ Код занят!")
    await state.clear()

# --- АДМИН-ПАНЕЛЬ (ПОЛНАЯ) ---
@dp.message(Command("admin"))
async def admin_p(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    conn = sqlite3.connect(DB_PATH)
    stats = conn.execute("SELECT COUNT(*), SUM(balance) FROM drivers").fetchone()
    kb = [[InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_cast")],
          [InlineKeyboardButton(text="🎟 Создать Промо", callback_data="mk_promo")]]
    await message.answer(f"👑 <b>ПАНЕЛЬ СТАРОСТЫ</b>\nЯмщиков: {stats[0]}\nОборот: {stats[1] or 0}₽", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "adm_cast")
async def adm_cast_ask(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Введите текст рассылки:"); await state.set_state(AdminBroadcast.text)

@dp.message(AdminBroadcast.text)
async def adm_cast_send(message: types.Message, state: FSMContext):
    conn = sqlite3.connect(DB_PATH)
    users = conn.execute("SELECT user_id FROM clients UNION SELECT user_id FROM drivers").fetchall()
    for u in users: await safe_send(u[0], f"📣 <b>ОБЪЯВЛЕНИЕ:</b>\n\n{message.text}")
    await message.answer("✅ Отправлено"); await state.clear()

# --- ВВОД КОДА ЯМЩИКА ---
@dp.message(F.text == "🔑 Ввести код Ямщика")
async def ask_key(message: types.Message, state: FSMContext):
    await message.answer("Введи код Ямщика:"); await state.set_state(Unlock.key)

@dp.message(Unlock.key)
async def check_key(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    with sqlite3.connect(DB_PATH) as con:
        drv = con.execute("SELECT user_id, fio FROM drivers WHERE access_code=? AND status='active'", (code,)).fetchone()
    if drv:
        set_link(message.from_user.id, drv[0])
        await message.answer(f"✅ Успех! Ямщик: {drv[1]}")
    else: await message.answer("❌ Неверный код.")
    await state.clear()

@dp.callback_query(F.data == "back_cab")
async def back_cab(call: types.CallbackQuery, state: FSMContext):
    await call.message.delete(); await cabinet(call.message)

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
