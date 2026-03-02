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
# ⚙️ НАСТРОЙКИ
# ==========================================
logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("API_TOKEN")
OWNER_ID = int(os.getenv("DRIVER_ID", 0))
APP_URL = os.getenv("APP_URL")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(BASE_DIR, 'index.html')
DB_PATH = "/data/taxi_db.sqlite" if os.path.exists("/data") else os.path.join(BASE_DIR, "taxi_db.sqlite")

VIP_LIMIT = 10          
MIN_COMMISSION = 4      
DEFAULT_COMMISSION = 10 
LAWYER_LINK = "https://t.me/Ai_advokatrobot"

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
active_orders = {} 

# ==========================================
# 📜 ТЕКСТЫ И КОНЦЕПЦИЯ
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
    "butler": {"cat": 1, "name": "🤵 Дворецкий", "desc": "Кланяемся, величаем Барином."},
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
# 🗄️ БАЗА ДАННЫХ
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS drivers (
        user_id INTEGER PRIMARY KEY, fio TEXT, car_info TEXT, payment_info TEXT, access_code TEXT UNIQUE, 
        vip_code TEXT UNIQUE, status TEXT DEFAULT 'pending', role TEXT DEFAULT 'driver', 
        balance INTEGER DEFAULT 0, rating_sum INTEGER DEFAULT 0, rating_count INTEGER DEFAULT 0, 
        commission INTEGER DEFAULT 10, referred_by INTEGER, promo_end_date TIMESTAMP)""")
    cur.execute("CREATE TABLE IF NOT EXISTS driver_services (driver_id INTEGER, service_key TEXT, is_active BOOLEAN DEFAULT 1, PRIMARY KEY (driver_id, service_key))")
    cur.execute("CREATE TABLE IF NOT EXISTS custom_services (id INTEGER PRIMARY KEY AUTOINCREMENT, driver_id INTEGER, category_id INTEGER, name TEXT, description TEXT, price INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, commission INTEGER, duration INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER DEFAULT NULL, total_spent INTEGER DEFAULT 0, trips_count INTEGER DEFAULT 0, vip_unlocked BOOLEAN DEFAULT 0)")
    cur.execute("CREATE TABLE IF NOT EXISTS order_history (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, driver_id INTEGER, service_name TEXT, price INTEGER, rating INTEGER DEFAULT 0, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    
    # Гарантируем админа
    cur.execute("INSERT OR IGNORE INTO drivers (user_id, fio, access_code, status, role) VALUES (?, 'Староста', 'ADMIN', 'active', 'owner')", (OWNER_ID,))
    conn.commit(); conn.close()

init_db()

# ==========================================
# 🛠 УТИЛИТЫ
# ==========================================
def generate_vip_code(name):
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"BOYAR-{name.split()[0].upper()}-{suffix}"

def get_driver(uid):
    with sqlite3.connect(DB_PATH) as con: return con.execute("SELECT * FROM drivers WHERE user_id=?", (uid,)).fetchone()

def get_client(uid):
    with sqlite3.connect(DB_PATH) as con: return con.execute("SELECT * FROM clients WHERE user_id=?", (uid,)).fetchone()

def get_linked_driver_id(client_id):
    cli = get_client(client_id)
    return cli[1] if cli else None

def set_link(client_id, driver_id):
    with sqlite3.connect(DB_PATH) as con:
        # Сохраняем статистику если была
        old = con.execute("SELECT total_spent, trips_count, vip_unlocked FROM clients WHERE user_id=?", (client_id,)).fetchone()
        s, t, v = old if old else (0, 0, 0)
        con.execute("INSERT OR REPLACE INTO clients (user_id, linked_driver_id, total_spent, trips_count, vip_unlocked) VALUES (?, ?, ?, ?, ?)", (client_id, driver_id, s, t, v))

def get_menu(driver_id):
    with sqlite3.connect(DB_PATH) as con:
        act = [r[0] for r in con.execute("SELECT service_key FROM driver_services WHERE driver_id=? AND is_active=1", (driver_id,)).fetchall()]
        cust = con.execute("SELECT id, name, description, price FROM custom_services WHERE driver_id=?", (driver_id,)).fetchall()
    return act, cust

def is_admin(uid):
    if uid == OWNER_ID: return True
    d = get_driver(uid)
    return d and d[7] in ('owner', 'admin') # role index 7

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
        
        did = get_linked_driver_id(uid)
        if not did:
            await bot.send_message(uid, "🚫 <b>Сначала введите код Ямщика в боте!</b>")
            return web.json_response({"status": "no_driver"})
            
        active_orders[uid] = {"driver_id": did, "price": price, "service": srv}
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"ok_{uid}")]])
        await bot.send_message(did, f"🔔 <b>НОВЫЙ ЗАКАЗ:</b>\n🎭 {srv}\n💰 {price} руб.", reply_markup=kb)
        await bot.send_message(uid, "⏳ <b>Гонец отправлен Ямщику...</b>")
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "details": str(e)})

# ==========================================
# 🤖 BOT HANDLERS
# ==========================================
class DriverReg(StatesGroup): fio=State(); car=State(); pay=State(); ref=State(); code=State()
class Unlock(StatesGroup): key=State()
class AdminPromo(StatesGroup): code=State(); comm=State(); dur=State()
class AddCustom(StatesGroup): name=State(); desc=State(); price=State()

@dp.message(Command("start"))
async def start(message: types.Message):
    with sqlite3.connect(DB_PATH) as con: con.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (message.from_user.id,))
    
    url = APP_URL if APP_URL else "https://google.com"
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🚖 ЗАКАЗАТЬ ПОТЕХУ", web_app=WebAppInfo(url=url))],
        [KeyboardButton(text="👤 Моя Светлица"), KeyboardButton(text="🔑 Ввести код Ямщика")],
        [KeyboardButton(text="⚖️ Казённый Стряпчий")]
    ], resize_keyboard=True)
    await message.answer(WELCOME_TEXT, reply_markup=kb)

# КАБИНЕТ
@dp.message(F.text == "👤 Моя Светлица")
@dp.message(Command("cab"))
async def cabinet(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    
    # 1. Проверка Водителя
    drv = get_driver(uid)
    if drv:
        # Индексы: 1=fio, 4=access_code, 8=balance, 11=commission
        kb = [[InlineKeyboardButton(text="🎛 Репертуар", callback_data="menu_edit"), InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
              [InlineKeyboardButton(text="🤝 Приведи друга", callback_data="ref_prog"), InlineKeyboardButton(text="🆘 Староста", callback_data="sos_admin")]]
        
        # Активный заказ
        status = "📴 Свободен"
        for cid, o in active_orders.items():
            if o.get('driver_id') == uid:
                status = f"🔥 В ДЕЛЕ (Клиент {cid})"
                kb.insert(0, [InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ", callback_data=f"fin_{cid}")])
                break
        
        await message.answer(f"🪪 <b>ЯМЩИК: {drv[1]}</b>\n💰 Баланс: {drv[8]}₽\n🔑 Код: <code>{drv[4]}</code>\n📉 Оброк: {drv[11]}%\n\n{status}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    # 2. Проверка Клиента
    cli = get_client(uid)
    if cli:
        # Индексы: 1=linked, 2=spent, 3=trips
        link_txt = "❌ Нет ямщика"
        if cli[1]:
            d = get_driver(cli[1])
            if d: link_txt = f"✅ Ямщик: {d[1]}"
            
        await message.answer(f"👤 <b>СВЕТЛИЦА БОЯРИНА</b>\n{link_txt}\n💰 Потрачено: {cli[2]}₽ | Поездок: {cli[3]}")
    else:
        await message.answer("Вас нет в списках. Жмите /start")

# ЗАКАЗЫ
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
        did = o['driver_id']
        price = int(o['price'])
        # Обновляем базу
        with sqlite3.connect(DB_PATH) as con:
            con.execute("UPDATE clients SET total_spent=total_spent+?, trips_count=trips_count+1 WHERE user_id=?", (price, cid))
            d_info = con.execute("SELECT commission FROM drivers WHERE user_id=?", (did,)).fetchone()
            comm = int(price * (d_info[0]/100))
            con.execute("UPDATE drivers SET balance=balance+? WHERE user_id=?", (comm, did))
            con.execute("INSERT INTO order_history (client_id, driver_id, service_name, price) VALUES (?,?,?,?)", (cid, did, o['service'], price))
        
        del active_orders[cid]
    
    await call.message.edit_text("💰 <b>Мзда получена!</b>")
    await bot.send_message(cid, "🙏 Благодарим за щедрость!")

# ВВОД КОДА
@dp.message(F.text == "🔑 Ввести код Ямщика")
async def ask_key(message: types.Message, state: FSMContext):
    await message.answer("Введи код:")
    await state.set_state(Unlock.key)

@dp.message(Unlock.key)
async def check_key(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    with sqlite3.connect(DB_PATH) as con:
        drv = con.execute("SELECT user_id, fio FROM drivers WHERE access_code=? AND status='active'", (code,)).fetchone()
    
    if drv:
        set_link(message.from_user.id, drv[0])
        await message.answer(f"✅ Привязан к ямщику: <b>{drv[1]}</b>")
    else:
        await message.answer("❌ Нет такого кода.")
    await state.clear()

# РЕГИСТРАЦИЯ
@dp.message(Command("drive"))
async def reg_start(message: types.Message, state: FSMContext):
    if get_driver(message.from_user.id): return await message.answer("Уже в системе. /cab")
    await message.answer("ФИО:")
    await state.set_state(DriverReg.fio)

@dp.message(DriverReg.fio)
async def reg_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text); await message.answer("Авто:")
    await state.set_state(DriverReg.car)

@dp.message(DriverReg.car)
async def reg_car(message: types.Message, state: FSMContext):
    await state.update_data(car=message.text); await message.answer("Реквизиты:")
    await state.set_state(DriverReg.pay)

@dp.message(DriverReg.pay)
async def reg_pay(message: types.Message, state: FSMContext):
    await state.update_data(pay=message.text); await message.answer("Код друга (если есть):")
    await state.set_state(DriverReg.ref)

@dp.message(DriverReg.ref)
async def reg_ref(message: types.Message, state: FSMContext):
    await state.update_data(ref=message.text); await message.answer("Придумай свой код (ENGLISH):")
    await state.set_state(DriverReg.code)

@dp.message(DriverReg.code)
async def reg_fin(message: types.Message, state: FSMContext):
    d = await state.get_data()
    code = message.text.upper().strip()
    vip = generate_vip_code(d['fio'])
    
    with sqlite3.connect(DB_PATH) as con:
        if con.execute("SELECT 1 FROM drivers WHERE access_code=?", (code,)).fetchone():
            return await message.answer("Код занят!")
        con.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, vip_code, status) VALUES (?,?,?,?,?,?,?, 'pending')",
                    (message.from_user.id, message.from_user.username, d['fio'], d['car'], d['pay'], code, vip))
    
    await message.answer(f"✅ Заявка отправлена!\nКод: {code}")
    await safe_send(OWNER_ID, f"🚨 <b>НОВЫЙ:</b> {d['fio']}", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅", callback_data=f"adm_yes_{message.from_user.id}")]]))
    await state.clear()

@dp.callback_query(F.data.startswith("adm_yes_"))
async def adm_yes(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    did = int(call.data.split("_")[2])
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE drivers SET status='active' WHERE user_id=?", (did,))
    await safe_send(did, "✅ ВАС ПРИНЯЛИ! Жмите /cab")
    await call.message.edit_text("✅ Одобрено")

# АДМИНКА
@dp.message(Command("admin"))
async def adm_menu(message: types.Message):
    if not is_admin(message.from_user.id): return await message.answer("⛔ Нет прав")
    await message.answer("Админка", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Промокоды", callback_data="mk_promo")]]))

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
