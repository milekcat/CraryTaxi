import asyncio
import logging
import os
import sqlite3
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties

logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("API_TOKEN")
BOSS_ID = os.getenv("DRIVER_ID") # Твой ID как владельца сети

if not API_TOKEN or not BOSS_ID:
    logging.error("ВНИМАНИЕ: API_TOKEN или DRIVER_ID не найдены!")

BOSS_ID = int(BOSS_ID)
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

active_orders = {} # Память для текущих заказов

# ==========================================
# 🗄️ БАЗА ДАННЫХ И КОМИССИЯ
# ==========================================
def init_db():
    conn = sqlite3.connect("taxi_db.sqlite")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            car_info TEXT,
            payment_info TEXT,
            status TEXT DEFAULT 'pending',
            balance INTEGER DEFAULT 0
        )
    """)
    cursor.execute("CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

init_db()

def get_active_drivers():
    conn = sqlite3.connect("taxi_db.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM drivers WHERE status='active'")
    drivers = cursor.fetchall()
    conn.close()
    return [d[0] for d in drivers]

def get_driver_info(user_id):
    conn = sqlite3.connect("taxi_db.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT username, car_info, payment_info, balance FROM drivers WHERE user_id=?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res

def add_commission(driver_id, amount):
    commission = int(amount * 0.10)
    if commission <= 0: return # За конфетку комиссию не берем :)
    conn = sqlite3.connect("taxi_db.sqlite")
    cursor = conn.cursor()
    cursor.execute("UPDATE drivers SET balance = balance + ? WHERE user_id=?", (commission, driver_id))
    conn.commit()
    conn.close()

def is_client_accepted(user_id):
    conn = sqlite3.connect("taxi_db.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM clients WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return bool(result)

# --- БАЗА УСЛУГ И КЛАВИАТУРЫ (ОБНОВЛЕННАЯ С МИЛЫМИ ОПЦИЯМИ) ---
CRAZY_SERVICES = {
    "candy": {"name": "🍬 Конфетка", "price": 0, "desc": "Водитель торжественно вручит вам вкусную конфетку и пожелает хорошего дня. Мелочь, а приятно!"},
    "joke": {"name": "🎭 Анекдот", "price": 50, "desc": "Водитель расскажет анекдот из своей золотой коллекции. За качество юмора ответственность не несем!"},
    "poem": {"name": "📜 Стих с выражением", "price": 100, "desc": "Прочту стихотворение с чувством, с толком, с расстановкой. Как на утреннике в детском саду."},
    "sleep": {"name": "🛌 Сон под шепот ям", "price": 150, "desc": "Аккуратная езда, расслабляющая музыка, водитель молчит как рыба."},
    "tale": {"name": "📖 Сказка на ночь", "price": 300, "desc": "Водитель расскажет захватывающую историю из жизни таксиста."},
    "dance": {"name": "🕺 Танцы на светофоре", "price": 15000, "desc": "Красный свет? Я выхожу из машины и танцую безумный танец!"},
    "burn": {"name": "🔥 Сжечь машину", "price": 1000000, "desc": "Приезжаем на пустырь, ты даешь лям, я даю канистру. Гори оно всё огнем."}
}

class OrderRide(StatesGroup):
    waiting_for_from = State()
    waiting_for_to = State()
    waiting_for_price = State()

class DriverOffer(StatesGroup):
    waiting_for_offer = State()

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚕 Заказать такси (Торг)")],
        [KeyboardButton(text="📜 CRAZY ХАОС-МЕНЮ")]
    ], resize_keyboard=True
)

# ==========================================
# 🛑 СТАРТ И ФРАНШИЗА
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not is_client_accepted(message.from_user.id):
        conn = sqlite3.connect("taxi_db.sqlite")
        conn.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (message.from_user.id,))
        conn.commit()
        conn.close()
    await message.answer("🔥 <b>ДОБРО ПОЖАЛОВАТЬ В СЕТЬ CRAZY TAXI!</b> 🔥\nВыбирай услугу:", reply_markup=main_kb)

@dp.message(Command("driver"))
async def cmd_driver_register(message: types.Message):
    await message.answer("Для регистрации водителя отправь Боссу свои данные в личку.")

# ==========================================
# 🚀 РАССЫЛКА ЗАКАЗОВ ВОДИТЕЛЯМ
# ==========================================
async def broadcast_order_to_drivers(client_id, order_text, reply_markup):
    drivers = get_active_drivers()
    if not drivers:
        await bot.send_message(client_id, "😔 Сейчас нет свободных Crazy-водителей. Попробуй позже!")
        return
    
    for d_id in drivers:
        try:
            await bot.send_message(chat_id=d_id, text=order_text, reply_markup=reply_markup)
        except Exception as e:
            logging.error(f"Не удалось отправить водителю {d_id}: {e}")

# ==========================================
# 📜 CRAZY ХАОС-МЕНЮ И ЛОГИКА ОПЛАТЫ
# ==========================================
@dp.message(F.text == "📜 CRAZY ХАОС-МЕНЮ")
async def show_crazy_menu(message: types.Message):
    buttons = []
    # Располагаем кнопки по две в ряд для красоты
    keys = list(CRAZY_SERVICES.keys())
    for i in range(0, len(keys), 2):
        row = []
        for key in keys[i:i+2]:
            data = CRAZY_SERVICES[key]
            price_text = "БЕСПЛАТНО" if data['price'] == 0 else f"{data['price']}₽"
            row.append(InlineKeyboardButton(text=f"{data['name']} ({price_text})", callback_data=f"csel_{key}"))
        buttons.append(row)
        
    await message.answer("🔥 <b>CRAZY DRIVER'S CHAOS MENU</b> 🔥\n\nВыбирай приключение:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("csel_"))
async def process_crazy_selection(callback: types.CallbackQuery):
    service_key = callback.data.split("_")[1]
    service = CRAZY_SERVICES[service_key]
    client_id = callback.from_user.id
    
    active_orders[client_id] = {"type": "crazy", "service": service, "status": "pending", "price": service["price"]}
    
    price_text = "БЕСПЛАТНО" if service["price"] == 0 else f"{service['price']}₽"
    
    await callback.message.edit_text(f"🎪 <b>ВЫБРАНА УСЛУГА:</b> {service['name']}\n📝 <b>Описание:</b> {service['desc']}\n💰 <b>Стоимость:</b> {price_text}\n\n⏳ <i>Ищем водителя, готового на это...</i>")
    
    driver_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡️ ЗАБРАТЬ ЗАКАЗ", callback_data=f"take_crazy_{client_id}")]
    ])
    text = f"🚨 <b>ХАОС-ЗАКАЗ!</b> 🚨\nКлиент: @{callback.from_user.username}\nУслуга: <b>{service['name']}</b> ({price_text})\nКто первый?!"
    await broadcast_order_to_drivers(client_id, text, driver_kb)

@dp.callback_query(F.data.startswith("take_crazy_"))
async def driver_takes_crazy(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)

    if not order or order["status"] != "pending":
        await callback.answer("Упс! Этот заказ уже забрал другой водитель 🏎💨", show_alert=True)
        await callback.message.delete()
        return

    order["status"] = "accepted"
    order["driver_id"] = driver_id
    driver_info = get_driver_info(driver_id)
    
    await callback.message.edit_text(f"✅ Ты забрал заказ: {order['service']['name']}!")
    
    # УМНАЯ ПРОВЕРКА ЦЕНЫ (Если бесплатно - не просим реквизиты)
    if order['price'] == 0:
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ЖДУ СЮРПРИЗ!", callback_data=f"cpay_done_{client_id}")]])
        client_text = (
            f"🚕 <b>ВОДИТЕЛЬ НАЙДЕН!</b>\n"
            f"К тебе приедет: {driver_info[0]} ({driver_info[1]})\n\n"
            f"🎁 <b>Эта услуга абсолютно бесплатна!</b>\n\n"
            f"Жми кнопку ниже, чтобы водитель начал!"
        )
    else:
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Я ОПЛАТИЛ", callback_data=f"cpay_done_{client_id}")]])
        client_text = (
            f"🚕 <b>ВОДИТЕЛЬ НАЙДЕН!</b>\n"
            f"К тебе приедет: {driver_info[0]} ({driver_info[1]})\n\n"
            f"💳 <b>Переведи {order['price']}₽ на реквизиты:</b>\n<code>{driver_info[2]}</code>\n\n"
            f"Жми кнопку ниже после перевода!"
        )
        
    await bot.send_message(client_id, client_text, reply_markup=pay_kb)

@dp.callback_query(F.data.startswith("cpay_done_"))
async def client_paid_crazy(callback: types.CallbackQuery):
    client_id = callback.from_user.id
    order = active_orders.get(client_id)
    if not order: return
    
    # УМНАЯ ПРОВЕРКА ЦЕНЫ ДЛЯ ВОДИТЕЛЯ
    if order['price'] == 0:
        await callback.message.edit_text("⏳ Водитель готовится...")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ВЫПОЛНИЛ!", callback_data=f"confirm_pay_{client_id}")]
        ])
        await bot.send_message(order["driver_id"], f"🎁 Клиент @{callback.from_user.username} ждет свой бонус: <b>{order['service']['name']}</b>!\nСделай это и нажми кнопку.", reply_markup=kb)
    else:
        await callback.message.edit_text("⏳ Проверяем поступление средств...")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ДЕНЬГИ ПРИШЛИ (Начать)", callback_data=f"confirm_pay_{client_id}")]
        ])
        await bot.send_message(order["driver_id"], f"💸 Клиент @{callback.from_user.username} нажал 'Оплатил' за {order['service']['name']}.\nПроверь баланс {order['price']}₽ и подтверди!", reply_markup=kb)

@dp.callback_query(F.data.startswith("confirm_pay_"))
async def driver_confirms_pay(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    order = active_orders.get(client_id)
    
    if not order: return
    
    add_commission(driver_id, order['price'])
    
    if order['price'] == 0:
        await callback.message.edit_text("✅ Заказ выполнен! Ты красавчик.")
        await bot.send_message(client_id, "🎉 Водитель подтвердил! Надеюсь, тебе понравилось!")
    else:
        await callback.message.edit_text("✅ Оплата подтверждена! Комиссия 10% записана в твой долг. Выполняй заказ!")
        await bot.send_message(client_id, "🎉 Водитель подтвердил оплату! Шоу начинается 💨")
        
    del active_orders[client_id]

# ==========================================
# 👑 АДМИН-ПАНЕЛЬ БОССА (С УПРАВЛЕНИЕМ)
# ==========================================
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != BOSS_ID: return

    conn = sqlite3.connect("taxi_db.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, status, balance FROM drivers")
    all_drivers = cursor.fetchall()
    conn.close()

    text = "👑 <b>УПРАВЛЕНИЕ ФРАНШИЗОЙ</b> 👑\n\n"
    for d in all_drivers:
        status_emoji = "🟢" if d[2] == 'active' else "🔴" if d[2] == 'blocked' else "🟡"
        text += f"{status_emoji} <b>{d[1]}</b> (ID: {d[0]})\nДолг: <b>{d[3]}₽</b> | Статус: {d[2]}\n"
        text += f"Блок: /block_{d[0]} | Анблок: /unblock_{d[0]}\n---\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Запросить оплату долгов", callback_data="adm_invoice_all")]
    ])
    await message.answer(text, reply_markup=kb)

@dp.message(F.text.startswith("/block_"))
async def block_driver(message: types.Message):
    if message.from_user.id != BOSS_ID: return
    d_id = int(message.text.split("_")[1])
    conn = sqlite3.connect("taxi_db.sqlite")
    conn.execute("UPDATE drivers SET status='blocked' WHERE user_id=?", (d_id,))
    conn.commit()
    conn.close()
    await message.answer(f"✅ Водитель {d_id} заблокирован. Он больше не увидит заказы.")

@dp.message(F.text.startswith("/unblock_"))
async def unblock_driver(message: types.Message):
    if message.from_user.id != BOSS_ID: return
    d_id = int(message.text.split("_")[1])
    conn = sqlite3.connect("taxi_db.sqlite")
    conn.execute("UPDATE drivers SET status='active', balance=0 WHERE user_id=?", (d_id,))
    conn.commit()
    conn.close()
    await message.answer(f"✅ Водитель {d_id} разблокирован. Долг обнулен!")

@dp.callback_query(F.data == "adm_invoice_all")
async def invoice_all(callback: types.CallbackQuery):
    if callback.from_user.id != BOSS_ID: return
    conn = sqlite3.connect("taxi_db.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, balance FROM drivers WHERE balance > 0 AND status='active'")
    debtors = cursor.fetchall()
    conn.close()
    
    for d_id, debt in debtors:
        try:
            await bot.send_message(d_id, f"⚠️ <b>ВРЕМЯ ПЛАТИТЬ ПО СЧЕТАМ</b> ⚠️\nТвой долг по комиссии: <b>{debt}₽</b>.\nПереведи на реквизиты Босса (Яндекс Банк: +79012723729 Андрей И.), иначе отключим от сети!")
        except: pass
    await callback.answer("Счета разосланы должникам!", show_alert=True)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
