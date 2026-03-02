import asyncio
import logging
import os
import sqlite3
import re
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
# ⚙️ 1. НАСТРОЙКИ И ПУТИ
# ==========================================
logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("API_TOKEN")
OWNER_ID_STR = os.getenv("DRIVER_ID")
APP_URL = os.getenv("APP_URL") 

if not API_TOKEN or not OWNER_ID_STR:
    logging.critical("⛔ CRITICAL ERROR: Token or ID missing")
    exit()

OWNER_ID = int(OWNER_ID_STR)
SUPER_ADMINS = [OWNER_ID]

# Абсолютные пути для Amvera
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
# 📜 2. КОНТЕНТ (ВЕСЁЛЫЙ ИЗВОЗЧИК)
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
    "candy": {"cat": 1, "price": 0, "name": "🍬 Сладкий гостинец", "desc": "Ямщик с поклоном вручает леденец."},
    "nose": {"cat": 1, "price": 300, "name": "👃 Перст в носу", "desc": "Ямщик всю дорогу в носу ковыряет."},
    "butler": {"cat": 1, "price": 200, "name": "🤵 Дворецкий", "desc": "Открываем дверь, кланяемся, величаем Барином."},
    "joke": {"cat": 1, "price": 50, "name": "🤡 Скоморох", "desc": "Шутка юмора. Смеяться обязательно."},
    "silence": {"cat": 1, "price": 150, "name": "🤐 Обет молчания", "desc": "Едем молча, как в монастыре."},
    "granny": {"cat": 2, "price": 800, "name": "👵 Ворчливая бабка", "desc": "Ролевая игра: Куда прешь, окаянный!"},
    "gopnik": {"cat": 2, "price": 500, "name": "🍺 Разбойник", "desc": "Шансон, семки, решение вопросиков."},
    "guide": {"cat": 2, "price": 600, "name": "🗣 Горе-Гид", "desc": "Небылицы о каждом столбе."},
    "psych": {"cat": 2, "price": 1000, "name": "🧠 Душеприказчик", "desc": "Слушаем кручину, даем советы."},
    "spy": {"cat": 3, "price": 2000, "name": "🕵️ Опричник (007)", "desc": "Тайная слежка и уход от погони."},
    "karaoke": {"cat": 3, "price": 5000, "name": "🎤 Застольные песни", "desc": "Орем песни дуэтом на всю улицу."},
    "dance": {"cat": 3, "price": 15000, "name": "🐻 Медвежьи пляски", "desc": "Танцы на капоте на светофоре."},
    "kidnap": {"cat": 4, "price": 30000, "name": "🎭 Похищение", "desc": "В мешок и в лес (понарошку)."},
    "tarzan": {"cat": 4, "price": 50000, "name": "🦍 Леший", "desc": "Рычим на прохожих, пугаем девок."},
    "burn": {"cat": 4, "price": 1000000, "name": "🔥 Огненная колесница", "desc": "Сжигаем повозку на пустыре."},
    "eyes": {"cat": 5, "price": 0, "name": "👁️ Очи чёрные", "desc": "Комплимент вашим глазам."},
    "smile": {"cat": 5, "price": 0, "name": "😁 Улыбка", "desc": "Комплимент вашей улыбке."},
    "style": {"cat": 5, "price": 0, "name": "👠 Модный приговор", "desc": "Восхищение нарядом."},
    "improv": {"cat": 5, "price": 0, "name": "✨ Импровизация", "desc": "Ямщик сам придумает потеху."},
    "propose": {"cat": 5, "price": 1000, "name": "💍 Сватовство", "desc": "Предложение руки и сердца."}
}

CATEGORIES = {1: "🟢 ЛАЙТ", 2: "🟡 МЕДИУМ", 3: "🔴 ХАРД", 4: "☠️ ЦАРСКИЙ (VIP)", 5: "🌹 ДЛЯ БОЯРЫНЬ"}

# ==========================================
# 🗄️ 3. БАЗА ДАННЫХ
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            user_id INTEGER PRIMARY KEY,
            username TEXT, fio TEXT, car_info TEXT, payment_info TEXT,
            access_code TEXT UNIQUE, vip_code TEXT UNIQUE,
            status TEXT DEFAULT 'pending', role TEXT DEFAULT 'driver',
            balance INTEGER DEFAULT 0, rating_sum INTEGER DEFAULT 0, rating_count INTEGER DEFAULT 0, 
            commission INTEGER DEFAULT 10, referred_by INTEGER, promo_end_date TIMESTAMP
        )
    """)
    cursor.execute("CREATE TABLE IF NOT EXISTS driver_services (driver_id INTEGER, service_key TEXT, is_active BOOLEAN DEFAULT 1, PRIMARY KEY (driver_id, service_key))")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custom_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id INTEGER, category_id INTEGER, name TEXT, description TEXT, price INTEGER
        )
    """)
    cursor.execute("CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, commission INTEGER, duration INTEGER)")
    cursor.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER DEFAULT NULL, total_spent INTEGER DEFAULT 0, trips_count INTEGER DEFAULT 0, vip_unlocked BOOLEAN DEFAULT 0)")
    cursor.execute("CREATE TABLE IF NOT EXISTS order_history (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, driver_id INTEGER, service_name TEXT, price INTEGER, rating INTEGER DEFAULT 0, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    
    # Админ
    cursor.execute("INSERT OR IGNORE INTO drivers (user_id, username, fio, car_info, payment_info, access_code, vip_code, status, role) VALUES (?, 'BOSS', 'Староста', 'Карета', 'CASH', ?, ?, 'active', 'owner')", (OWNER_ID, f"ADMIN_{OWNER_ID}", f"VIP_{OWNER_ID}"))
    cursor.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (OWNER_ID,))
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 🛠 4. УТИЛИТЫ
# ==========================================
def generate_vip_code(name):
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"BOYAR-{name.split()[0].upper()}-{suffix}"

def get_driver_info(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT username, car_info, payment_info, balance, status, access_code, role, fio, rating_sum, rating_count, vip_code, commission, promo_end_date FROM drivers WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return res

def get_client_info(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT total_spent, trips_count, vip_unlocked, linked_driver_id FROM clients WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return res

def get_linked_driver(client_id):
    info = get_client_info(client_id)
    return info[3] if info else None

def set_linked_driver(client_id, driver_id):
    conn = sqlite3.connect(DB_PATH)
    # Сохраняем статистику, если она была
    curr = conn.execute("SELECT total_spent, trips_count, vip_unlocked FROM clients WHERE user_id=?", (client_id,)).fetchone()
    s, t, v = (curr[0], curr[1], curr[2]) if curr else (0, 0, 0)
    conn.execute("INSERT OR REPLACE INTO clients (user_id, linked_driver_id, total_spent, trips_count, vip_unlocked) VALUES (?, ?, ?, ?, ?)", (client_id, driver_id, s, t, v))
    conn.commit(); conn.close()

def get_driver_menu(driver_id):
    conn = sqlite3.connect(DB_PATH)
    active_keys = [r[0] for r in conn.execute("SELECT service_key FROM driver_services WHERE driver_id=? AND is_active=1", (driver_id,)).fetchall()]
    customs = conn.execute("SELECT id, category_id, name, description, price FROM custom_services WHERE driver_id=?", (driver_id,)).fetchall()
    conn.close()
    return active_keys, customs

def init_driver_services_defaults(driver_id):
    conn = sqlite3.connect(DB_PATH)
    for k in CRAZY_SERVICES:
        conn.execute("INSERT OR IGNORE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, 1)", (driver_id, k))
    conn.commit(); conn.close()

def is_admin(user_id):
    if user_id in SUPER_ADMINS: return True
    info = get_driver_info(user_id)
    return info and info[6] in ('owner', 'admin')

def get_active_drivers():
    conn = sqlite3.connect(DB_PATH)
    res = [d[0] for d in conn.execute("SELECT user_id FROM drivers WHERE status='active'").fetchall()]
    conn.close()
    return res

def check_and_reset_promo(driver_id):
    info = get_driver_info(driver_id)
    if info and info[12]: 
        try:
            date_str = str(info[12]).split('.')[0] # Убираем миллисекунды если есть
            end_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            if datetime.now() > end_date:
                conn = sqlite3.connect(DB_PATH)
                ref_count = conn.execute("SELECT COUNT(*) FROM drivers WHERE referred_by=?", (driver_id,)).fetchone()[0]
                new_comm = max(MIN_COMMISSION, DEFAULT_COMMISSION - ref_count)
                conn.execute("UPDATE drivers SET commission = ?, promo_end_date = NULL WHERE user_id = ?", (new_comm, driver_id))
                conn.commit(); conn.close()
        except Exception as e: logging.error(f"Promo date error: {e}")

async def safe_send(chat_id, text, kb=None):
    try: await bot.send_message(chat_id, text, reply_markup=kb); return True
    except: return False

# ==========================================
# 📡 WEB SERVER (ДЛЯ МИНИ-АППА)
# ==========================================
async def web_main_handler(request):
    try:
        with open(HTML_FILE, 'r', encoding='utf-8') as f:
            return web.Response(text=f.read(), content_type='text/html')
    except FileNotFoundError:
        return web.Response(text="<h1>ERROR 404: Index file not found</h1>", status=404, content_type='text/html')

async def web_order_handler(request):
    try:
        data = await request.json()
        uid = data.get('user_id')
        srv = data.get('service')
        price = data.get('price')
        
        did = get_linked_driver(uid)
        if not did:
            await bot.send_message(uid, "🚫 <b>Сначала введите код Ямщика в боте!</b>")
            return web.json_response({"status": "no_driver"})
            
        active_orders[uid] = {"driver_id": did, "price": str(price), "service": srv}
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"t_ok_{uid}")]])
        await bot.send_message(did, f"🔔 <b>ЗАКАЗ ПОТЕХИ:</b>\n🎭 {srv}\n💰 {price} руб.", reply_markup=kb)
        await bot.send_message(uid, "⏳ <b>Гонец отправлен Ямщику...</b>")
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "details": str(e)})

# ==========================================
# 🤖 BOT LOGIC
# ==========================================
class DriverReg(StatesGroup): fio=State(); car=State(); pay=State(); ref=State(); code=State()
class Unlock(StatesGroup): key=State()
class AdminPromo(StatesGroup): code=State(); comm=State(); dur=State()
class ChatWithBoss(StatesGroup): active=State()
class DriverEdit(StatesGroup): new_pay=State(); new_code=State()
class AddCustomService(StatesGroup): name=State(); desc=State(); price=State(); cat=State()

# СТАРТ
@dp.message(Command("start"))
async def start(message: types.Message):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO clients (user_id, trips_count) VALUES (?, 0)", (message.from_user.id,))
    conn.commit(); conn.close()
    
    web_url = APP_URL if APP_URL else "https://google.com"
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎭 Выбрать Потеху (Mini App)", web_app=WebAppInfo(url=web_url))],
        [KeyboardButton(text="👤 Моя Светлица"), KeyboardButton(text="🔑 Ввести код Ямщика")],
        [KeyboardButton(text="⚖️ Казённый Стряпчий")]
    ], resize_keyboard=True)
    await message.answer(WELCOME_TEXT, reply_markup=kb)

# ЕДИНЫЙ ХЕНДЛЕР КАБИНЕТА (ФИКС)
@dp.message(F.text == "👤 Моя Светлица")
@dp.message(Command("cab"))
async def cabinet_handler(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    
    # 1. Проверяем, Водитель ли это
    drv = get_driver_info(uid)
    if drv:
        check_and_reset_promo(uid)
        drv = get_driver_info(uid) # Обновляем
        
        kb = [
            [InlineKeyboardButton(text="🎛 Мой Репертуар", callback_data="driver_menu_edit")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="driver_settings"), InlineKeyboardButton(text="📊 История", callback_data="driver_history")],
            [InlineKeyboardButton(text="🤝 Реферальная программа", callback_data="driver_referral")],
            [InlineKeyboardButton(text="🆘 Чат с Продюсером", callback_data="chat_with_boss")]
        ]
        kb.append([InlineKeyboardButton(text="💎 Мой VIP-код", callback_data="show_vip_code")])
        
        status_txt = "📴 Свободен"
        # Ищем активный заказ
        for cid, order in active_orders.items():
            if order.get('driver_id') == uid:
                status_txt = f"🎬 <b>В ДЕЛЕ (Клиент {cid})</b>"
                kb.insert(0, [InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ", callback_data=f"pay_ok_{cid}")])
                break
        
        promo_txt = f" (Промо до {drv[12]})" if drv[12] else ""
        await message.answer(f"🪪 <b>ГРИМЕРКА ЯМЩИКА: {drv[7]}</b>\n💰 Долг: {drv[3]}₽\n🔑 Код: <code>{drv[5]}</code>\n📉 Комиссия: <b>{drv[11]}%</b>{promo_txt}\n━━━━━━━━━━━━\n{status_txt}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    # 2. Если не водитель - показываем кабинет Клиента
    cli = get_client_info(uid)
    if cli:
        # (spent, trips, vip, driver_id)
        status = "👹 ЦАРСКИЙ (VIP)" if cli[2] or cli[1] >= VIP_LIMIT else "👶 ЗРИТЕЛЬ"
        progress = "" if "VIP" in status else f"\n🔓 До VIP: <b>{VIP_LIMIT - cli[1]} поездок</b>"
        
        conn = sqlite3.connect(DB_PATH)
        hist = conn.execute("SELECT service_name, price FROM order_history WHERE client_id=? ORDER BY id DESC LIMIT 5", (uid,)).fetchall()
        conn.close()
        h_txt = "\n".join([f"▪ {h[0]} ({h[1]}₽)" for h in hist]) or "Нет истории."
        
        await message.answer(f"👤 <b>СВЕТЛИЦА БОЯРИНА</b>\n👑 Статус: {status}\n💰 Потрачено: {cli[0]}₽ | 🎬 Поездок: {cli[1]}{progress}\n\n📜 <b>Былые потехи:</b>\n{h_txt}")
    else:
        await message.answer("Странно, но вас нет в списках. Нажмите /start")

# ВВОД КОДА
@dp.message(F.text == "🔑 Ввести код Ямщика")
async def enter_code_btn(message: types.Message, state: FSMContext):
    await message.answer("Введи тайный код Ямщика:")
    await state.set_state(Unlock.key)

@dp.message(Unlock.key)
async def check_key(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    conn = sqlite3.connect(DB_PATH)
    drv = conn.execute("SELECT user_id, fio FROM drivers WHERE access_code=? AND status='active'", (code,)).fetchone()
    
    if drv:
        set_linked_driver(message.from_user.id, drv[0])
        await message.answer(f"🔓 <b>Связь установлена!</b>\nТвой ямщик: {drv[1]}\nТеперь можно заказывать потехи.", reply_markup=None)
    else:
        # Проверка VIP кода
        vip_drv = conn.execute("SELECT user_id, fio FROM drivers WHERE vip_code=? AND status='active'", (code,)).fetchone()
        if vip_drv:
            set_linked_driver(message.from_user.id, vip_drv[0])
            conn.execute("UPDATE clients SET vip_unlocked=1 WHERE user_id=?", (message.from_user.id,))
            conn.commit()
            await message.answer(f"💎 <b>VIP АКТИВИРОВАН!</b>\nЯмщик: {vip_drv[1]}\nВам доступны Царские потехи.", reply_markup=None)
        else:
            await message.answer("❌ Нет такого ямщика.")
    conn.close()
    await state.clear()

# ЗАКАЗ
@dp.callback_query(F.data.startswith("t_ok_"))
async def order_accept(callback: types.CallbackQuery):
    cid = int(callback.data.split("_")[2])
    o = active_orders.get(cid)
    if not o: return await callback.answer("Уже не актуально")
    
    await callback.message.edit_text(f"✅ <b>В работе!</b>\nПотеха: {o['service']}")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 ПОЛУЧИЛ МЗДУ", callback_data=f"pay_ok_{cid}")]])
    await callback.message.answer("Как выполнишь — жми:", reply_markup=kb)
    await bot.send_message(cid, f"✅ <b>Ямщик согласился!</b>\nГотовьте {o['price']} руб.")

@dp.callback_query(F.data.startswith("pay_ok_"))
async def pay_ok(callback: types.CallbackQuery):
    cid = int(callback.data.split("_")[2])
    # Сохраняем историю
    o = active_orders.get(cid)
    if o:
        did = o['driver_id']
        price = int(float(o['price']))
        
        conn = sqlite3.connect(DB_PATH)
        # Обновляем клиента
        conn.execute("UPDATE clients SET total_spent = total_spent + ?, trips_count = trips_count + 1 WHERE user_id=?", (price, cid))
        # История
        conn.execute("INSERT INTO order_history (client_id, driver_id, service_name, price) VALUES (?, ?, ?, ?)", (cid, did, o['service'], price))
        # Комиссия водителя
        d_info = conn.execute("SELECT commission FROM drivers WHERE user_id=?", (did,)).fetchone()
        comm = int(price * (d_info[0] / 100))
        conn.execute("UPDATE drivers SET balance = balance + ?, rating_count = rating_count + 1, rating_sum = rating_sum + 5 WHERE user_id=?", (comm, did))
        conn.commit(); conn.close()
        
        del active_orders[cid]

    await callback.message.edit_text("💰 <b>Мзда получена!</b>")
    await bot.send_message(cid, "🙏 Благодарим за щедрость! Ждем снова.")

# РЕГИСТРАЦИЯ
@dp.message(Command("drive"))
async def reg_start(message: types.Message, state: FSMContext):
    if get_driver_info(message.from_user.id): return await message.answer("Уже в артели. Жми /cab")
    await message.answer("Как звать-величать? (ФИО)")
    await state.set_state(DriverReg.fio)

@dp.message(DriverReg.fio)
async def reg_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await message.answer("На чём скачешь? (Авто)")
    await state.set_state(DriverReg.car)

@dp.message(DriverReg.car)
async def reg_car(message: types.Message, state: FSMContext):
    await state.update_data(car=message.text)
    await message.answer("Куда монету слать? (Реквизиты)")
    await state.set_state(DriverReg.pay)

@dp.message(DriverReg.pay)
async def reg_pay(message: types.Message, state: FSMContext):
    await state.update_data(pay=message.text)
    await message.answer("Код приглашения (если есть):")
    await state.set_state(DriverReg.ref)

@dp.message(DriverReg.ref)
async def reg_ref(message: types.Message, state: FSMContext):
    ref_txt = message.text.strip().upper() if len(message.text) > 2 else None
    await state.update_data(ref=ref_txt)
    await message.answer("Придумай свой Код-Пароль (ENGLISH):")
    await state.set_state(DriverReg.code)

@dp.message(DriverReg.code)
async def reg_code(message: types.Message, state: FSMContext):
    code = message.text.upper().strip()
    data = await state.get_data()
    
    conn = sqlite3.connect(DB_PATH)
    if conn.execute("SELECT 1 FROM drivers WHERE access_code=?", (code,)).fetchone():
        conn.close(); return await message.answer("❌ Занят код, другой давай!")
    
    comm = DEFAULT_COMMISSION
    ref_id = None
    end_date = None
    
    if data['ref']:
        promo = conn.execute("SELECT commission, duration FROM promo_codes WHERE code=?", (data['ref'],)).fetchone()
        if promo:
            comm = promo[0]
            end_date = datetime.now() + timedelta(days=promo[1])
        else:
            inviter = conn.execute("SELECT user_id, commission FROM drivers WHERE access_code=?", (data['ref'],)).fetchone()
            if inviter:
                ref_id = inviter[0]
                comm = 5 # 5% новичку
                # Бонус другу
                new_c = max(MIN_COMMISSION, inviter[1] - 1)
                conn.execute("UPDATE drivers SET commission=? WHERE user_id=?", (new_c, ref_id))
                await safe_send(ref_id, f"🎉 Друг пришел! Твоя комиссия: {new_c}%")

    vip = generate_vip_code(data['fio'])
    conn.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, vip_code, commission, referred_by, promo_end_date, status) VALUES (?,?,?,?,?,?,?,?,?,?, 'pending')",
                 (message.from_user.id, message.from_user.username, data['fio'], data['car'], data['pay'], code, vip, comm, ref_id, end_date))
    conn.commit(); conn.close()
    
    await message.answer(f"✅ <b>Заявка принята!</b>\nКомиссия: {comm}%\nКод: {code}")
    await safe_send(OWNER_ID, f"🚨 <b>НОВЫЙ ЯМЩИК:</b> {data['fio']}", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"adm_ok_{message.from_user.id}")]]))
    await state.clear()

@dp.callback_query(F.data.startswith("adm_ok_"))
async def adm_ok(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    did = int(callback.data.split("_")[2])
    conn = sqlite3.connect(DB_PATH); conn.execute("UPDATE drivers SET status='active' WHERE user_id=?", (did,)); conn.commit(); conn.close()
    await safe_send(did, "✅ <b>ВАС ПРИНЯЛИ В АРТЕЛЬ!</b>\nЖмите /cab")
    await callback.message.edit_text("✅ Принят.")

# --- УПРАВЛЕНИЕ МЕНЮ И НАСТРОЙКИ (Драйвер) ---
@dp.callback_query(F.data == "driver_menu_edit")
async def driver_menu(callback: types.CallbackQuery):
    act, customs = get_driver_menu(callback.from_user.id)
    kb = []
    for k, v in CRAZY_SERVICES.items():
        st = "✅" if k in act else "❌"
        kb.append([InlineKeyboardButton(text=f"{st} {v['name']}", callback_data=f"tgl_{k}")])
    for c in customs:
        kb.append([InlineKeyboardButton(text=f"🗑 {c[2]}", callback_data=f"del_{c[0]}")])
    kb.append([InlineKeyboardButton(text="➕ Своя потеха", callback_data="add_custom")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_cab")])
    await callback.message.edit_text("🎛 <b>РЕПЕРТУАР:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("tgl_"))
async def toggle_srv(callback: types.CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    key = callback.data.split("_")[1]
    curr = conn.execute("SELECT is_active FROM driver_services WHERE driver_id=? AND service_key=?", (callback.from_user.id, key)).fetchone()
    new_s = 0 if (curr and curr[0]) else 1
    conn.execute("INSERT OR REPLACE INTO driver_services (driver_id, service_key, is_active) VALUES (?, ?, ?)", (callback.from_user.id, key, new_s))
    conn.commit(); conn.close()
    await driver_menu(callback)

@dp.callback_query(F.data == "add_custom")
async def add_cust_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Название услуги:")
    await state.set_state(AddCustomService.name)

@dp.message(AddCustomService.name)
async def add_cust_n(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text); await message.answer("Описание:")
    await state.set_state(AddCustomService.desc)

@dp.message(AddCustomService.desc)
async def add_cust_d(message: types.Message, state: FSMContext):
    await state.update_data(desc=message.text); await message.answer("Цена (число):")
    await state.set_state(AddCustomService.price)

@dp.message(AddCustomService.price)
async def add_cust_p(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    d = await state.get_data()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO custom_services (driver_id, category_id, name, description, price) VALUES (?, 1, ?, ?, ?)", (message.from_user.id, d['name'], d['desc'], int(message.text)))
    conn.commit(); conn.close()
    await message.answer("✅ Добавлено!")
    await state.clear()

@dp.callback_query(F.data.startswith("del_"))
async def del_cust(callback: types.CallbackQuery):
    cid = int(callback.data.split("_")[1])
    conn = sqlite3.connect(DB_PATH); conn.execute("DELETE FROM custom_services WHERE id=?", (cid,)); conn.commit(); conn.close()
    await driver_menu(callback)

@dp.callback_query(F.data == "back_cab")
async def back_cab(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await cabinet_handler(callback.message, state)

@dp.callback_query(F.data == "driver_referral")
async def show_ref(callback: types.CallbackQuery):
    i = get_driver_info(callback.from_user.id)
    await callback.message.answer(f"Код для друзей: <code>{i[5]}</code>\nПриведи друга - снизь комиссию!")
    await callback.answer()

@dp.callback_query(F.data == "show_vip_code")
async def show_vip(callback: types.CallbackQuery):
    i = get_driver_info(callback.from_user.id)
    await callback.message.answer(f"VIP код для клиентов: <code>{i[10]}</code>")
    await callback.answer()

# АДМИНКА
@dp.message(Command("admin"))
async def admin_p(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await message.answer("Админка", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎟 Создать Промо", callback_data="mk_promo")]]))

@dp.callback_query(F.data == "mk_promo")
async def mk_promo(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Код:")
    await state.set_state(AdminPromo.code)

@dp.message(AdminPromo.code)
async def pr_c(message: types.Message, state: FSMContext):
    await state.update_data(c=message.text); await message.answer("Комиссия (%):")
    await state.set_state(AdminPromo.comm)

@dp.message(AdminPromo.comm)
async def pr_cm(message: types.Message, state: FSMContext):
    await state.update_data(cm=int(message.text)); await message.answer("Дней:")
    await state.set_state(AdminPromo.dur)

@dp.message(AdminPromo.dur)
async def pr_d(message: types.Message, state: FSMContext):
    d = await state.get_data()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO promo_codes VALUES (?, ?, ?)", (d['c'], d['cm'], int(message.text)))
    conn.commit(); conn.close()
    await message.answer("✅ Промо создано"); await state.clear()

# ==========================================
# 🚀 ЗАПУСК
# ==========================================
async def on_startup(app):
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))

def main():
    app = web.Application()
    app.router.add_get('/', web_main_handler)
    app.router.add_post('/webapp_order', web_order_handler)
    app.on_startup.append(on_startup)
    web.run_app(app, host='0.0.0.0', port=8080)

if __name__ == "__main__":
    main()
