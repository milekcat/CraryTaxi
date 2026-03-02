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
# 📜 УСЛУГИ И КАТЕГОРИИ
# ==========================================
# Safe: Малые, Средние, Светские
# Wild (VIP): Большие, Дикие
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
# 🗄️ БАЗА ДАННЫХ (ОБНОВЛЕННАЯ СТРУКТУРА)
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Таблица водителей (с двумя кодами)
    cur.execute("""CREATE TABLE IF NOT EXISTS drivers (
        user_id INTEGER PRIMARY KEY, username TEXT, fio TEXT, car_info TEXT, payment_info TEXT, 
        access_code TEXT UNIQUE, vip_code TEXT UNIQUE, 
        status TEXT DEFAULT 'pending', role TEXT DEFAULT 'driver', balance INTEGER DEFAULT 0, lat REAL, lon REAL)""")
    
    # Миграция колонок
    cur.execute("PRAGMA table_info(drivers)")
    cols = [c[1] for c in cur.fetchall()]
    if 'vip_code' not in cols: cur.execute("ALTER TABLE drivers ADD COLUMN vip_code TEXT UNIQUE")
    if 'lat' not in cols: cur.execute("ALTER TABLE drivers ADD COLUMN lat REAL")

    # Таблица отключенных услуг (driver_id, service_key)
    cur.execute("CREATE TABLE IF NOT EXISTS disabled_services (driver_id INTEGER, service_key TEXT, PRIMARY KEY(driver_id, service_key))")
    
    # Таблица личных услуг (с категорией)
    cur.execute("CREATE TABLE IF NOT EXISTS custom_services (id INTEGER PRIMARY KEY AUTOINCREMENT, driver_id INTEGER, name TEXT, description TEXT, price INTEGER, category TEXT)")
    # Миграция категории
    cur.execute("PRAGMA table_info(custom_services)")
    cols_cust = [c[1] for c in cur.fetchall()]
    if 'category' not in cols_cust: cur.execute("ALTER TABLE custom_services ADD COLUMN category TEXT DEFAULT 'Личные'")

    # Таблица клиентов (хранит уровень доступа: 'std' или 'vip')
    cur.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, linked_driver_id INTEGER DEFAULT NULL, access_level TEXT DEFAULT 'std')")
    cur.execute("PRAGMA table_info(clients)")
    cols_cli = [c[1] for c in cur.fetchall()]
    if 'access_level' not in cols_cli: cur.execute("ALTER TABLE clients ADD COLUMN access_level TEXT DEFAULT 'std'")

    # Админ
    cur.execute("INSERT OR IGNORE INTO drivers (user_id, fio, access_code, vip_code, status, role) VALUES (?, 'СТАРОСТА', 'ADMIN', 'ADMIN_VIP', 'active', 'owner')", (OWNER_ID,))
    cur.execute("UPDATE drivers SET role='owner', status='active' WHERE user_id=?", (OWNER_ID,))
    conn.commit(); conn.close()

init_db()

# ==========================================
# 📡 WEB API (ФИЛЬТРАЦИЯ ПО КОДАМ И НАСТРОЙКАМ)
# ==========================================
async def get_services(request):
    uid = int(request.query.get('user_id', 0))
    with sqlite3.connect(DB_PATH) as con:
        # Получаем данные клиента (к кому привязан, какой уровень доступа)
        cli = con.execute("SELECT linked_driver_id, access_level FROM clients WHERE user_id=?", (uid,)).fetchone()
        
        # Если не привязан к водителю (заказ на биржу) - показываем только БАЗОВЫЕ (безопасные) услуги
        if not cli or not cli[0]:
            res = []
            for k, v in CRAZY_SERVICES.items():
                if v['cat'] not in CATEGORIES_VIP: # Только безопасные для биржи
                    res.append(v)
            return web.json_response(res)
        
        did = cli[0]
        access_level = cli[1] # 'std' или 'vip'

        # Получаем список отключенных водителем услуг
        disabled = [r[0] for r in con.execute("SELECT service_key FROM disabled_services WHERE driver_id=?", (did,)).fetchall()]
        
        # Получаем личные услуги водителя
        customs = con.execute("SELECT name, description, price, category FROM custom_services WHERE driver_id=?", (did,)).fetchall()
    
    final_list = []

    # 1. Фильтруем стандартные услуги
    for key, srv in CRAZY_SERVICES.items():
        if key in disabled: continue # Водитель отключил
        if access_level != 'vip' and srv['cat'] in CATEGORIES_VIP: continue # Клиент ввел обычный код, а услуга VIP
        
        srv_data = srv.copy()
        srv_data['id'] = key # Для идентификации
        final_list.append(srv_data)

    # 2. Фильтруем личные услуги
    for c in customs:
        # Личные услуги доступны:
        # - Если уровень VIP (всегда)
        # - Если уровень STD, но категория услуги не VIP
        cat = c[3]
        if access_level != 'vip' and cat in CATEGORIES_VIP: continue
        
        final_list.append({"name": c[0], "desc": c[1], "price": c[2], "cat": cat})

    return web.json_response(final_list)

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
        order_id = f"m_{uid}_{int(datetime.now().timestamp())}"
        market_orders[order_id] = {"uid": uid, "srv": srv, "price": price, "map": map_url}
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✋ ЗАБРАТЬ", callback_data=f"take_{order_id}")]])
        
        with sqlite3.connect(DB_PATH) as con: drivers = con.execute("SELECT user_id FROM drivers WHERE status='active' AND role!='owner'").fetchall()
        cnt = 0
        for d in drivers:
            try: 
                await bot.send_message(d[0], f"📥 <b>БИРЖА:</b> {srv} ({price}₽)", reply_markup=kb)
                cnt += 1
            except: pass
        return web.json_response({"status": "ok_market" if cnt > 0 else "no_active_drivers"})

# ==========================================
# 🤖 ЛОГИКА БОТА
# ==========================================
class DriverReg(StatesGroup): fio=State(); car=State(); pay=State(); code1=State(); code2=State()
class CustomSrv(StatesGroup): name=State(); desc=State(); price=State(); cat=State()
class ChangeCodes(StatesGroup): c1=State(); c2=State()
class AdminMsg(StatesGroup): text=State()
class AdminHR(StatesGroup): text=State()

# --- ПРИВЯЗКА КОДА (ПРОВЕРКА 2-Х КОДОВ) ---
@dp.message(F.text == "🔑 Код Ямщика")
async def link_ask(m: types.Message): await m.answer("Введите код ямщика:")

@dp.message(lambda x: len(x.text) > 0 and not x.text.startswith("/"))
async def process_code(m: types.Message):
    code = m.text.strip().upper()
    with sqlite3.connect(DB_PATH) as con:
        # Ищем совпадение по любому из кодов
        drv = con.execute("SELECT user_id, fio, access_code, vip_code FROM drivers WHERE (access_code=? OR vip_code=?) AND status='active'", (code, code)).fetchone()
    
    if drv:
        did, name, c1, c2 = drv
        level = 'vip' if code == c2 else 'std' # Определяем уровень
        type_str = "👑 VIP-ДОСТУП" if level == 'vip' else "👤 ОБЫЧНЫЙ ДОСТУП"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ДА, МОЙ", callback_data=f"pass_yes_{m.from_user.id}_{level}"),
             InlineKeyboardButton(text="⛔ НЕТ", callback_data=f"pass_no_{m.from_user.id}")]])
        
        await safe_send(did, f"🚨 <b>ПРОВЕРКА!</b>\nПассажир ввел код: {code} ({type_str})\nОн у вас в машине?", kb)
        await m.answer(f"⏳ <b>Ожидаем подтверждения...</b>\nТип доступа: {type_str}")
    else: pass # Игнор, если не код

@dp.callback_query(F.data.startswith("pass_yes_"))
async def pass_yes(call: types.CallbackQuery):
    _, _, cid, level = call.data.split("_")
    did = call.from_user.id
    with sqlite3.connect(DB_PATH) as con:
        con.execute("UPDATE clients SET linked_driver_id=?, access_level=? WHERE user_id=?", (did, level, cid))
    await call.message.edit_text(f"✅ <b>Пассажир принят!</b>\nУровень: {level.upper()}")
    await safe_send(cid, "🎉 <b>Доступ открыт!</b> Меню обновлено.")

@dp.callback_query(F.data.startswith("pass_no_"))
async def pass_no(call: types.CallbackQuery):
    cid = call.data.split("_")[2]
    await call.message.edit_text("⛔ <b>Отказ.</b>"); await safe_send(cid, "🚫 Ямщик отклонил вход.")

# --- УПРАВЛЕНИЕ УСЛУГАМИ (ТУМБЛЕРЫ) ---
@dp.callback_query(F.data == "menu_toggles")
async def menu_toggles(call: types.CallbackQuery):
    did = call.from_user.id
    with sqlite3.connect(DB_PATH) as con:
        disabled = [r[0] for r in con.execute("SELECT service_key FROM disabled_services WHERE driver_id=?", (did,)).fetchall()]
    
    kb = []
    # Группируем по категориям для удобства? Нет, слишком длинно. Просто список.
    for k, v in CRAZY_SERVICES.items():
        state = "🔴" if k in disabled else "🟢"
        kb.append([InlineKeyboardButton(text=f"{state} {v['name']}", callback_data=f"tgl_{k}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="cab_back")])
    
    await call.message.edit_text("🎛 <b>УПРАВЛЕНИЕ РЕПЕРТУАРОМ</b>\nНажми, чтобы вкл/выкл услугу для клиентов.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("tgl_"))
async def toggle_srv(call: types.CallbackQuery):
    key = call.data.split("_")[1]
    did = call.from_user.id
    with sqlite3.connect(DB_PATH) as con:
        exists = con.execute("SELECT 1 FROM disabled_services WHERE driver_id=? AND service_key=?", (did, key)).fetchone()
        if exists:
            con.execute("DELETE FROM disabled_services WHERE driver_id=? AND service_key=?", (did, key)) # Включаем (удаляем из черного списка)
        else:
            con.execute("INSERT INTO disabled_services VALUES (?, ?)", (did, key)) # Выключаем
    await menu_toggles(call)

# --- ДОБАВЛЕНИЕ ЛИЧНОЙ УСЛУГИ С КАТЕГОРИЕЙ ---
@dp.callback_query(F.data == "add_custom")
async def add_cust(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Название услуги:"); await state.set_state(CustomSrv.name)
@dp.message(CustomSrv.name)
async def cn(m: types.Message, state: FSMContext):
    await state.update_data(name=m.text); await m.answer("Описание:"); await state.set_state(CustomSrv.desc)
@dp.message(CustomSrv.desc)
async def cd(m: types.Message, state: FSMContext):
    await state.update_data(desc=m.text); await m.answer("Цена (число):"); await state.set_state(CustomSrv.price)
@dp.message(CustomSrv.price)
async def cp(m: types.Message, state: FSMContext):
    if not m.text.isdigit(): return
    await state.update_data(price=int(m.text))
    # Выбор категории
    kb = []
    cats = ["Малые", "Средние", "Большие", "Дикие", "Светские"]
    for c in cats: kb.append([KeyboardButton(text=c)])
    await m.answer("Выберите категорию (Дикие и Большие видны только по VIP коду):", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))
    await state.set_state(CustomSrv.cat)

@dp.message(CustomSrv.cat)
async def cc(m: types.Message, state: FSMContext):
    d = await state.get_data()
    with sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT INTO custom_services (driver_id, name, description, price, category) VALUES (?,?,?,?,?)",
                    (m.from_user.id, d['name'], d['desc'], d['price'], m.text))
    await m.answer("✅ Услуга добавлена!", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="👤 Моя Светлица")]], resize_keyboard=True))
    await state.clear()

# --- СМЕНА КОДОВ ---
@dp.callback_query(F.data == "settings")
async def settings(call: types.CallbackQuery):
    kb = [[InlineKeyboardButton(text="🔑 Сменить коды", callback_data="chg_codes")], [InlineKeyboardButton(text="🔙 Назад", callback_data="cab_back")]]
    await call.message.edit_text("⚙️ <b>НАСТРОЙКИ</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "chg_codes")
async def chg_codes(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Введите новый ОБЫЧНЫЙ код (для всех):"); await state.set_state(ChangeCodes.c1)
@dp.message(ChangeCodes.c1)
async def chg_c1(m: types.Message, state: FSMContext):
    await state.update_data(c1=m.text.upper()); await m.answer("Введите новый VIP код (для своих):"); await state.set_state(ChangeCodes.c2)
@dp.message(ChangeCodes.c2)
async def chg_c2(m: types.Message, state: FSMContext):
    d = await state.get_data()
    try:
        with sqlite3.connect(DB_PATH) as con:
            con.execute("UPDATE drivers SET access_code=?, vip_code=? WHERE user_id=?", (d['c1'], m.text.upper(), m.from_user.id))
        await m.answer(f"✅ <b>Коды обновлены!</b>\nОбычный: {d['c1']}\nVIP: {m.text.upper()}")
    except: await m.answer("❌ Один из кодов уже занят.")
    await state.clear()

# --- РЕГИСТРАЦИЯ (ОБНОВЛЕННАЯ - 2 КОДА) ---
@dp.message(Command("drive"))
async def reg_start(m: types.Message, state: FSMContext):
    if get_driver(m.from_user.id): return await m.answer("Уже в системе.")
    await m.answer("ФИО?"); await state.set_state(DriverReg.fio)
@dp.message(DriverReg.fio)
async def rf(m: types.Message, state: FSMContext):
    await state.update_data(fio=m.text); await m.answer("Авто?"); await state.set_state(DriverReg.car)
@dp.message(DriverReg.car)
async def rc(m: types.Message, state: FSMContext):
    await state.update_data(car=m.text); await m.answer("Реквизиты?"); await state.set_state(DriverReg.pay)
@dp.message(DriverReg.pay)
async def rp(m: types.Message, state: FSMContext):
    await state.update_data(pay=m.text); await m.answer("Придумайте ПУБЛИЧНЫЙ код (для всех):"); await state.set_state(DriverReg.code1)
@dp.message(DriverReg.code1)
async def rc1(m: types.Message, state: FSMContext):
    await state.update_data(c1=m.text.upper()); await m.answer("Придумайте VIP код (для особых гостей):"); await state.set_state(DriverReg.code2)
@dp.message(DriverReg.code2)
async def rc2(m: types.Message, state: FSMContext):
    d = await state.get_data()
    try:
        with sqlite3.connect(DB_PATH) as con:
            con.execute("INSERT INTO drivers (user_id, username, fio, car_info, payment_info, access_code, vip_code, status) VALUES (?,?,?,?,?,?,?, 'pending')",
                        (m.from_user.id, m.from_user.username, d['fio'], d['car'], d['pay'], d['c1'], m.text.upper()))
        await m.answer("📜 Заявка отправлена!")
        await safe_send(OWNER_ID, f"🔔 <b>ЗАЯВКА!</b>\n{d['fio']}\nКод 1: {d['c1']}\nКод 2: {m.text.upper()}")
    except: await m.answer("❌ Коды заняты.")
    await state.clear()

# --- КАБИНЕТ (С КНОПКАМИ НАСТРОЕК) ---
@dp.message(F.text == "👤 Моя Светлица")
async def cabinet(m: types.Message):
    uid = m.from_user.id
    if uid == OWNER_ID:
        kb = [[InlineKeyboardButton(text="📥 Заявки", callback_data="adm_reqs")],
              [InlineKeyboardButton(text="📋 Ямщики", callback_data="adm_list")],
              [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_cast")]]
        return await m.answer("👑 <b>АДМИНКА</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    
    drv = get_driver(uid)
    if drv and drv[6] == 'active':
        # drv: 2=fio, 5=code1, 6=vip
        vip_c = drv[6] if drv[6] else "Нет"
        kb = [[InlineKeyboardButton(text="🎛 Репертуар (Вкл/Выкл)", callback_data="menu_toggles")],
              [InlineKeyboardButton(text="➕ Своя услуга", callback_data="add_custom")],
              [InlineKeyboardButton(text="⚙️ Настройки кодов", callback_data="settings")]]
        await m.answer(f"🪪 <b>ЯМЩИК: {drv[2]}</b>\n🔑 Код (Публичный): <code>{drv[5]}</code>\n💎 Код (VIP): <code>{vip_c}</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return
    await m.answer("👤 <b>КАБИНЕТ ПАССАЖИРА</b>")

# --- СЛУЖЕБНЫЕ (АДМИН, ЗАКАЗЫ) ---
# (Сокращаю только стандартные, логика не менялась)
@dp.callback_query(F.data=="cab_back")
async def back(c: types.CallbackQuery): await c.message.delete(); await cabinet(c.message)
@dp.callback_query(F.data=="adm_reqs")
async def ar(c: types.CallbackQuery):
    with sqlite3.connect(DB_PATH) as con: rs=con.execute("SELECT user_id,fio FROM drivers WHERE status='pending'").fetchall()
    if not rs: return await c.message.answer("Пусто.")
    for r in rs: 
        kb=[[InlineKeyboardButton(text="✅", callback_data=f"ok_{r[0]}"), InlineKeyboardButton(text="❌", callback_data=f"no_{r[0]}")]]
        await c.message.answer(f"📝 {r[1]}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
@dp.callback_query(F.data.startswith("ok_"))
async def aok(c: types.CallbackQuery): 
    did=c.data.split("_")[1]
    with sqlite3.connect(DB_PATH) as con: con.execute("UPDATE drivers SET status='active' WHERE user_id=?", (did,))
    await c.answer("Ок"); await safe_send(did, "✅ Принят!")
@dp.callback_query(F.data.startswith("no_"))
async def ano(c: types.CallbackQuery):
    did=c.data.split("_")[1]
    with sqlite3.connect(DB_PATH) as con: con.execute("DELETE FROM drivers WHERE user_id=?", (did,))
    await c.answer("Нет"); await safe_send(did, "❌ Отказ")

# --- UTILS & STARTUP ---
def get_driver(uid): 
    with sqlite3.connect(DB_PATH) as con: return con.execute("SELECT * FROM drivers WHERE user_id=?", (uid,)).fetchone()
async def safe_send(chat_id, text, kb=None):
    try: await bot.send_message(chat_id, text, reply_markup=kb); return True
    except: return False
async def on_startup(app): await bot.delete_webhook(drop_pending_updates=True); asyncio.create_task(dp.start_polling(bot))
def main():
    app = web.Application(); app.router.add_get('/', lambda r: web.FileResponse(HTML_FILE))
    app.router.add_get('/get_services', get_services); app.router.add_post('/webapp_order', web_order)
    app.on_startup.append(on_startup); web.run_app(app, host='0.0.0.0', port=8080)

if __name__ == "__main__": main()
