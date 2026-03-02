import asyncio
import logging
import os
import sqlite3
import json
from datetime import datetime
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

# Списки активных данных
active_orders = {}   # Текущие поездки (привязанные)
market_orders = {}   # Биржа (свободные заказы)

# ==========================================
# 📜 ПОЛНЫЙ РЕПЕРТУАР (БЕЗ СОКРАЩЕНИЙ)
# ==========================================
CRAZY_SERVICES = {
    "candy": {"cat": "Малые", "name": "🍬 Сладкий гостинец", "desc": "Ямщик с поклоном вручает леденец на палочке.", "price": 100},
    "nose": {"cat": "Малые", "name": "👃 Перст в носу", "desc": "Ямщик всю дорогу демонстративно ковыряет в носу.", "price": 150},
    "butler": {"cat": "Малые", "name": "🤵 Дворецкий", "desc": "Открываем дверь, кланяемся, величаем Барином.", "price": 300},
    "joke": {"cat": "Малые", "name": "🤡 Скоморох", "desc": "Травим анекдоты. Смеяться обязательно, иначе обидимся.", "price": 200},
    "silence": {"cat": "Малые", "name": "🤐 Обет молчания", "desc": "Едем молча, как в монастыре. Ни слова за всю дорогу.", "price": 500},
    "granny": {"cat": "Средние", "name": "👵 Ворчливая бабка", "desc": "Ролевая игра: Куда прешь, окаянный! Наркоманы проклятые!", "price": 400},
    "gopnik": {"cat": "Средние", "name": "🍺 Разбойник", "desc": "Шансон, семки, решение вопросиков по телефону.", "price": 600},
    "guide": {"cat": "Средние", "name": "🗣 Горе-Гид", "desc": "Рассказываем небылицы о каждом столбе и доме.", "price": 350},
    "psych": {"cat": "Средние", "name": "🧠 Душеприказчик", "desc": "Выслушаем вашу кручину, дадим житейский совет.", "price": 1000},
    "spy": {"cat": "Большие", "name": "🕵️ Опричник (007)", "desc": "Тайная слежка, петляем по дворам, уходим от погони.", "price": 1500},
    "karaoke": {"cat": "Большие", "name": "🎤 Застольные песни", "desc": "Орем песни дуэтом на всю улицу. Репертуар широкий.", "price": 800},
    "dance": {"cat": "Большие", "name": "🐻 Медвежьи пляски", "desc": "Танцы на капоте на каждом светофоре.", "price": 1200},
    "kidnap": {"cat": "Дикие", "name": "🎭 Похищение", "desc": "Мешок на голову, в лес (понарошку), потом чай с баранками.", "price": 3000},
    "tarzan": {"cat": "Дикие", "name": "🦍 Леший", "desc": "Рычим на прохожих, пугаем девок, ездим по газонам.", "price": 2000},
    "burn": {"cat": "Дикие", "name": "🔥 Огненная колесница", "desc": "В конце поездки торжественно сжигаем повозку на пустыре.", "price": 50000},
    "eyes": {"cat": "Светские", "name": "👁️ Очи чёрные", "desc": "Изысканный комплимент вашим глазам.", "price": 50},
    "smile": {"cat": "Светские", "name": "😁 Улыбка", "desc": "Изысканный комплимент вашей улыбке.", "price": 50},
    "style": {"cat": "Светские", "name": "👠 Модный приговор", "desc": "Восхищение вашим нарядом и вкусом.", "price": 100},
    "improv": {"cat": "Светские", "name": "✨ Импровизация", "desc": "Ямщик сам придумает потеху на свой вкус.", "price": 500},
    "propose": {"cat": "Светские", "name": "💍 Сватовство", "desc": "Торжественное предложение руки и сердца вашей спутнице.", "price": 10000}
}

WELCOME_TEXT = (
    "🐎 <b>Здравия желаю, Барин!</b>\n\n"
    "Добро пожаловать в артель <b>«Весёлый Извозчик»</b>!\n"
    "У нас не просто телега с мотором, у нас — душа нараспашку.\n\n"
    "📜 <b>В программе:</b>\n"
    "• Ямщик-Психолог (выслушает кручину)\n"
    "• Пляски на тракте\n"
    "• Огненная потеха (сжигание повозки)\n\n"
    "<b>Куда путь держим?</b> 👇"
)

# ==========================================
# 🗄️ БАЗА ДАННЫХ
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS drivers (
        user_id INTEGER PRIMARY KEY, username TEXT, fio TEXT, car_info TEXT, payment_info TEXT, access_code TEXT UNIQUE, 
        status TEXT DEFAULT 'pending', role TEXT DEFAULT 'driver', balance INTEGER DEFAULT 0, lat REAL, lon REAL)""")
    
    cur.execute("PRAGMA table_info(drivers)")
    cols = [c[1] for c in cur.fetchall()]
    if 'username' not in cols: cur.execute("ALTER TABLE drivers ADD COLUMN username TEXT")
    if 'lat' not in cols: cur.execute("ALTER TABLE drivers ADD COLUMN lat REAL")
    if 'lon' not in cols: cur.execute("ALTER TABLE drivers ADD COLUMN lon REAL")

    cur.execute("CREATE TABLE IF NOT EXISTS custom_services (id INTEGER PRIMARY KEY AUTOINCREMENT, driver_id INTEGER, name TEXT, description TEXT, price INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER DEFAULT NULL)")
    
    cur.execute("INSERT OR IGNORE INTO drivers (user_id, fio, access_code, status, role) VALUES (?, 'СТАРОСТА', 'ADMIN', 'active', 'owner')", (OWNER_ID,))
    cur.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (OWNER_ID,))
    conn.commit(); conn.close()

init_db()

# ==========================================
# 📡 WEB API (АГРЕГАТОР + БИРЖА)
# ==========================================
async def get_services(request):
    uid = int(request.query.get('user_id', 0))
    with sqlite3.connect(DB_PATH) as con:
        # Проверяем привязку. Если нет - отдаем только стандартные (для заказа на биржу)
        cli = con.execute("SELECT linked_driver_id FROM clients WHERE user_id=?", (uid,)).fetchone()
        customs = []
        if cli and cli[0]:
            customs = con.execute("SELECT name, description, price FROM custom_services WHERE driver_id=?", (cli[0],)).fetchall()
    
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
    
    map_url = f"https://www.google.com/maps?q={lat},{lon}"
    
    # СЦЕНАРИЙ 1: Есть привязанный водитель
    if cli and cli[0]:
        did = cli[0]
        active_orders[uid] = {"driver_id": did}
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"ok_{uid}"),
             InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"fin_{uid}")]
        ])
        await bot.send_message(did, f"🔔 <b>ЛИЧНЫЙ ЗАКАЗ!</b>\n🎭 {srv}\n💰 {price}₽\n📍 <a href='{map_url}'>КАРТА</a>", reply_markup=kb)
        return web.json_response({"status": "ok"})
    
    # СЦЕНАРИЙ 2: БИРЖА (Нет водителя)
    else:
        order_id = f"m_{uid}_{int(datetime.now().timestamp())}"
        market_orders[order_id] = {"uid": uid, "srv": srv, "price": price, "lat": lat, "lon": lon, "map": map_url}
        
        # Уведомляем ВСЕХ активных водителей
        with sqlite3.connect(DB_PATH) as con:
            drivers = con.execute("SELECT user_id FROM drivers WHERE status='active' AND role!='owner'").fetchall()
        
        count = 0
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✋ ЗАБРАТЬ ЗАКАЗ", callback_data=f"take_{order_id}")]])
        for d in drivers:
            try:
                await bot.send_message(d[0], f"📥 <b>ЗАКАЗ НА БИРЖЕ!</b>\n🎭 {srv}\n💰 {price}₽\n📍 <a href='{map_url}'>КАРТА</a>", reply_markup=kb)
                count += 1
            except: pass
            
        if count > 0: return web.json_response({"status": "ok_market"})
        else: return web.json_response({"status": "no_active_drivers"})

# ==========================================
# 🤖 BOT HANDLERS (FSM)
# ==========================================
class DriverReg(StatesGroup): fio=State(); car=State(); pay=State(); code=State()
class AdminHR(StatesGroup): interview_text=State()
class AdminMsg(StatesGroup): text=State()
class CustomSrv(StatesGroup): name=State(); desc=State(); price=State()

# --- УТИЛИТЫ ---
def get_driver(uid):
    with sqlite3.connect(DB_PATH) as con: return con.execute("SELECT * FROM drivers WHERE user_id=?", (uid,)).fetchone()

async def safe_send(chat_id, text, kb=None):
    try: await bot.send_message(chat_id, text, reply_markup=kb); return True
    except: return False

@dp.message(Command("start"))
async def start(m: types.Message):
    with sqlite3.connect(DB_PATH) as con: con.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (m.from_user.id,))
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🚖 ЗАКАЗАТЬ ПОТЕХУ", web_app=WebAppInfo(url=APP_URL))],
                                       [KeyboardButton(text="👤 Моя Светлица"), KeyboardButton(text="🔑 Код Ямщика")]], resize_keyboard=True)
    await m.answer(WELCOME_TEXT, reply_markup=kb)

# --- ЛОГИКА БИРЖИ (КТО ПЕРВЫЙ ВЗЯЛ) ---
@dp.callback_query(F.data.startswith("take_"))
async def take_market_order(call: types.CallbackQuery):
    oid = call.data.split("take_")[1]
    did = call.from_user.id
    
    if oid not in market_orders:
        return await call.message.edit_text("❌ <b>Заказ уже забрали!</b>")
    
    order = market_orders[oid]
    client_id = order['uid']
    
    # Привязываем клиента к этому водителю
    with sqlite3.connect(DB_PATH) as con:
        con.execute("UPDATE clients SET linked_driver_id=? WHERE user_id=?", (did, client_id))
    
    del market_orders[oid] # Удаляем с биржи
    
    # Меню управления поездкой
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ ПОЕЗДКУ", callback_data=f"fin_{client_id}")]])
    
    await call.message.edit_text(f"✅ <b>ВЫ ВЗЯЛИ ЗАКАЗ!</b>\nКлиент: {client_id}\nМчите по адресу!", reply_markup=kb)
    await safe_send(client_id, f"🎉 <b>Ямщик найден!</b>\nК вам едет водитель. Можете заказывать услуги!")

# --- ПРИВЯЗКА С ВЕРИФИКАЦИЕЙ ---
@dp.message(F.text == "🔑 Код Ямщика")
async def link_code_ask(m: types.Message):
    await m.answer("Введите код ямщика:"); 

@dp.message(lambda x: len(x.text) > 0 and not x.text.startswith("/") and x.text not in ["👤 Моя Светлица", "🔑 Код Ямщика"])
async def process_code_check(m: types.Message):
    code = m.text.strip().upper()
    with sqlite3.connect(DB_PATH) as con:
        drv = con.execute("SELECT user_id, fio FROM drivers WHERE access_code=? AND status='active'", (code,)).fetchone()
    if drv:
        did, name = drv[0], drv[1]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ДА, ЭТО ОН", callback_data=f"pass_yes_{m.from_user.id}"),
             InlineKeyboardButton(text="⛔ ГНАТЬ В ШЕЮ", callback_data=f"pass_no_{m.from_user.id}")]])
        await safe_send(did, f"🚨 <b>ПРОВЕРКА!</b>\nПассажир {m.from_user.full_name} ввел ваш код.\nОн у вас в машине?", kb)
        await m.answer(f"⏳ <b>Ждем кивка Ямщика...</b>\nЯмщик {name} должен подтвердить вашу посадку.")
    else: pass 

@dp.callback_query(F.data.startswith("pass_yes_"))
async def pass_yes(call: types.CallbackQuery):
    cid = int(call.data.split("_")[2]); did = call.from_user.id
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE clients SET linked_driver_id=? WHERE user_id=?", (did, cid))
    await call.message.edit_text("✅ <b>Пассажир подтвержден!</b>")
    await safe_send(cid, "🎉 <b>Доступ открыт!</b> Ямщик подтвердил посадку.")

@dp.callback_query(F.data.startswith("pass_no_"))
async def pass_no(call: types.CallbackQuery):
    cid = int(call.data.split("_")[2])
    await call.message.edit_text("⛔ <b>Отказано.</b>"); await safe_send(cid, "🚫 Ямщик вас не узнал.")

# --- УПРАВЛЕНИЕ ЗАКАЗОМ ---
@dp.callback_query(F.data.startswith("fin_"))
async def finish_order(call: types.CallbackQuery):
    cid = int(call.data.split("_")[1])
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE clients SET linked_driver_id=NULL WHERE user_id=?", (cid,))
    if cid in active_orders: del active_orders[cid]
    await call.message.edit_text("🏁 <b>ПОЕЗДКА ЗАВЕРШЕНА</b>"); await safe_send(cid, "👋 Поездка окончена!")

@dp.callback_query(F.data.startswith("ok_"))
async def accept_order(call: types.CallbackQuery):
    cid = int(call.data.split("_")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ", callback_data=f"fin_{cid}")]])
    await call.message.edit_text(f"✅ <b>В ПУТИ!</b>\n{call.message.html_text.splitlines()[1]}", reply_markup=kb)
    await safe_send(cid, "🚀 Ямщик принял заказ!")

# --- РЕГИСТРАЦИЯ ВОДИТЕЛЯ (ПОЛНАЯ) ---
@dp.message(Command("drive"))
async def reg_start(m: types.Message, state: FSMContext):
    if get_driver(m.from_user.id): return await m.answer("Вы уже в системе.")
    await m.answer("<b>АНКЕТА:</b> ФИО?"); await state.set_state(DriverReg.fio)

@dp.message(DriverReg.fio)
async def reg_fio(m: types.Message, state: FSMContext):
    await state.update_data(fio=m.text); await m.answer("Авто (Марка, Номер)?"); await state.set_state(DriverReg.car)

@dp.message(DriverReg.car)
async def reg_car(m: types.Message, state: FSMContext):
    await state.update_data(car=m.text); await m.answer("Реквизиты?"); await state.set_state(DriverReg.pay)

@dp.message(DriverReg.pay)
async def reg_pay(m: types.Message, state: FSMContext):
    await state.update_data(pay=m.text); await m.answer("Придумайте КОД (латиница):"); await state.set_state(DriverReg.code)

@dp.message(DriverReg.code)
async def reg_fin(m: types.Message, state: FSMContext):
    d = await state.get_data(); code = m.text.strip().upper()
    try:
        with sqlite3.connect(DB_PATH) as con:
            con.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, status) VALUES (?,?,?,?,?,?, 'pending')",
                        (m.from_user.id, m.from_user.username, d['fio'], d['car'], d['pay'], code))
        await m.answer("📜 Заявка отправлена!")
        await safe_send(OWNER_ID, f"🔔 <b>НОВАЯ ЗАЯВКА!</b>\n{d['fio']} (Code: {code})")
    except: await m.answer("❌ Код занят.")
    await state.clear()

# --- КАБИНЕТЫ ---
@dp.message(F.text == "👤 Моя Светлица")
async def cabinet(m: types.Message):
    uid = m.from_user.id
    if uid == OWNER_ID:
        kb = [[InlineKeyboardButton(text="📥 Заявки (HR)", callback_data="adm_requests")],
              [InlineKeyboardButton(text="📋 Список Ямщиков", callback_data="adm_list")],
              [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_cast")]]
        return await m.answer("👑 <b>КАБИНЕТ СТАРОСТЫ</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    
    drv = get_driver(uid)
    if drv and drv[6] == 'active':
        kb = [[InlineKeyboardButton(text="➕ Своя услуга", callback_data="add_custom")]]
        return await m.answer(f"🪪 <b>ЯМЩИК: {drv[2]}</b>\n🔑 Код: {drv[5]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    
    await m.answer("👤 <b>КАБИНЕТ ПАССАЖИРА</b>")

# --- HR И АДМИНКА (ВОССТАНОВЛЕНО ПОЛНОСТЬЮ) ---
@dp.callback_query(F.data == "adm_requests")
async def adm_reqs(call: types.CallbackQuery):
    with sqlite3.connect(DB_PATH) as con: reqs = con.execute("SELECT user_id, fio, car_info, username FROM drivers WHERE status='pending'").fetchall()
    if not reqs: return await call.message.answer("Заявок нет.")
    for r in reqs:
        kb = [[InlineKeyboardButton(text="✅ Принять", callback_data=f"appr_{r[0]}"), InlineKeyboardButton(text="❌ Отказ", callback_data=f"reje_{r[0]}")],
              [InlineKeyboardButton(text="📞 Собеседование", callback_data=f"talk_{r[0]}")]]
        await call.message.answer(f"📝 {r[1]} | @{r[3]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("talk_"))
async def hr_talk(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(target=call.data.split("_")[1])
    await call.message.answer("Вопрос кандидату:"); await state.set_state(AdminHR.interview_text)

@dp.message(AdminHR.interview_text)
async def hr_send(m: types.Message, state: FSMContext):
    d = await state.get_data(); await safe_send(d['target'], f"🤝 <b>Собеседование:</b>\n{m.text}")
    await m.answer("Отправлено."); await state.clear()

@dp.callback_query(F.data.startswith("appr_"))
async def approve(call: types.CallbackQuery):
    did = call.data.split("_")[1]
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE drivers SET status='active' WHERE user_id=?", (did,))
    await call.answer("Принят!"); await safe_send(did, "🎉 Вы приняты!")

@dp.callback_query(F.data.startswith("reje_"))
async def reject(call: types.CallbackQuery):
    did = call.data.split("_")[1]
    with sqlite3.connect(DB_PATH) as con: con.execute("DELETE FROM drivers WHERE user_id=?", (did,))
    await call.answer("Удален"); await safe_send(did, "❌ Отказ.")

@dp.callback_query(F.data == "adm_list")
async def adm_list(call: types.CallbackQuery):
    with sqlite3.connect(DB_PATH) as con: drvs = con.execute("SELECT user_id, fio, status FROM drivers WHERE role!='owner'").fetchall()
    for d in drvs:
        kb = [[InlineKeyboardButton(text="🚫 Блок", callback_data=f"blk_{d[0]}"), InlineKeyboardButton(text="✉️ Письмо", callback_data=f"msg_{d[0]}")],
              [InlineKeyboardButton(text="✅ Разблок", callback_data=f"unl_{d[0]}")]]
        await call.message.answer(f"👤 {d[1]} | {d[2]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("blk_"))
async def blk(call: types.CallbackQuery):
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE drivers SET status='blocked' WHERE user_id=?", (call.data.split("_")[1],))
    await call.answer("Блок")

@dp.callback_query(F.data.startswith("unl_"))
async def unl(call: types.CallbackQuery):
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE drivers SET status='active' WHERE user_id=?", (call.data.split("_")[1],))
    await call.answer("Разблок")

@dp.callback_query(F.data.startswith("msg_"))
async def msg_start(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(target=call.data.split("_")[1])
    await call.message.answer("Текст:"); await state.set_state(AdminMsg.text)

@dp.message(AdminMsg.text)
async def msg_send(m: types.Message, state: FSMContext):
    d = await state.get_data(); await safe_send(d['target'], f"✉️ <b>АДМИН:</b> {m.text}")
    await m.answer("Отправлено."); await state.clear()

@dp.callback_query(F.data == "adm_cast")
async def cast_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Текст рассылки:"); await state.set_state("broadcast")

@dp.message(F.state == "broadcast")
async def cast_send(m: types.Message, state: FSMContext):
    with sqlite3.connect(DB_PATH) as con: us = con.execute("SELECT user_id FROM clients UNION SELECT user_id FROM drivers").fetchall()
    for u in us: await safe_send(u[0], f"📢 <b>ОБЪЯВЛЕНИЕ:</b>\n{m.text}")
    await m.answer("Разослано."); await state.clear()

# --- СВОИ УСЛУГИ ---
@dp.callback_query(F.data == "add_custom")
async def add_cust(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Название:"); await state.set_state(CustomSrv.name)
@dp.message(CustomSrv.name)
async def cust_name(m: types.Message, state: FSMContext):
    await state.update_data(name=m.text); await m.answer("Описание:"); await state.set_state(CustomSrv.desc)
@dp.message(CustomSrv.desc)
async def cust_desc(m: types.Message, state: FSMContext):
    await state.update_data(desc=m.text); await m.answer("Цена:"); await state.set_state(CustomSrv.price)
@dp.message(CustomSrv.price)
async def cust_price(m: types.Message, state: FSMContext):
    if not m.text.isdigit(): return
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
