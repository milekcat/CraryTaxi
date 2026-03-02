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

# --- ПОЛНЫЙ ПЕРЕЧЕНЬ УСЛУГ ---
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
# 📡 WEB API
# ==========================================
async def get_services(request):
    uid = int(request.query.get('user_id', 0))
    with sqlite3.connect(DB_PATH) as con:
        # ПРОВЕРКА: Если водитель не привязан, возвращаем ошибку
        cli = con.execute("SELECT linked_driver_id FROM clients WHERE user_id=?", (uid,)).fetchone()
        if not cli or not cli[0]: return web.json_response({"error": "no_driver"})
        
        did = cli[0]
        customs = con.execute("SELECT name, description, price FROM custom_services WHERE driver_id=?", (did,)).fetchall()
    
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
    
    # ПРОВЕРКА: Нельзя заказать, если нет связи
    if not cli or not cli[0]: return web.json_response({"status": "no_driver"})
    
    active_orders[uid] = {"driver_id": cli[0]} 
    map_url = f"https://www.google.com/maps?q={lat},{lon}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"ok_{uid}"),
         InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"fin_{uid}")]
    ])
    await bot.send_message(cli[0], f"🔔 <b>ЗАКАЗ!</b>\n🎭 {srv}\n💰 {price}₽\n📍 <a href='{map_url}'>МЕСТО ВСТРЕЧИ</a>", reply_markup=kb)
    return web.json_response({"status": "ok"})

# ==========================================
# 🤖 BOT LOGIC
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
    await m.answer("Введите код:"); await state.set_state("waiting_code")

# --- ВЕРИФИКАЦИЯ ПАССАЖИРА ---
@dp.message(F.state == "waiting_code")
async def process_code(m: types.Message, state: FSMContext):
    code = m.text.strip().upper()
    with sqlite3.connect(DB_PATH) as con:
        drv = con.execute("SELECT user_id, fio FROM drivers WHERE access_code=? AND status='active'", (code,)).fetchone()
    
    if drv:
        # Не привязываем сразу! Спрашиваем водителя.
        did, name = drv[0], drv[1]
        
        # Кнопки для водителя
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ДА, МОЙ ПАССАЖИР", callback_data=f"pass_yes_{m.from_user.id}"),
             InlineKeyboardButton(text="⛔ ГНАТЬ В ШЕЮ", callback_data=f"pass_no_{m.from_user.id}")]
        ])
        
        # Шлем запрос водителю
        username = f"@{m.from_user.username}" if m.from_user.username else "Без ника"
        await safe_send(did, f"🚨 <b>ПРОВЕРКА!</b>\nПассажир {m.from_user.full_name} ({username}) ввел ваш код.\n\nОн действительно у вас в машине?", kb)
        
        # Отвечаем пассажиру
        await m.answer(f"⏳ <b>Ожидаем подтверждения...</b>\nЯмщик {name} получил запрос. Он должен подтвердить, что вы действительно находитесь в карете.")
    else:
        await m.answer("❌ Код не найден.")
    await state.clear()

# ВОДИТЕЛЬ ПОДТВЕРДИЛ
@dp.callback_query(F.data.startswith("pass_yes_"))
async def pass_confirm(call: types.CallbackQuery):
    client_id = int(call.data.split("_")[2])
    driver_id = call.from_user.id
    
    with sqlite3.connect(DB_PATH) as con:
        con.execute("UPDATE clients SET linked_driver_id=? WHERE user_id=?", (driver_id, client_id))
    
    await call.message.edit_text(f"✅ <b>Пассажир подтвержден!</b>\nЕму открыт доступ к меню услуг.")
    await safe_send(client_id, "🎉 <b>Доступ открыт!</b>\nЯмщик подтвердил посадку. Теперь вы можете заказывать услуги в приложении.")

# ВОДИТЕЛЬ ОТКЛОНИЛ
@dp.callback_query(F.data.startswith("pass_no_"))
async def pass_reject(call: types.CallbackQuery):
    client_id = int(call.data.split("_")[2])
    await call.message.edit_text(f"⛔ <b>В доступе отказано.</b>")
    await safe_send(client_id, "🚫 <b>Отказ!</b>\nЯмщик сообщил, что вас нет в машине. Доступ к услугам заблокирован.")

# --- ЗАВЕРШЕНИЕ ПОЕЗДКИ И РАЗРЫВ СВЯЗИ ---
@dp.callback_query(F.data.startswith("fin_"))
async def finish_order(call: types.CallbackQuery):
    client_id = int(call.data.split("_")[1])
    with sqlite3.connect(DB_PATH) as con:
        con.execute("UPDATE clients SET linked_driver_id=NULL WHERE user_id=?", (client_id,))
    if client_id in active_orders: del active_orders[client_id]
    await call.message.edit_text("🏁 <b>ПОЕЗДКА ЗАВЕРШЕНА</b>\nПассажир высажен, связь разорвана.")
    await safe_send(client_id, "👋 <b>Поездка окончена!</b>\nДля нового заказа введите код Ямщика заново.")

@dp.callback_query(F.data.startswith("ok_"))
async def accept_order(call: types.CallbackQuery):
    cid = int(call.data.split("_")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ ПОЕЗДКУ", callback_data=f"fin_{cid}")]])
    await call.message.edit_text(f"✅ <b>ВЫ В ПУТИ!</b>\n{call.message.html_text.splitlines()[1]}", reply_markup=kb)
    await safe_send(cid, "🚀 <b>Ямщик принял заказ!</b> Мчит к вам!")

# --- РЕГИСТРАЦИЯ ВОДИТЕЛЯ ---
@dp.message(Command("drive"))
async def reg_start(m: types.Message, state: FSMContext):
    if get_driver(m.from_user.id): return await m.answer("Вы уже в системе.")
    await m.answer("<b>АНКЕТА КАНДИДАТА</b>\nВаше ФИО:"); await state.set_state(DriverReg.fio)

@dp.message(DriverReg.fio)
async def reg_fio(m: types.Message, state: FSMContext):
    await state.update_data(fio=m.text); await m.answer("Марка и госномер авто:"); await state.set_state(DriverReg.car)

@dp.message(DriverReg.car)
async def reg_car(m: types.Message, state: FSMContext):
    await state.update_data(car=m.text); await m.answer("Реквизиты:"); await state.set_state(DriverReg.pay)

@dp.message(DriverReg.pay)
async def reg_pay(m: types.Message, state: FSMContext):
    await state.update_data(pay=m.text); await m.answer("Придумайте секретный код (латиница):"); await state.set_state(DriverReg.code)

@dp.message(DriverReg.code)
async def reg_fin(m: types.Message, state: FSMContext):
    d = await state.get_data(); code = m.text.strip().upper()
    try:
        with sqlite3.connect(DB_PATH) as con:
            con.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status) VALUES (?,?,?,?,?,?, 'pending')",
                        (m.from_user.id, m.from_user.username, d['fio'], d['car'], d['pay'], code))
        await m.answer("📜 <b>Заявка подана!</b> Ждите решения Старосты.")
        await safe_send(OWNER_ID, f"🔔 <b>НОВАЯ ЗАЯВКА!</b>\n{d['fio']} (Code: {code})\nПроверь кабинет.")
    except: await m.answer("❌ Код занят.")
    await state.clear()

# --- АДМИНКА ---
@dp.message(F.text == "👤 Моя Светлица")
async def cabinet(m: types.Message):
    uid = m.from_user.id
    if uid == OWNER_ID:
        kb = [[InlineKeyboardButton(text="📥 Заявки", callback_data="adm_requests")], [InlineKeyboardButton(text="📋 Ямщики", callback_data="adm_list")]]
        return await m.answer("👑 <b>КАБИНЕТ СТАРОСТЫ</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    with sqlite3.connect(DB_PATH) as con: drv = con.execute("SELECT status, fio, access_code FROM drivers WHERE user_id=?", (uid,)).fetchone()
    if drv and drv[0] == 'active':
        kb = [[InlineKeyboardButton(text="➕ Своя услуга", callback_data="add_custom")]]
        return await m.answer(f"🪪 <b>ЯМЩИК: {drv[1]}</b>\n🔑 Код: {drv[2]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await m.answer("👤 <b>КАБИНЕТ ПАССАЖИРА</b>")

@dp.callback_query(F.data == "adm_requests")
async def adm_requests(call: types.CallbackQuery):
    with sqlite3.connect(DB_PATH) as con: reqs = con.execute("SELECT user_id, fio, car_info FROM drivers WHERE status='pending'").fetchall()
    if not reqs: return await call.message.answer("Заявок нет.")
    for r in reqs:
        kb = [[InlineKeyboardButton(text="✅ Принять", callback_data=f"appr_{r[0]}"), InlineKeyboardButton(text="❌ Отказ", callback_data=f"reje_{r[0]}")]]
        await call.message.answer(f"📝 {r[1]} | {r[2]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("appr_"))
async def approve(call: types.CallbackQuery):
    did = call.data.split("_")[1]
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE drivers SET status='active' WHERE user_id=?", (did,))
    await call.answer("Принят!"); await safe_send(did, "🎉 Вы приняты в Артель!")

@dp.callback_query(F.data.startswith("reje_"))
async def reject(call: types.CallbackQuery):
    did = call.data.split("_")[1]
    with sqlite3.connect(DB_PATH) as con: con.execute("DELETE FROM drivers WHERE user_id=?", (did,))
    await call.answer("Удален"); await safe_send(did, "❌ Отказ.")

# --- УТИЛИТЫ ---
def get_driver(uid):
    with sqlite3.connect(DB_PATH) as con: return con.execute("SELECT * FROM drivers WHERE user_id=?", (uid,)).fetchone()

async def safe_send(chat_id, text, kb=None):
    try: await bot.send_message(chat_id, text, reply_markup=kb); return True
    except: return False

# --- СВОЯ УСЛУГА ---
@dp.callback_query(F.data == "add_custom")
async def add_custom(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Название:"); await state.set_state(CustomSrv.name)
@dp.message(CustomSrv.name)
async def custom_name(m: types.Message, state: FSMContext):
    await state.update_data(name=m.text); await m.answer("Описание:"); await state.set_state(CustomSrv.desc)
@dp.message(CustomSrv.desc)
async def custom_desc(m: types.Message, state: FSMContext):
    await state.update_data(desc=m.text); await m.answer("Цена:"); await state.set_state(CustomSrv.price)
@dp.message(CustomSrv.price)
async def custom_price(m: types.Message, state: FSMContext):
    if not m.text.isdigit(): return await m.answer("Числом!")
    d = await state.get_data()
    with sqlite3.connect(DB_PATH) as con: con.execute("INSERT INTO custom_services (driver_id, name, description, price) VALUES (?, ?, ?, ?)", (m.from_user.id, d['name'], d['desc'], int(m.text)))
    await m.answer("✅ Добавлено!"); await state.clear()

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
