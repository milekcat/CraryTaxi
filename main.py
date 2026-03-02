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
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ==========================================
# ⚙️ НАСТРОЙКИ
# ==========================================
logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("API_TOKEN")
OWNER_ID_STR = os.getenv("DRIVER_ID")
APP_URL = os.getenv("APP_URL")  # Ссылка на приложение в Amvera

if not API_TOKEN or not OWNER_ID_STR:
    exit("⛔ CRITICAL ERROR: Token or ID missing")

OWNER_ID = int(OWNER_ID_STR)
SUPER_ADMINS = [OWNER_ID]

VIP_LIMIT = 10 
MIN_COMMISSION = 4 
DEFAULT_COMMISSION = 10 
LAWYER_LINK = "https://t.me/Ai_advokatrobot"

# Настройки сервера
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = 8080

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

active_orders = {} 

# ==========================================
# 📜 ТЕКСТЫ "ВЕСЁЛЫЙ ИЗВОЗЧИК"
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

# ==========================================
# 🗄️ БАЗА ДАННЫХ
# ==========================================
DB_PATH = "/data/taxi_db.sqlite" if os.path.exists("/data") else "taxi_db.sqlite"

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
    cursor.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER DEFAULT NULL, total_spent INTEGER DEFAULT 0, trips_count INTEGER DEFAULT 0, vip_unlocked BOOLEAN DEFAULT 0)")
    cursor.execute("CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, commission INTEGER, duration INTEGER)")
    cursor.execute("CREATE TABLE IF NOT EXISTS order_history (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, driver_id INTEGER, service_name TEXT, price INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    
    # Админ
    cursor.execute("INSERT OR IGNORE INTO drivers (user_id, username, fio, car_info, payment_info, access_code, vip_code, status, role) VALUES (?, 'BOSS', 'Староста', 'Карета', 'CASH', ?, ?, 'active', 'owner')", (OWNER_ID, f"ADMIN_{OWNER_ID}", f"VIP_{OWNER_ID}"))
    cursor.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (OWNER_ID,))
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 🛠 УТИЛИТЫ
# ==========================================
def generate_vip_code(name):
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"BOYAR-{name.split()[0].upper()}-{suffix}"

def get_driver_info(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT username, car_info, payment_info, balance, status, access_code, role, fio, rating_sum, rating_count, vip_code, commission, promo_end_date FROM drivers WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return res

def is_admin(user_id):
    if user_id in SUPER_ADMINS: return True
    i = get_driver_info(user_id)
    return i and i[6] in ('owner', 'admin') and i[4] == 'active'

def get_active_drivers():
    conn = sqlite3.connect(DB_PATH)
    res = [d[0] for d in conn.execute("SELECT user_id FROM drivers WHERE status='active'").fetchall()]
    conn.close()
    return res

def set_linked_driver(client_id, driver_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO clients (user_id, linked_driver_id, total_spent, trips_count, vip_unlocked) VALUES (?, ?, (SELECT total_spent FROM clients WHERE user_id=?), (SELECT trips_count FROM clients WHERE user_id=?), (SELECT vip_unlocked FROM clients WHERE user_id=?))", (client_id, driver_id, client_id, client_id, client_id))
    conn.commit(); conn.close()

def get_linked_driver(client_id):
    conn = sqlite3.connect(DB_PATH); res = conn.execute("SELECT linked_driver_id FROM clients WHERE user_id=?", (client_id,)).fetchone(); conn.close()
    return res[0] if res else None

async def safe_send(chat_id, text, kb=None):
    try: await bot.send_message(chat_id, text, reply_markup=kb); return True
    except: return False

# ==========================================
# 📡 WEB SERVER (ДЛЯ МИНИ-АППА)
# ==========================================
async def web_main_handler(request):
    with open('index.html', 'r', encoding='utf-8') as f:
        return web.Response(text=f.read(), content_type='text/html')

async def web_order_handler(request):
    data = await request.json()
    uid = data.get('user_id')
    srv = data.get('service')
    price = data.get('price')
    
    # Логика заказа
    did = get_linked_driver(uid)
    if not did:
        await bot.send_message(uid, "🚫 <b>Сначала введите код Ямщика!</b>\nНажмите /start -> Найти Ямщика")
        return web.json_response({"status": "error"})
        
    active_orders[uid] = {"driver_id": did, "price": str(price), "service": srv, "status": "pending"}
    
    # Уведомляем водителя
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"t_ok_{uid}")]])
    await bot.send_message(did, f"🔔 <b>ЗАКАЗ ПОТЕХИ:</b>\n🎭 {srv}\n💰 {price} руб.", reply_markup=kb)
    
    await bot.send_message(uid, "⏳ <b>Гонец отправлен Ямщику...</b>")
    return web.json_response({"status": "ok"})

# ==========================================
# 🤖 BOT LOGIC
# ==========================================
class DriverReg(StatesGroup): fio=State(); car=State(); pay=State(); ref=State(); code=State()
class Unlock(StatesGroup): key=State()
class AdminPromo(StatesGroup): code=State(); comm=State(); dur=State()

# СТАРТ
@dp.message(Command("start"))
async def start(message: types.Message):
    # Главное меню с WebApp кнопкой
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎭 Выбрать Потеху (Mini App)", web_app=WebAppInfo(url=f"{APP_URL}"))],
        [KeyboardButton(text="👤 Моя Светлица"), KeyboardButton(text="🚖 Ввести код Ямщика")],
        [KeyboardButton(text="⚖️ Казённый Стряпчий")]
    ], resize_keyboard=True)
    
    await message.answer(WELCOME_TEXT, reply_markup=kb)

# ВВОД КОДА
@dp.message(F.text == "🚖 Ввести код Ямщика")
async def enter_code_btn(message: types.Message, state: FSMContext):
    await message.answer("Введи тайный код Ямщика:")
    await state.set_state(Unlock.key)

@dp.message(Unlock.key)
async def check_key(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    conn = sqlite3.connect(DB_PATH)
    drv = conn.execute("SELECT user_id, fio FROM drivers WHERE access_code=? AND status='active'", (code,)).fetchone()
    conn.close()
    
    if drv:
        set_linked_driver(message.from_user.id, drv[0])
        await message.answer(f"🔓 <b>Связь установлена!</b>\nТвой ямщик: {drv[1]}\nТеперь можно заказывать потехи через кнопку меню.", reply_markup=None)
    else:
        await message.answer("❌ Нет такого ямщика.")
    await state.clear()

# ОБРАБОТКА ЗАКАЗА (Водитель принял)
@dp.callback_query(F.data.startswith("t_ok_"))
async def order_accept(callback: types.CallbackQuery, state: FSMContext):
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
    await callback.message.edit_text("💰 <b>Мзда получена!</b>")
    await bot.send_message(cid, "🙏 Благодарим за щедрость!")
    if cid in active_orders: del active_orders[cid]

# РЕГИСТРАЦИЯ ВОДИТЕЛЯ
@dp.message(Command("drive"))
async def reg_start(message: types.Message, state: FSMContext):
    if get_driver_info(message.from_user.id): return await message.answer("Уже в артели.")
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
    await state.update_data(ref=message.text if len(message.text) > 2 else None)
    await message.answer("Придумай свой Код-Пароль (ENGLISH):")
    await state.set_state(DriverReg.code)

@dp.message(DriverReg.code)
async def reg_code(message: types.Message, state: FSMContext):
    code = message.text.upper().strip()
    data = await state.get_data()
    
    conn = sqlite3.connect(DB_PATH)
    if conn.execute("SELECT 1 FROM drivers WHERE access_code=?", (code,)).fetchone():
        conn.close(); return await message.answer("❌ Занят код, другой давай!")
    
    # Логика рефералки/промо
    comm = DEFAULT_COMMISSION
    ref_id = None
    if data['ref']:
        # Проверка админ-промо
        promo = conn.execute("SELECT commission, duration FROM promo_codes WHERE code=?", (data['ref'].upper(),)).fetchone()
        if promo:
            comm = promo[0] # Применяем промо-комиссию
        else:
            # Проверка друга
            inviter = conn.execute("SELECT user_id, commission FROM drivers WHERE access_code=?", (data['ref'].upper(),)).fetchone()
            if inviter:
                ref_id = inviter[0]
                comm = 5 # Льгота новичку
                # Бонус другу
                new_c = max(MIN_COMMISSION, inviter[1] - 1)
                conn.execute("UPDATE drivers SET commission=? WHERE user_id=?", (new_c, ref_id))
                await safe_send(ref_id, f"🎉 Друг пришел! Твоя комиссия: {new_c}%")

    vip = generate_vip_code(data['fio'])
    conn.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, vip_code, commission, referred_by, status) VALUES (?,?,?,?,?,?,?,?,?, 'pending')",
                 (message.from_user.id, message.from_user.username, data['fio'], data['car'], data['pay'], code, vip, comm, ref_id))
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ <b>Заявка принята!</b>\nКомиссия: {comm}%\nКод: {code}")
    await safe_send(OWNER_ID, f"🚨 <b>НОВЫЙ ЯМЩИК:</b> {data['fio']}", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"adm_ok_{message.from_user.id}")]]))
    await state.clear()

# АДМИНКА
@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await message.answer("👑 <b>УПРАВЛЕНИЕ АРТЕЛЬЮ</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎟 Создать Промокод", callback_data="add_promo")]]))

@dp.callback_query(F.data == "add_promo")
async def add_promo(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Код (напр. SUMMER):")
    await state.set_state(AdminPromo.code)

@dp.message(AdminPromo.code)
async def promo_code(message: types.Message, state: FSMContext):
    await state.update_data(c=message.text.upper())
    await message.answer("Процент комиссии:")
    await state.set_state(AdminPromo.comm)

@dp.message(AdminPromo.comm)
async def promo_comm(message: types.Message, state: FSMContext):
    await state.update_data(p=int(message.text))
    await message.answer("Дней действия:")
    await state.set_state(AdminPromo.dur)

@dp.message(AdminPromo.dur)
async def promo_fin(message: types.Message, state: FSMContext):
    d = await state.get_data()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO promo_codes (code, commission, duration) VALUES (?, ?, ?)", (d['c'], d['p'], int(message.text)))
    conn.commit()
    conn.close()
    await message.answer("✅ Промокод создан!")
    await state.clear()

@dp.callback_query(F.data.startswith("adm_ok_"))
async def adm_ok(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    did = int(callback.data.split("_")[2])
    conn = sqlite3.connect(DB_PATH); conn.execute("UPDATE drivers SET status='active' WHERE user_id=?", (did,)); conn.commit(); conn.close()
    await safe_send(did, "✅ <b>ВАС ПРИНЯЛИ В АРТЕЛЬ!</b>\nЖмите /cab")
    await callback.message.edit_text("✅ Принят.")

# КАБИНЕТ
@dp.message(Command("cab"))
async def my_cab(message: types.Message):
    i = get_driver_info(message.from_user.id)
    if not i: return await message.answer("Нет прав. /drive")
    await message.answer(f"🪪 <b>ГРИМЕРКА: {i[7]}</b>\n💰 Долг: {i[3]}₽\n📉 Комиссия: {i[11]}%")

# ==========================================
# 🚀 ЗАПУСК СЕРВЕРА И БОТА
# ==========================================
async def on_startup(app):
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))

def main():
    app = web.Application()
    app.router.add_get('/', web_main_handler) # Отдает HTML
    app.router.add_post('/webapp_order', web_order_handler) # Принимает заказы из JS
    app.on_startup.append(on_startup)
    
    # Запуск сервера
    web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)

if __name__ == "__main__":
    main()
