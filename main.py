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

active_orders = {}
market_orders = {}

# ==========================================
# 📜 УСЛУГИ (ПОЛНЫЙ СПИСОК 20 ШТ)
# ==========================================
CATEGORIES_VIP = ["Большие", "Дикие"] 

CRAZY_SERVICES = {
    "candy": {"cat": "Малые", "name": "🍬 Сладкий гостинец", "desc": "Ямщик с поклоном вручает леденец.", "price": 100},
    "nose": {"cat": "Малые", "name": "👃 Перст в носу", "desc": "Ямщик всю дорогу ковыряет в носу.", "price": 150},
    "butler": {"cat": "Малые", "name": "🤵 Дворецкий", "desc": "Открываем дверь, величаем Барином.", "price": 300},
    "joke": {"cat": "Малые", "name": "🤡 Скоморох", "desc": "Шутки юмора. Смеяться обязательно.", "price": 200},
    "silence": {"cat": "Малые", "name": "🤐 Обет молчания", "desc": "Едем молча, как в монастыре.", "price": 500},
    
    "granny": {"cat": "Средние", "name": "👵 Ворчливая бабка", "desc": "Ролевая игра: Куда прешь, окаянный!", "price": 400},
    "gopnik": {"cat": "Средние", "name": "🍺 Разбойник", "desc": "Шансон, семки, решение вопросиков.", "price": 600},
    "guide": {"cat": "Средние", "name": "🗣 Горе-Гид", "desc": "Небылицы о каждом столбе.", "price": 350},
    "psych": {"cat": "Средние", "name": "🧠 Душеприказчик", "desc": "Слушаем кручину, даем советы.", "price": 1000},

    "spy": {"cat": "Большие", "name": "🕵️ Опричник (007)", "desc": "Тайная слежка и уход от погони.", "price": 1500},
    "karaoke": {"cat": "Большие", "name": "🎤 Застольные песни", "desc": "Орем песни дуэтом.", "price": 800},
    "dance": {"cat": "Большие", "name": "🐻 Медвежьи пляски", "desc": "Танцы на капоте.", "price": 1200},

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
    
    # 0:user_id, 1:username, 2:fio, 3:car_info, 4:payment_info, 5:access_code, 6:vip_code, 7:status, 8:role, 9:balance, 10:lat, 11:lon
    cur.execute("""CREATE TABLE IF NOT EXISTS drivers (
        user_id INTEGER PRIMARY KEY, username TEXT, fio TEXT, car_info TEXT, payment_info TEXT, 
        access_code TEXT UNIQUE, vip_code TEXT UNIQUE, 
        status TEXT DEFAULT 'pending', role TEXT DEFAULT 'driver', balance INTEGER DEFAULT 0, lat REAL, lon REAL)""")
    
    cur.execute("CREATE TABLE IF NOT EXISTS disabled_services (driver_id INTEGER, service_key TEXT, PRIMARY KEY(driver_id, service_key))")
    cur.execute("CREATE TABLE IF NOT EXISTS custom_services (id INTEGER PRIMARY KEY AUTOINCREMENT, driver_id INTEGER, name TEXT, description TEXT, price INTEGER, category TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER DEFAULT NULL, access_level TEXT DEFAULT 'std')")

    # Миграция (защищенная)
    def add_col(tbl, col, tp):
        try: cur.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {tp}")
        except: pass

    add_col("drivers", "vip_code", "TEXT UNIQUE")
    add_col("drivers", "lat", "REAL")
    add_col("drivers", "username", "TEXT")
    add_col("custom_services", "category", "TEXT DEFAULT 'Личные'")
    add_col("clients", "access_level", "TEXT DEFAULT 'std'")

    # Админ
    cur.execute("INSERT OR IGNORE INTO drivers (user_id, fio, access_code, vip_code, status, role) VALUES (?, 'СТАРОСТА', 'ADMIN', 'ADMIN_VIP', 'active', 'owner')", (OWNER_ID,))
    cur.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (OWNER_ID,))
    
    conn.commit(); conn.close()

init_db()

# ==========================================
# 📡 WEB API
# ==========================================
async def get_services(request):
    uid = int(request.query.get('user_id', 0))
    with sqlite3.connect(DB_PATH) as con:
        cli = con.execute("SELECT linked_driver_id, access_level FROM clients WHERE user_id=?", (uid,)).fetchone()
        
        # Если нет водителя - отдаем базовый список для биржи
        if not cli or not cli[0]:
            res = [v for k, v in CRAZY_SERVICES.items() if v['cat'] not in CATEGORIES_VIP]
            return web.json_response(res)
        
        did, level = cli[0], cli[1]
        disabled = [r[0] for r in con.execute("SELECT service_key FROM disabled_services WHERE driver_id=?", (did,)).fetchall()]
        customs = con.execute("SELECT name, description, price, category FROM custom_services WHERE driver_id=?", (did,)).fetchall()
    
    final = []
    # Стандартные
    for k, v in CRAZY_SERVICES.items():
        if k in disabled: continue
        if level != 'vip' and v['cat'] in CATEGORIES_VIP: continue
        final.append(v)
    
    # Личные
    for c in customs:
        cat = c[3]
        if level != 'vip' and cat in CATEGORIES_VIP: continue
        final.append({"name": c[0], "desc": c[1], "price": c[2], "cat": cat})
        
    return web.json_response(final)

async def web_order(request):
    data = await request.json()
    uid, srv, price, lat, lon = data.get('user_id'), data.get('service'), data.get('price'), data.get('lat'), data.get('lon')
    
    with sqlite3.connect(DB_PATH) as con:
        cli = con.execute("SELECT linked_driver_id FROM clients WHERE user_id=?", (uid,)).fetchone()
    
    map_url = f"https://www.google.com/maps?q={lat},{lon}"
    
    if cli and cli[0]:
        # Личный заказ
        active_orders[uid] = {"driver_id": cli[0]}
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"ok_{uid}"), InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"fin_{uid}")]])
        await bot.send_message(cli[0], f"🔔 <b>ЛИЧНЫЙ ЗАКАЗ!</b>\n🎭 {srv}\n💰 {price}₽\n📍 <a href='{map_url}'>КАРТА</a>", reply_markup=kb)
        return web.json_response({"status": "ok"})
    else:
        # Биржа
        oid = f"m_{uid}_{int(datetime.now().timestamp())}"
        market_orders[oid] = {"uid": uid, "srv": srv, "price": price, "map": map_url}
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✋ ЗАБРАТЬ", callback_data=f"take_{oid}")]])
        
        with sqlite3.connect(DB_PATH) as con:
            drvs = con.execute("SELECT user_id FROM drivers WHERE status='active' AND role!='owner'").fetchall()
        
        cnt = 0
        for d in drvs:
            try:
                await bot.send_message(d[0], f"📥 <b>БИРЖА:</b> {srv} ({price}₽)", reply_markup=kb)
                cnt += 1
            except: pass
        return web.json_response({"status": "ok_market" if cnt > 0 else "no_active_drivers"})

# ==========================================
# 🤖 BOT HANDLERS
# ==========================================
class DriverReg(StatesGroup): fio=State(); car=State(); pay=State(); code1=State(); code2=State()
class CustomSrv(StatesGroup): name=State(); desc=State(); price=State(); cat=State()
class ChangeCodes(StatesGroup): c1=State(); c2=State()
class AdminMsg(StatesGroup): text=State()
class AdminHR(StatesGroup): text=State()

def get_driver(uid):
    with sqlite3.connect(DB_PATH) as con: return con.execute("SELECT * FROM drivers WHERE user_id=?", (uid,)).fetchone()

async def safe_send(chat_id, text, kb=None):
    try: await bot.send_message(chat_id, text, reply_markup=kb); return True
    except: return False

@dp.message(Command("start"))
async def start(m: types.Message, state: FSMContext):
    await state.clear()
    with sqlite3.connect(DB_PATH) as con: con.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (m.from_user.id,))
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🚖 ЗАКАЗАТЬ ПОТЕХУ", web_app=WebAppInfo(url=APP_URL))],
                                       [KeyboardButton(text="👤 Моя Светлица"), KeyboardButton(text="🔑 Код Ямщика")]], resize_keyboard=True)
    await m.answer("🐎 <b>Артель приветствует!</b>", reply_markup=kb)

# --- ПРИВЯЗКА (ВЕРИФИКАЦИЯ) ---
@dp.message(F.text == "🔑 Код Ямщика")
async def link_ask(m: types.Message): await m.answer("Введите код:")

@dp.message(F.text & ~F.text.startswith("/"))
async def process_code(m: types.Message):
    code = m.text.strip().upper()
    with sqlite3.connect(DB_PATH) as con:
        # Проверяем оба кода
        drv = con.execute("SELECT user_id, fio, access_code, vip_code FROM drivers WHERE (access_code=? OR vip_code=?) AND status='active'", (code, code)).fetchone()
    
    if drv:
        did, name, c1, c2 = drv
        lvl = 'vip' if code == c2 else 'std'
        info = "VIP 👑" if lvl == 'vip' else "ОБЫЧНЫЙ 👤"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ДА, МОЙ", callback_data=f"pass_yes_{m.from_user.id}_{lvl}"),
             InlineKeyboardButton(text="⛔ ЧУЖАК", callback_data=f"pass_no_{m.from_user.id}")]])
        
        await safe_send(did, f"🚨 <b>ПРОВЕРКА!</b>\nПассажир ввел {info} код: {code}\nОн у вас в машине?", kb)
        await m.answer(f"⏳ <b>Ждем подтверждения...</b>\nЯмщик {name} должен кивнуть.")
    else: pass

@dp.callback_query(F.data.startswith("pass_yes_"))
async def py(c: types.CallbackQuery):
    _, _, cid, lvl = c.data.split("_")
    did = c.from_user.id
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE clients SET linked_driver_id=?, access_level=? WHERE user_id=?", (did, lvl, cid))
    await c.message.edit_text(f"✅ Пассажир подтвержден ({lvl.upper()})")
    await safe_send(cid, "🎉 Доступ открыт!")

@dp.callback_query(F.data.startswith("pass_no_"))
async def pn(c: types.CallbackQuery):
    cid = c.data.split("_")[2]
    await c.message.edit_text("⛔ Отказ"); await safe_send(cid, "🚫 Ямщик отклонил вход.")

# --- БИРЖА ---
@dp.callback_query(F.data.startswith("take_"))
async def take(c: types.CallbackQuery):
    oid = c.data.split("take_")[1]; did = c.from_user.id
    if oid not in market_orders: return await c.message.edit_text("❌ Опоздали!")
    ord = market_orders[oid]
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE clients SET linked_driver_id=? WHERE user_id=?", (did, ord['uid']))
    del market_orders[oid]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ", callback_data=f"fin_{ord['uid']}")]])
    await c.message.edit_text("✅ <b>Заказ ваш!</b>", reply_markup=kb)
    await safe_send(ord['uid'], "🚀 Ямщик найден!")

# --- КАБИНЕТЫ ---
@dp.message(F.text == "👤 Моя Светлица")
async def cab(m: types.Message):
    uid = m.from_user.id
    if uid == OWNER_ID:
        kb = [[InlineKeyboardButton(text="📥 Заявки", callback_data="adm_reqs")],
              [InlineKeyboardButton(text="📋 Ямщики", callback_data="adm_list")],
              [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_cast")]]
        return await m.answer("👑 <b>КАБИНЕТ СТАРОСТЫ</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    
    drv = get_driver(uid)
    # ИСПРАВЛЕНО: Индекс статуса теперь точно 7, так как мы добавили колонки
    if drv and drv[7] == 'active':
        kb = [[InlineKeyboardButton(text="🎛 Репертуар", callback_data="menu_tgl")],
              [InlineKeyboardButton(text="➕ Своя услуга", callback_data="add_custom")],
              [InlineKeyboardButton(text="⚙️ Коды", callback_data="settings")]]
        await m.answer(f"🪪 <b>ЯМЩИК: {drv[2]}</b>\n🔑 Код: <code>{drv[5]}</code>\n💎 VIP: <code>{drv[6]}</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return
    
    await m.answer("👤 <b>КАБИНЕТ ПАССАЖИРА</b>")

# --- ЯМЩИК (НАСТРОЙКИ) ---
@dp.callback_query(F.data == "menu_tgl")
async def mt(c: types.CallbackQuery):
    did = c.from_user.id
    with sqlite3.connect(DB_PATH) as con: dis = [r[0] for r in con.execute("SELECT service_key FROM disabled_services WHERE driver_id=?", (did,)).fetchall()]
    kb = []
    for k, v in CRAZY_SERVICES.items():
        s = "🔴" if k in dis else "🟢"
        kb.append([InlineKeyboardButton(text=f"{s} {v['name']}", callback_data=f"tg_{k}")])
    kb.append([InlineKeyboardButton(text="🔙", callback_data="back")])
    await c.message.edit_text("🎛 <b>Репертуар:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("tg_"))
async def tg(c: types.CallbackQuery):
    k = c.data.split("_")[1]; did = c.from_user.id
    with sqlite3.connect(DB_PATH) as con:
        if con.execute("SELECT 1 FROM disabled_services WHERE driver_id=? AND service_key=?", (did, k)).fetchone():
            con.execute("DELETE FROM disabled_services WHERE driver_id=? AND service_key=?", (did, k))
        else: con.execute("INSERT INTO disabled_services VALUES (?, ?)", (did, k))
    await mt(c)

@dp.callback_query(F.data == "settings")
async def sett(c: types.CallbackQuery):
    kb = [[InlineKeyboardButton(text="🔑 Сменить коды", callback_data="chg_c")], [InlineKeyboardButton(text="🔙", callback_data="back")]]
    await c.message.edit_text("⚙️ <b>Настройки</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "chg_c")
async def cc_start(c: types.CallbackQuery, state: FSMContext): await c.message.answer("Новый ПУБЛИЧНЫЙ код:"); await state.set_state(ChangeCodes.c1)
@dp.message(ChangeCodes.c1)
async def cc1(m: types.Message, state: FSMContext): await state.update_data(c1=m.text.upper()); await m.answer("Новый VIP код:"); await state.set_state(ChangeCodes.c2)
@dp.message(ChangeCodes.c2)
async def cc2(m: types.Message, state: FSMContext):
    d = await state.get_data()
    try:
        with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE drivers SET access_code=?, vip_code=? WHERE user_id=?", (d['c1'], m.text.upper(), m.from_user.id))
        await m.answer("✅ Коды изменены!")
    except: await m.answer("❌ Занято.")
    await state.clear()

@dp.callback_query(F.data == "add_custom")
async def ac(c: types.CallbackQuery, state: FSMContext): await c.message.answer("Название:"); await state.set_state(CustomSrv.name)
@dp.message(CustomSrv.name)
async def cn(m: types.Message, state: FSMContext): await state.update_data(name=m.text); await m.answer("Описание:"); await state.set_state(CustomSrv.desc)
@dp.message(CustomSrv.desc)
async def cd(m: types.Message, state: FSMContext): await state.update_data(desc=m.text); await m.answer("Цена:"); await state.set_state(CustomSrv.price)
@dp.message(CustomSrv.price)
async def cp(m: types.Message, state: FSMContext):
    if not m.text.isdigit(): return
    await state.update_data(price=int(m.text))
    kb = [[KeyboardButton(text=c)] for c in ["Малые", "Средние", "Большие", "Дикие", "Светские"]]
    await m.answer("Категория:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)); await state.set_state(CustomSrv.cat)
@dp.message(CustomSrv.cat)
async def ccat(m: types.Message, state: FSMContext):
    d = await state.get_data()
    with sqlite3.connect(DB_PATH) as con: con.execute("INSERT INTO custom_services (driver_id, name, description, price, category) VALUES (?,?,?,?,?)", (m.from_user.id, d['name'], d['desc'], d['price'], m.text))
    await m.answer("✅ Добавлено!", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="👤 Моя Светлица")]], resize_keyboard=True)); await state.clear()

# --- АДМИНКА ---
@dp.callback_query(F.data == "adm_reqs")
async def ar(c: types.CallbackQuery):
    with sqlite3.connect(DB_PATH) as con: rs = con.execute("SELECT user_id, fio, username FROM drivers WHERE status='pending'").fetchall()
    if not rs: return await c.message.answer("Пусто.")
    for r in rs:
        kb = [[InlineKeyboardButton(text="✅", callback_data=f"ok_{r[0]}"), InlineKeyboardButton(text="❌", callback_data=f"no_{r[0]}")],
              [InlineKeyboardButton(text="📞", callback_data=f"talk_{r[0]}")]]
        await c.message.answer(f"📝 {r[1]} (@{r[2]})", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("talk_"))
async def talk(c: types.CallbackQuery, state: FSMContext): await state.update_data(trg=c.data.split("_")[1]); await c.message.answer("Вопрос:"); await state.set_state(AdminHR.text)
@dp.message(AdminHR.text)
async def ts(m: types.Message, state: FSMContext):
    d = await state.get_data(); await safe_send(d['trg'], f"🤝 <b>Собеседование:</b>\n{m.text}"); await m.answer("Ушло."); await state.clear()

@dp.callback_query(F.data.startswith("ok_"))
async def aok(c: types.CallbackQuery):
    did = c.data.split("_")[1]
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE drivers SET status='active' WHERE user_id=?", (did,))
    await c.answer("Ок"); await safe_send(did, "✅ Принят!")

@dp.callback_query(F.data.startswith("no_"))
async def ano(c: types.CallbackQuery):
    did = c.data.split("_")[1]
    with sqlite3.connect(DB_PATH) as con: con.execute("DELETE FROM drivers WHERE user_id=?", (did,))
    await c.answer("Нет"); await safe_send(did, "❌ Отказ")

@dp.callback_query(F.data == "adm_list")
async def al(c: types.CallbackQuery):
    with sqlite3.connect(DB_PATH) as con: ds = con.execute("SELECT user_id, fio, status FROM drivers WHERE role!='owner'").fetchall()
    for d in ds:
        kb = [[InlineKeyboardButton(text="Блок", callback_data=f"blk_{d[0]}"), InlineKeyboardButton(text="Разблок", callback_data=f"unl_{d[0]}")],
              [InlineKeyboardButton(text="Письмо", callback_data=f"msg_{d[0]}")]]
        await c.message.answer(f"👤 {d[1]} | {d[2]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("blk_"))
async def blk(c: types.CallbackQuery):
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE drivers SET status='blocked' WHERE user_id=?", (c.data.split("_")[1],))
    await c.answer("Блок")
@dp.callback_query(F.data.startswith("unl_"))
async def unl(c: types.CallbackQuery):
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE drivers SET status='active' WHERE user_id=?", (c.data.split("_")[1],))
    await c.answer("Разблок")
@dp.callback_query(F.data.startswith("msg_"))
async def ams(c: types.CallbackQuery, state: FSMContext): await state.update_data(trg=c.data.split("_")[1]); await c.message.answer("Текст:"); await state.set_state(AdminMsg.text)
@dp.message(AdminMsg.text)
async def amss(m: types.Message, state: FSMContext):
    d = await state.get_data(); await safe_send(d['trg'], f"✉️ <b>АДМИН:</b> {m.text}"); await m.answer("Ушло."); await state.clear()
@dp.callback_query(F.data == "adm_cast")
async def cast(c: types.CallbackQuery, state: FSMContext): await c.message.answer("Текст:"); await state.set_state("bc")
@dp.message(F.state == "bc")
async def casts(m: types.Message, state: FSMContext):
    with sqlite3.connect(DB_PATH) as con: us = con.execute("SELECT user_id FROM clients UNION SELECT user_id FROM drivers").fetchall()
    for u in us: await safe_send(u[0], f"📢 {m.text}"); await m.answer("Разослано."); await state.clear()

# --- СИСТЕМА ---
@dp.callback_query(F.data == "back")
async def bck(c: types.CallbackQuery): await c.message.delete(); await cabinet(c.message)
@dp.message(Command("drive"))
async def reg(m: types.Message, state: FSMContext):
    if get_driver(m.from_user.id): return await m.answer("Уже в системе.")
    await m.answer("ФИО?"); await state.set_state(DriverReg.fio)
@dp.message(DriverReg.fio)
async def rf(m: types.Message, state: FSMContext): await state.update_data(fio=m.text); await m.answer("Авто?"); await state.set_state(DriverReg.car)
@dp.message(DriverReg.car)
async def rc(m: types.Message, state: FSMContext): await state.update_data(car=m.text); await m.answer("Реквизиты?"); await state.set_state(DriverReg.pay)
@dp.message(DriverReg.pay)
async def rp(m: types.Message, state: FSMContext): await state.update_data(pay=m.text); await m.answer("ПУБЛИЧНЫЙ код:"); await state.set_state(DriverReg.code1)
@dp.message(DriverReg.code1)
async def rc1(m: types.Message, state: FSMContext): await state.update_data(c1=m.text.upper()); await m.answer("VIP код:"); await state.set_state(DriverReg.code2)
@dp.message(DriverReg.code2)
async def rc2(m: types.Message, state: FSMContext):
    d = await state.get_data()
    try:
        with sqlite3.connect(DB_PATH) as con:
            con.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, vip_code, status) VALUES (?,?,?,?,?,?,?, 'pending')",
                        (m.from_user.id, m.from_user.username, d['fio'], d['car'], d['pay'], d['c1'], m.text.upper()))
        await m.answer("📜 Заявка отправлена!")
        await safe_send(OWNER_ID, f"🔔 ЗАЯВКА!\n{d['fio']}")
    except: await m.answer("❌ Коды заняты.")
    await state.clear()
@dp.callback_query(F.data.startswith("fin_"))
async def fin(c: types.CallbackQuery):
    cid = int(c.data.split("_")[1])
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE clients SET linked_driver_id=NULL WHERE user_id=?", (cid,))
    if cid in active_orders: del active_orders[cid]
    await c.message.edit_text("🏁 ЗАВЕРШЕНО"); await safe_send(cid, "👋 Поездка окончена!")
@dp.callback_query(F.data.startswith("ok_"))
async def ok(c: types.CallbackQuery):
    cid = int(c.data.split("_")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ", callback_data=f"fin_{cid}")]])
    await c.message.edit_text(f"✅ В ПУТИ!\n{c.message.html_text.splitlines()[1]}", reply_markup=kb)
    await safe_send(cid, "🚀 Принято!")

async def on_startup(app): await bot.delete_webhook(drop_pending_updates=True); asyncio.create_task(dp.start_polling(bot))
def main():
    app = web.Application(); app.router.add_get('/', lambda r: web.FileResponse(HTML_FILE))
    app.router.add_get('/get_services', get_services); app.router.add_post('/webapp_order', web_order)
    app.on_startup.append(on_startup); web.run_app(app, host='0.0.0.0', port=8080)
if __name__ == "__main__": main()
