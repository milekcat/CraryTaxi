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
# Берем ID из переменных. Если пусто или ошибка — ставим 0, чтобы бот не падал
try:
    OWNER_ID = int(os.getenv("DRIVER_ID", 0))
except:
    OWNER_ID = 0

APP_URL = os.getenv("APP_URL")

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
# 📜 КОНТЕНТ
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
    "candy": "🍬 Сладкий гостинец",
    "nose": "👃 Перст в носу",
    "butler": "🤵 Дворецкий",
    "joke": "🤡 Скоморох",
    "silence": "🤐 Обет молчания",
    "granny": "👵 Ворчливая бабка",
    "gopnik": "🍺 Разбойник",
    "guide": "🗣 Горе-Гид",
    "psych": "🧠 Душеприказчик",
    "spy": "🕵️ Опричник (007)",
    "karaoke": "🎤 Застольные песни",
    "dance": "🐻 Медвежьи пляски",
    "kidnap": "🎭 Похищение",
    "tarzan": "🦍 Леший",
    "burn": "🔥 Огненная колесница",
    "eyes": "👁️ Очи чёрные",
    "smile": "😁 Улыбка",
    "style": "👠 Модный приговор",
    "improv": "✨ Импровизация",
    "propose": "💍 Сватовство"
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
    cur.execute("CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, commission INTEGER, duration INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER DEFAULT NULL, total_spent INTEGER DEFAULT 0, trips_count INTEGER DEFAULT 0, vip_unlocked BOOLEAN DEFAULT 0)")
    cur.execute("CREATE TABLE IF NOT EXISTS order_history (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, driver_id INTEGER, service_name TEXT, price INTEGER, rating INTEGER DEFAULT 0, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    
    # Гарантируем админа (если ID задан)
    if OWNER_ID > 0:
        cur.execute("INSERT OR IGNORE INTO drivers (user_id, fio, access_code, status, role) VALUES (?, 'ГЛАВНЫЙ БОЯРИН', 'ADMIN', 'active', 'owner')", (OWNER_ID,))
        cur.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (OWNER_ID,))
    
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
        old = con.execute("SELECT total_spent, trips_count, vip_unlocked FROM clients WHERE user_id=?", (client_id,)).fetchone()
        s, t, v = old if old else (0, 0, 0)
        con.execute("INSERT OR REPLACE INTO clients (user_id, linked_driver_id, total_spent, trips_count, vip_unlocked) VALUES (?, ?, ?, ?, ?)", (client_id, driver_id, s, t, v))

def is_admin(uid):
    if uid == OWNER_ID: return True
    d = get_driver(uid)
    return d and d[7] in ('owner', 'admin')

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
class AdminBroadcast(StatesGroup): text=State()

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

# --- КАБИНЕТ (УМНЫЙ) ---
@dp.message(F.text == "👤 Моя Светлица")
@dp.message(Command("cab"))
async def cabinet(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    
    # 1. ВОДИТЕЛЬ
    drv = get_driver(uid)
    if drv:
        # drv: 0=id, 1=fio, 4=code, 7=role, 8=balance, 9=rating_sum, 10=rating_count, 11=comm
        rating = round(drv[9]/drv[10], 1) if drv[10] > 0 else "Новичок"
        
        kb = [
            [InlineKeyboardButton(text="🎛 Мой Репертуар (Вкл/Выкл)", callback_data="menu_edit")],
            [InlineKeyboardButton(text="🤝 Реферальная программа", callback_data="ref_prog")],
            [InlineKeyboardButton(text="🆘 Поддержка", url="https://t.me/milekcat")] # Замени на свой юзернейм
        ]
        
        # Активный заказ
        status = "🟢 Свободен"
        for cid, o in active_orders.items():
            if o.get('driver_id') == uid:
                status = f"🔥 В ДЕЛЕ (Клиент {cid})"
                kb.insert(0, [InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ ПОЕЗДКУ", callback_data=f"fin_{cid}")])
                break
        
        await message.answer(
            f"🪪 <b>КАБИНЕТ ЯМЩИКА</b>\n"
            f"👤 {drv[1]}\n"
            f"⭐️ Рейтинг: {rating}\n"
            f"💰 Баланс: {drv[8]}₽\n"
            f"🔑 Код доступа: <code>{drv[4]}</code>\n"
            f"📉 Комиссия Артели: {drv[11]}%\n"
            f"━━━━━━━━━━━━\n"
            f"Статус: {status}", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    # 2. КЛИЕНТ
    cli = get_client(uid)
    if cli:
        # cli: 1=linked_id, 2=spent, 3=trips
        link_txt = "❌ Ямщик не выбран (введите код!)"
        if cli[1]:
            d = get_driver(cli[1])
            if d: link_txt = f"✅ Ваш Ямщик: <b>{d[1]}</b>"
            
        vip_status = "👑 БОЯРИН" if cli[3] >= VIP_LIMIT else "Простой люд"
        
        conn = sqlite3.connect(DB_PATH)
        hist = conn.execute("SELECT service_name, price, date FROM order_history WHERE client_id=? ORDER BY id DESC LIMIT 5", (uid,)).fetchall()
        conn.close()
        
        h_text = "\n".join([f"▫️ {h[0]} ({h[1]}₽)" for h in hist]) if hist else "Пока не катались."
        
        await message.answer(
            f"👤 <b>СВЕТЛИЦА ПАССАЖИРА</b>\n"
            f"{link_txt}\n"
            f"Статус: {vip_status}\n"
            f"Поездок: {cli[3]} | Потрачено: {cli[2]}₽\n\n"
            f"📜 <b>Последние потехи:</b>\n{h_text}")
    else:
        await message.answer("Вас нет в списках. Жмите /start")

# --- ЛОГИКА ЗАКАЗОВ ---
@dp.callback_query(F.data.startswith("ok_"))
async def accept_order(call: types.CallbackQuery):
    cid = int(call.data.split("_")[1])
    await call.message.edit_text("✅ <b>Вы приняли заказ!</b>\nПодавайте карету!")
    await bot.send_message(cid, "✅ <b>Ямщик принял заказ!</b> Ждите карету.")

@dp.callback_query(F.data.startswith("fin_"))
async def finish_order(call: types.CallbackQuery):
    cid = int(call.data.split("_")[1])
    o = active_orders.get(cid)
    if o:
        did = o['driver_id']
        price = int(o['price'])
        
        with sqlite3.connect(DB_PATH) as con:
            # Обновляем клиента
            con.execute("UPDATE clients SET total_spent=total_spent+?, trips_count=trips_count+1 WHERE user_id=?", (price, cid))
            # Обновляем водителя (баланс и рейтинг)
            d_info = con.execute("SELECT commission FROM drivers WHERE user_id=?", (did,)).fetchone()
            comm = int(price * (d_info[0]/100))
            con.execute("UPDATE drivers SET balance=balance+?, rating_count=rating_count+1, rating_sum=rating_sum+5 WHERE user_id=?", (comm, did))
            # История
            con.execute("INSERT INTO order_history (client_id, driver_id, service_name, price) VALUES (?,?,?,?)", (cid, did, o['service'], price))
        
        del active_orders[cid]
    
    await call.message.edit_text("💰 <b>Поездка завершена!</b>\nМзда получена, оброк учтен.")
    await bot.send_message(cid, "🙏 <b>Поездка завершена!</b>\nБлагодарим за щедрость!")

# --- НАСТРОЙКИ ВОДИТЕЛЯ (МЕНЮ УСЛУГ) ---
@dp.callback_query(F.data == "menu_edit")
async def edit_menu(call: types.CallbackQuery):
    uid = call.from_user.id
    with sqlite3.connect(DB_PATH) as con:
        # Получаем отключенные услуги (если записи нет - значит включено по умолчанию, если 0 - выключено)
        # Для простоты: если запись есть и is_active=0, значит выкл. Иначе вкл.
        rows = con.execute("SELECT service_key FROM driver_services WHERE driver_id=? AND is_active=0", (uid,)).fetchall()
        disabled = [r[0] for r in rows]
        
    kb = []
    for key, name in CRAZY_SERVICES.items():
        status = "❌" if key in disabled else "✅"
        kb.append([InlineKeyboardButton(text=f"{status} {name}", callback_data=f"tgl_{key}")])
    
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_cab")])
    await call.message.edit_text("🎛 <b>ВАШ РЕПЕРТУАР:</b>\nНажмите, чтобы включить/выключить услугу.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("tgl_"))
async def toggle_service(call: types.CallbackQuery):
    key = call.data.split("_")[1]
    uid = call.from_user.id
    with sqlite3.connect(DB_PATH) as con:
        # Проверяем текущее состояние
        curr = con.execute("SELECT is_active FROM driver_services WHERE driver_id=? AND service_key=?", (uid, key)).fetchone()
        if curr:
            new_state = 1 if curr[0] == 0 else 0
            con.execute("UPDATE driver_services SET is_active=? WHERE driver_id=? AND service_key=?", (new_state, uid, key))
        else:
            # Если записи нет, значит было включено (1), ставим 0
            con.execute("INSERT INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, 0)", (uid, key))
    
    await edit_menu(call) # Обновляем меню

@dp.callback_query(F.data == "back_cab")
async def back_to_cab(call: types.CallbackQuery, state: FSMContext):
    await call.message.delete()
    await cabinet(call.message, state)

# --- ПРИВЯЗКА ---
@dp.message(F.text == "🔑 Ввести код Ямщика")
async def ask_key(message: types.Message, state: FSMContext):
    await message.answer("Введи код Ямщика:")
    await state.set_state(Unlock.key)

@dp.message(Unlock.key)
async def check_key(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    with sqlite3.connect(DB_PATH) as con:
        drv = con.execute("SELECT user_id, fio FROM drivers WHERE access_code=? AND status='active'", (code,)).fetchone()
    
    if drv:
        set_link(message.from_user.id, drv[0])
        await message.answer(f"✅ Успех! Вы привязаны к ямщику: <b>{drv[1]}</b>")
    else:
        await message.answer("❌ Нет такого кода.")
    await state.clear()

# --- АДМИНКА (FULL) ---
@dp.message(Command("admin"))
async def adm_menu(message: types.Message):
    if not is_admin(message.from_user.id): 
        return await message.answer(f"⛔ <b>ДОСТУП ЗАПРЕЩЕН</b>\nВаш ID: {message.from_user.id}\nТребуемый ID: {OWNER_ID}")
    
    conn = sqlite3.connect(DB_PATH)
    drivers_count = conn.execute("SELECT COUNT(*) FROM drivers").fetchone()[0]
    orders_count = conn.execute("SELECT COUNT(*) FROM order_history").fetchone()[0]
    money_sum = conn.execute("SELECT SUM(price) FROM order_history").fetchone()[0] or 0
    conn.close()

    kb = [
        [InlineKeyboardButton(text="📢 Рассылка всем", callback_data="adm_cast")],
        [InlineKeyboardButton(text="🎟 Создать Промокод", callback_data="mk_promo")],
        [InlineKeyboardButton(text="🔄 Обновить базу", callback_data="adm_refresh")]
    ]
    
    await message.answer(
        f"👑 <b>ПАНЕЛЬ СТАРОСТЫ</b>\n"
        f"👨‍✈️ Всего ямщиков: {drivers_count}\n"
        f"🚕 Всего поездок: {orders_count}\n"
        f"💰 Оборот Артели: {money_sum}₽", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "adm_cast")
async def adm_broadcast_ask(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Введите текст для рассылки всем пользователям:")
    await state.set_state(AdminBroadcast.text)

@dp.message(AdminBroadcast.text)
async def adm_broadcast_send(message: types.Message, state: FSMContext):
    text = message.text
    conn = sqlite3.connect(DB_PATH)
    users = conn.execute("SELECT user_id FROM clients UNION SELECT user_id FROM drivers").fetchall()
    conn.close()
    
    count = 0
    for u in users:
        if await safe_send(u[0], f"📣 <b>ОБЪЯВЛЕНИЕ АРТЕЛИ:</b>\n\n{text}"):
            count += 1
    
    await message.answer(f"✅ Рассылка завершена. Получили: {count} чел.")
    await state.clear()

@dp.callback_query(F.data == "mk_promo")
async def mk_promo(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите код промокода:")
    await state.set_state(AdminPromo.code)

@dp.message(AdminPromo.code)
async def pr_c(message: types.Message, state: FSMContext):
    await state.update_data(c=message.text); await message.answer("Скидка комиссии (%):")
    await state.set_state(AdminPromo.comm)

@dp.message(AdminPromo.comm)
async def pr_cm(message: types.Message, state: FSMContext):
    await state.update_data(cm=int(message.text)); await message.answer("Срок действия (дней):")
    await state.set_state(AdminPromo.dur)

@dp.message(AdminPromo.dur)
async def pr_d(message: types.Message, state: FSMContext):
    d = await state.get_data()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO promo_codes VALUES (?, ?, ?)", (d['c'], d['cm'], int(message.text)))
    conn.commit(); conn.close()
    await message.answer("✅ Промокод создан!"); await state.clear()

# --- РЕГИСТРАЦИЯ ВОДИТЕЛЯ (ПОЛНАЯ) ---
@dp.message(Command("drive"))
async def reg_start(message: types.Message, state: FSMContext):
    if get_driver(message.from_user.id): return await message.answer("Вы уже Ямщик! /cab")
    await message.answer("📝 <b>АНКЕТА ЯМЩИКА</b>\n\nКак вас величать? (ФИО)")
    await state.set_state(DriverReg.fio)

@dp.message(DriverReg.fio)
async def reg_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await message.answer("На какой колеснице скачете? (Марка, Цвет, Номер)")
    await state.set_state(DriverReg.car)

@dp.message(DriverReg.car)
async def reg_car(message: types.Message, state: FSMContext):
    await state.update_data(car=message.text)
    await message.answer("Куда монеты ссыпать? (Номер карты/телефон)")
    await state.set_state(DriverReg.pay)

@dp.message(DriverReg.pay)
async def reg_pay(message: types.Message, state: FSMContext):
    await state.update_data(pay=message.text)
    await message.answer("Код приглашения (если есть, или минус):")
    await state.set_state(DriverReg.ref)

@dp.message(DriverReg.ref)
async def reg_ref(message: types.Message, state: FSMContext):
    await state.update_data(ref=message.text)
    await message.answer("Придумайте секретный КОД ЯМЩИКА (латиница):")
    await state.set_state(DriverReg.code)

@dp.message(DriverReg.code)
async def reg_fin(message: types.Message, state: FSMContext):
    d = await state.get_data()
    code = message.text.upper().strip()
    vip = generate_vip_code(d['fio'])
    
    with sqlite3.connect(DB_PATH) as con:
        if con.execute("SELECT 1 FROM drivers WHERE access_code=?", (code,)).fetchone():
            return await message.answer("❌ Этот код уже занят другим ямщиком. Придумайте другой.")
        
        con.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, vip_code, status) VALUES (?,?,?,?,?,?,?, 'pending')",
                    (message.from_user.id, message.from_user.username, d['fio'], d['car'], d['pay'], code, vip))
    
    await message.answer(f"✅ <b>Заявка отправлена Старосте!</b>\nЖдите одобрения.\nВаш код: {code}")
    
    # Уведомление админу
    if OWNER_ID > 0:
        msg = f"🚨 <b>НОВЫЙ КАНДИДАТ!</b>\n👤 {d['fio']}\n🚘 {d['car']}\n💳 {d['pay']}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"adm_yes_{message.from_user.id}")]])
        await safe_send(OWNER_ID, msg, kb)
    
    await state.clear()

@dp.callback_query(F.data.startswith("adm_yes_"))
async def adm_approve(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    did = int(call.data.split("_")[2])
    with sqlite3.connect(DB_PATH) as con:
        con.execute("UPDATE drivers SET status='active' WHERE user_id=?", (did,))
    await safe_send(did, "🎉 <b>ВАС ПРИНЯЛИ В АРТЕЛЬ!</b>\nЖмите /cab для выхода на линию.")
    await call.message.edit_text(f"{call.message.text}\n\n✅ ОДОБРЕНО")


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
