import asyncio
import logging
import os
import sqlite3
import json
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, FSInputFile
from aiogram.client.default import DefaultBotProperties

# ==========================================
# ⚙️ НАСТРОЙКИ И КОНСТАНТЫ
# ==========================================
logging.basicConfig(level=logging.INFO)
API_TOKEN = os.getenv("API_TOKEN")
OWNER_ID = 6004764782
APP_URL = "https://tazyy-milekcat.amvera.io"

PARTNER_TEXT = (
    "💎 <b>ПАРТНЁР АРТЕЛИ</b>\n\n"
    "Наш генеральный спонсор и друг — <b>KWORK</b>.\n"
    "Лучшая биржа фриланса для бояр и купцов.\n\n"
    "<i>Здесь могла быть ваша реклама или ссылка на канал.</i>"
)

WELCOME_TEXT = (
    "📜 <b>УКАЗ ПО АРТЕЛИ «ВЕСЁЛЫЙ ИЗВОЗЧИК»</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Приветствуем тебя, добрый человек!\n"
    "Здесь не просто такси, здесь — <b>Душа</b>.\n\n"
    "🎭 <b>ЧТО МЫ МОЖЕМ:</b>\n"
    "• <b>Утешить:</b> Ямщик-психолог выслушает.\n"
    "• <b>Развлечь:</b> Песни, пляски, медведи.\n"
    "• <b>Удивить:</b> Сожжем карету за ваши деньги.\n\n"
    "👇 <b>КАК ПОЛЬЗОВАТЬСЯ:</b>\n"
    "1. Жми <b>«Заказать потеху»</b> для вызова.\n"
    "2. Введи <b>«Код Ямщика»</b>, если уже сел в сани.\n"
    "3. Загляни в <b>«Светлицу»</b> для настроек.\n\n"
    "<i>Поехали, с ветерком!</i> 🐎💨"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(BASE_DIR, 'index.html')
# Используем постоянное хранилище Amvera /data
DB_PATH = "/data/taxi_db.sqlite" if os.path.exists("/data") else os.path.join(BASE_DIR, "taxi_db.sqlite")

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

active_orders = {}
market_orders = {}

# ==========================================
# 📜 УСЛУГИ
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
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row 
    return conn

def init_db():
    logging.info(f"💾 [DB] Initializing database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""CREATE TABLE IF NOT EXISTS drivers (
            user_id INTEGER PRIMARY KEY, username TEXT, fio TEXT, car_info TEXT, payment_info TEXT, 
            access_code TEXT UNIQUE, vip_code TEXT UNIQUE, 
            status TEXT DEFAULT 'pending', role TEXT DEFAULT 'driver', balance INTEGER DEFAULT 0, lat REAL, lon REAL)""")
        conn.commit()

        cur.execute("CREATE TABLE IF NOT EXISTS disabled_services (driver_id INTEGER, service_key TEXT, PRIMARY KEY(driver_id, service_key))")
        cur.execute("CREATE TABLE IF NOT EXISTS custom_services (id INTEGER PRIMARY KEY AUTOINCREMENT, driver_id INTEGER, name TEXT, description TEXT, price INTEGER, category TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER DEFAULT NULL, access_level TEXT DEFAULT 'std')")
        conn.commit()

        # Миграции
        def add_col(tbl, col, tp):
            try: cur.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {tp}")
            except: pass
        
        add_col("drivers", "vip_code", "TEXT UNIQUE")
        add_col("drivers", "lat", "REAL")
        add_col("drivers", "username", "TEXT")
        add_col("custom_services", "category", "TEXT DEFAULT 'Личные'")
        add_col("clients", "access_level", "TEXT DEFAULT 'std'")
        conn.commit()

        # Админ
        cur.execute("INSERT OR IGNORE INTO drivers (user_id, fio, access_code, vip_code, status, role) VALUES (?, 'СТАРОСТА', 'ADMIN', 'ADMIN_VIP', 'active', 'owner')", (OWNER_ID,))
        cur.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (OWNER_ID,))
        conn.commit()
        conn.close()
        logging.info("✅ [DB] OK.")
    except Exception as e:
        logging.error(f"❌ [DB] ERROR: {e}")

init_db()

# ==========================================
# 📡 WEB API
# ==========================================
async def get_services(request):
    uid = int(request.query.get('user_id', 0))
    with get_db_connection() as con:
        cli = con.execute("SELECT linked_driver_id, access_level FROM clients WHERE user_id=?", (uid,)).fetchone()
        
        if not cli or not cli['linked_driver_id']:
            res = [v for k, v in CRAZY_SERVICES.items() if v['cat'] not in CATEGORIES_VIP]
            return web.json_response(res)
        
        did = cli['linked_driver_id']
        level = cli['access_level']
        disabled = [r['service_key'] for r in con.execute("SELECT service_key FROM disabled_services WHERE driver_id=?", (did,)).fetchall()]
        customs = con.execute("SELECT name, description, price, category FROM custom_services WHERE driver_id=?", (did,)).fetchall()
    
    final = []
    for k, v in CRAZY_SERVICES.items():
        if k in disabled: continue
        if level != 'vip' and v['cat'] in CATEGORIES_VIP: continue
        final.append(v)
    for c in customs:
        cat = c['category']
        if level != 'vip' and cat in CATEGORIES_VIP: continue
        final.append({"name": c['name'], "desc": c['description'], "price": c['price'], "cat": cat})
        
    return web.json_response(final)

async def web_order(request):
    data = await request.json()
    uid, srv, price, lat, lon = data.get('user_id'), data.get('service'), data.get('price'), data.get('lat'), data.get('lon')
    
    with get_db_connection() as con:
        cli = con.execute("SELECT linked_driver_id FROM clients WHERE user_id=?", (uid,)).fetchone()
    
    map_url = f"https://www.google.com/maps?q={lat},{lon}"
    
    if cli and cli['linked_driver_id']:
        did = cli['linked_driver_id']
        active_orders[uid] = {"driver_id": did}
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"ok_{uid}"), 
             InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"fin_{uid}")]
        ])
        await bot.send_message(did, f"🔔 <b>ЛИЧНЫЙ ЗАКАЗ!</b>\n🎭 {srv}\n💰 {price}₽\n📍 <a href='{map_url}'>КАРТА</a>", reply_markup=kb)
        return web.json_response({"status": "ok"})
    else:
        oid = f"m_{uid}_{int(datetime.now().timestamp())}"
        market_orders[oid] = {"uid": uid, "srv": srv, "price": price, "map": map_url}
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✋ ЗАБРАТЬ", callback_data=f"take_{oid}")]])
        with get_db_connection() as con:
            drvs = con.execute("SELECT user_id FROM drivers WHERE status='active' AND role!='owner'").fetchall()
        cnt = 0
        for d in drvs:
            try:
                await bot.send_message(d['user_id'], f"📥 <b>БИРЖА:</b> {srv} ({price}₽)\n📍 <a href='{map_url}'>Показать на карте</a>", reply_markup=kb)
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
    with get_db_connection() as con: return con.execute("SELECT * FROM drivers WHERE user_id=?", (uid,)).fetchone()

async def safe_send(chat_id, text, kb=None):
    try: await bot.send_message(chat_id, text, reply_markup=kb); return True
    except: return False

# 1. COMMANDS
@dp.message(Command("start"))
async def start(m: types.Message, state: FSMContext):
    await state.clear()
    try:
        with get_db_connection() as con: 
            con.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (m.from_user.id,))
    except: pass

    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🚖 ЗАКАЗАТЬ ПОТЕХУ", web_app=WebAppInfo(url=APP_URL))],
        [KeyboardButton(text="👤 Моя Светлица"), KeyboardButton(text="🔑 Код Ямщика")]
    ], resize_keyboard=True)
    await m.answer(WELCOME_TEXT, reply_markup=kb)

# 2. SPECIFIC TEXT HANDLERS (PRIORITY)
@dp.message(F.text == "🔑 Код Ямщика")
async def link_ask(m: types.Message, state: FSMContext): 
    await state.clear()
    await m.answer("Введите код ямщика:")

@dp.message(F.text == "👤 Моя Светлица")
async def cab(m: types.Message, state: FSMContext):
    await state.clear() # Сбрасываем любые зависшие диалоги
    uid = m.from_user.id
    if uid == OWNER_ID:
        kb = [[InlineKeyboardButton(text="📥 Заявки", callback_data="adm_reqs")],
              [InlineKeyboardButton(text="📋 Ямщики", callback_data="adm_list")],
              [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_cast")],
              [InlineKeyboardButton(text="💎 Партнёр Артели", callback_data="partner")]]
        return await m.answer("👑 <b>КАБИНЕТ СТАРОСТЫ</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    
    drv = get_driver(uid)
    if drv and drv['status'] == 'active':
        kb = [[InlineKeyboardButton(text="🎛 Репертуар", callback_data="menu_tgl")],
              [InlineKeyboardButton(text="➕ Своя услуга", callback_data="add_custom")],
              [InlineKeyboardButton(text="⚙️ Коды", callback_data="settings")],
              [InlineKeyboardButton(text="💎 Партнёр Артели", callback_data="partner")]]
        await m.answer(
            f"🪪 <b>ЯМЩИК: {drv['fio']}</b>\n🔑 Публичный: <code>{drv['access_code']}</code>\n💎 VIP: <code>{drv['vip_code']}</code>", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return
    
    kb = [[InlineKeyboardButton(text="💎 Партнёр Артели", callback_data="partner")]]
    await m.answer("👤 <b>КАБИНЕТ ПАССАЖИРА</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# 3. GENERIC CODE HANDLER (С ЗАЩИТОЙ ОТ СТЕЙТОВ)
@dp.message(F.text & ~F.text.startswith("/") & StateFilter(None))
async def process_code(m: types.Message):
    code = m.text.strip().upper()
    if len(code) > 15 or " " in code: return # Игнорируем длинные тексты
    
    with get_db_connection() as con:
        drv = con.execute("SELECT user_id, fio, access_code, vip_code FROM drivers WHERE (access_code=? OR vip_code=?) AND status='active'", (code, code)).fetchone()
        pending = None
        if not drv:
            pending = con.execute("SELECT status FROM drivers WHERE access_code=? OR vip_code=?", (code, code)).fetchone()

    if drv:
        did = drv['user_id']
        name = drv['fio']
        c2 = drv['vip_code']
        lvl = 'vip' if code == c2 else 'std'
        info = "VIP 👑" if lvl == 'vip' else "ОБЫЧНЫЙ 👤"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ДА", callback_data=f"pass_yes_{m.from_user.id}_{lvl}"), InlineKeyboardButton(text="⛔ НЕТ", callback_data=f"pass_no_{m.from_user.id}")]])
        await safe_send(did, f"🚨 <b>ПРОВЕРКА!</b>\nПассажир ввел {info} код: {code}\nОн у вас в машине?", kb)
        await m.answer(f"⏳ <b>Ждем подтверждения...</b>\nЯмщик {name} должен кивнуть.")
    elif pending:
        await m.answer(f"❌ <b>Ямщик не работает!</b>\nСтатус: {pending['status']}.")
    else:
        await m.answer("❌ <b>Код не найден!</b>")

# 4. CALLBACKS
@dp.callback_query(F.data == "partner")
async def show_partner(c: types.CallbackQuery): await c.message.answer(PARTNER_TEXT); await c.answer()

@dp.callback_query(F.data.startswith("pass_yes_"))
async def py(c: types.CallbackQuery):
    _, _, cid, lvl = c.data.split("_")
    did = c.from_user.id
    with get_db_connection() as con: con.execute("UPDATE clients SET linked_driver_id=?, access_level=? WHERE user_id=?", (did, lvl, cid))
    await c.message.edit_text(f"✅ Пассажир подтвержден ({lvl.upper()})")
    await safe_send(cid, "🎉 <b>Доступ открыт!</b>")

@dp.callback_query(F.data.startswith("pass_no_"))
async def pn(c: types.CallbackQuery):
    cid = c.data.split("_")[2]
    await c.message.edit_text("⛔ Отказ"); await safe_send(cid, "🚫 Ямщик отклонил вход.")

@dp.callback_query(F.data.startswith("take_"))
async def take(c: types.CallbackQuery):
    oid = c.data.split("take_")[1]; did = c.from_user.id
    if oid not in market_orders: return await c.message.edit_text("❌ Опоздали!")
    ord = market_orders[oid]
    with get_db_connection() as con: con.execute("UPDATE clients SET linked_driver_id=? WHERE user_id=?", (did, ord['uid']))
    del market_orders[oid]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 ЗАВЕРШИТЬ", callback_data=f"fin_{ord['uid']}")]])
    await c.message.edit_text("✅ <b>Заказ ваш!</b>", reply_markup=kb)
    await safe_send(ord['uid'], "🚀 <b>Ямщик найден!</b>\nК вам едет карета.")

@dp.callback_query(F.data == "menu_tgl")
async def mt(c: types.CallbackQuery, state: FSMContext):
    await state.clear() # Чистим стейты
    did = c.from_user.id
    with get_db_connection() as con: dis = [r['service_key'] for r in con.execute("SELECT service_key FROM disabled_services WHERE driver_id=?", (did,)).fetchall()]
    kb = []
    for k, v in CRAZY_SERVICES.items():
        s = "🔴" if k in dis else "🟢"
        kb.append([InlineKeyboardButton(text=f"{s} {v['name']}", callback_data=f"tg_{k}")])
    kb.append([InlineKeyboardButton(text="🔙", callback_data="back")])
    await c.message.edit_text("🎛 <b>Репертуар:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await c.answer()

@dp.callback_query(F.data.startswith("tg_"))
async def tg(c: types.CallbackQuery):
    k = c.data.split("_")[1]; did = c.from_user.id
    with get_db_connection() as con:
        if con.execute("SELECT 1 FROM disabled_services WHERE driver_id=? AND service_key=?", (did, k)).fetchone():
            con.execute("DELETE FROM disabled_services WHERE driver_id=? AND service_key=?", (did, k))
        else: con.execute("INSERT INTO disabled_services VALUES (?, ?)", (did, k))
    await mt(c, FSMContext(storage=storage, key=c.from_user.id)) # Hack to refresh

@dp.callback_query(F.data == "settings")
async def sett(c: types.CallbackQuery, state: FSMContext):
    await state.clear()
    kb = [[InlineKeyboardButton(text="🔑 Сменить коды", callback_data="chg_c")], [InlineKeyboardButton(text="🔙", callback_data="back")]]
    await c.message.edit_text("⚙️ <b>Настройки</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await c.answer()

@dp.callback_query(F.data == "chg_c")
async def cc_start(c: types.CallbackQuery, state: FSMContext): await c.message.answer("Новый ПУБЛИЧНЫЙ код:"); await state.set_state(ChangeCodes.c1); await c.answer()
@dp.message(ChangeCodes.c1)
async def cc1(m: types.Message, state: FSMContext): await state.update_data(c1=m.text.upper()); await m.answer("Новый VIP код:"); await state.set_state(ChangeCodes.c2)
@dp.message(ChangeCodes.c2)
async def cc2(m: types.Message, state: FSMContext):
    d = await state.get_data()
    try:
        with get_db_connection() as con: con.execute("UPDATE drivers SET access_code=?, vip_code=? WHERE user_id=?", (d['c1'], m.text.upper(), m.from_user.id))
        await m.answer("✅ Коды изменены!")
    except: await m.answer("❌ Занято.")
    await state.clear()

@dp.callback_query(F.data == "add_custom")
async def ac(c: types.CallbackQuery, state: FSMContext): 
    await state.clear()
    await c.message.answer("Название:"); await state.set_state(CustomSrv.name); await c.answer()
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
    with get_db_connection() as con: con.execute("INSERT INTO custom_services (driver_id, name, description, price, category) VALUES (?,?,?,?,?)", (m.from_user.id, d['name'], d['desc'], d['price'], m.text))
    await m.answer("✅ Добавлено!", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="👤 Моя Светлица")]], resize_keyboard=True)); await state.clear()

# 5. ADMIN & REG
@dp.callback_query(F.data == "adm_reqs")
async def ar(c: types.CallbackQuery, state: FSMContext):
    await state.clear() # ВАЖНО: Сбрасываем стейт, чтобы не висело "Текст:"
    with get_db_connection() as con: rs = con.execute("SELECT user_id, fio, username FROM drivers WHERE status='pending'").fetchall()
    if not rs: 
        await c.answer()
        return await c.message.answer("Список заявок пуст 🤷‍♂️")
    for r in rs:
        kb = [[InlineKeyboardButton(text="✅", callback_data=f"ok_{r['user_id']}"), InlineKeyboardButton(text="❌", callback_data=f"no_{r['user_id']}")]
             ,[InlineKeyboardButton(text="📞", callback_data=f"talk_{r['user_id']}")]]
        await c.message.answer(f"📝 {r['fio']} (@{r['username']})", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await c.answer()

@dp.callback_query(F.data.startswith("talk_"))
async def talk(c: types.CallbackQuery, state: FSMContext): 
    await state.update_data(trg=c.data.split("_")[1]); await c.message.answer("Введите вопрос кандидату:"); await state.set_state(AdminHR.text); await c.answer()
@dp.message(AdminHR.text)
async def ts(m: types.Message, state: FSMContext):
    d = await state.get_data(); await safe_send(d['trg'], f"🤝 <b>Собеседование:</b>\n{m.text}"); await m.answer("Отправлено."); await state.clear()

@dp.callback_query(F.data.startswith("ok_"))
async def aok(c: types.CallbackQuery):
    did = c.data.split("_")[1]
    with get_db_connection() as con: con.execute("UPDATE drivers SET status='active' WHERE user_id=?", (did,))
    await c.answer("Принято!"); await safe_send(did, "✅ <b>Заявка одобрена!</b>\nТеперь вы полноценный Ямщик.")

@dp.callback_query(F.data.startswith("no_"))
async def ano(c: types.CallbackQuery):
    did = c.data.split("_")[1]
    with get_db_connection() as con: con.execute("DELETE FROM drivers WHERE user_id=?", (did,))
    await c.answer("Удалено"); await safe_send(did, "❌ Ваша заявка отклонена.")

@dp.callback_query(F.data == "adm_list")
async def al(c: types.CallbackQuery, state: FSMContext):
    await state.clear()
    with get_db_connection() as con: ds = con.execute("SELECT user_id, fio, status FROM drivers WHERE role!='owner'").fetchall()
    if not ds:
        await c.answer()
        return await c.message.answer("Список ямщиков пуст.")
    for d in ds:
        kb = [[InlineKeyboardButton(text="Блок", callback_data=f"blk_{d['user_id']}"), InlineKeyboardButton(text="Разблок", callback_data=f"unl_{d['user_id']}")]
             ,[InlineKeyboardButton(text="Письмо", callback_data=f"msg_{d['user_id']}")]]
        await c.message.answer(f"👤 {d['fio']} | {d['status']}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await c.answer()

@dp.callback_query(F.data.startswith("blk_"))
async def blk(c: types.CallbackQuery):
    with get_db_connection() as con: con.execute("UPDATE drivers SET status='blocked' WHERE user_id=?", (c.data.split("_")[1],))
    await c.answer("Заблокирован")
@dp.callback_query(F.data.startswith("unl_"))
async def unl(c: types.CallbackQuery):
    with get_db_connection() as con: con.execute("UPDATE drivers SET status='active' WHERE user_id=?", (c.data.split("_")[1],))
    await c.answer("Разблокирован")
@dp.callback_query(F.data.startswith("msg_"))
async def ams(c: types.CallbackQuery, state: FSMContext): await state.update_data(trg=c.data.split("_")[1]); await c.message.answer("Текст письма:"); await state.set_state(AdminMsg.text); await c.answer()
@dp.message(AdminMsg.text)
async def amss(m: types.Message, state: FSMContext):
    d = await state.get_data(); await safe_send(d['trg'], f"✉️ <b>АДМИН:</b> {m.text}"); await m.answer("Ушло."); await state.clear()
@dp.callback_query(F.data == "adm_cast")
async def cast(c: types.CallbackQuery, state: FSMContext): 
    await state.clear()
    await c.message.answer("Введите текст рассылки:"); await state.set_state("bc"); await c.answer()
@dp.message(F.state == "bc")
async def casts(m: types.Message, state: FSMContext):
    with get_db_connection() as con: us = con.execute("SELECT user_id FROM clients UNION SELECT user_id FROM drivers").fetchall()
    for u in us: await safe_send(u[0], f"📢 {m.text}"); 
    await m.answer("Разослано."); await state.clear()

@dp.callback_query(F.data == "back")
async def bck(c: types.CallbackQuery, state: FSMContext): await state.clear(); await c.message.delete(); await cab(c.message, state)

@dp.message(Command("drive"))
async def reg(m: types.Message, state: FSMContext):
    await state.clear()
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
        with get_db_connection() as con:
            con.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, vip_code, status) VALUES (?,?,?,?,?,?,?, 'pending')",
                        (m.from_user.id, m.from_user.username, d['fio'], d['car'], d['pay'], d['c1'], m.text.upper()))
        await m.answer("📜 Заявка отправлена!")
        await safe_send(OWNER_ID, f"🔔 ЗАЯВКА!\n{d['fio']}")
    except: await m.answer("❌ Коды заняты.")
    await state.clear()

@dp.callback_query(F.data.startswith("fin_"))
async def fin(c: types.CallbackQuery):
    cid = int(c.data.split("_")[1])
    with get_db_connection() as con: con.execute("UPDATE clients SET linked_driver_id=NULL WHERE user_id=?", (cid,))
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
