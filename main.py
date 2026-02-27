import asyncio
import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties

# Включаем логирование
logging.basicConfig(level=logging.INFO)

# Переменные окружения (Amvera)
API_TOKEN = os.getenv("API_TOKEN")
BOSS_ID = os.getenv("DRIVER_ID") # Теперь это ID главного админа (тебя)

if not API_TOKEN or not BOSS_ID:
    logging.error("ВНИМАНИЕ: API_TOKEN или DRIVER_ID не найдены!")

BOSS_ID = int(BOSS_ID)

# Инициализация бота
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ==========================================
# 🗄️ БАЗА ДАННЫХ SQLITE
# ==========================================
def init_db():
    conn = sqlite3.connect("taxi_db.sqlite")
    cursor = conn.cursor()
    # Таблица водителей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            car_info TEXT,
            payment_info TEXT,
            status TEXT DEFAULT 'pending', -- pending, active, blocked
            balance INTEGER DEFAULT 0 -- Долг по комиссии
        )
    """)
    # Таблица клиентов (принявших правила)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            user_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

init_db() # Создаем базу при запуске

# Вспомогательные функции для работы с БД
def is_client_accepted(user_id):
    conn = sqlite3.connect("taxi_db.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM clients WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return bool(result)

def accept_client_tos(user_id):
    conn = sqlite3.connect("taxi_db.sqlite")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO clients (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_driver(user_id):
    conn = sqlite3.connect("taxi_db.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT status, car_info, payment_info, balance FROM drivers WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result

# --- СОСТОЯНИЯ FSM ---
class DriverRegistration(StatesGroup):
    waiting_for_car = State()
    waiting_for_payment_info = State()

# --- КЛАВИАТУРЫ ---
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚕 Заказать такси (Торг)")],
        [KeyboardButton(text="📜 CRAZY ХАОС-МЕНЮ")],
        [KeyboardButton(text="💡 Свой вариант (Предложить идею)")],
        [KeyboardButton(text="⚖️ Вызвать адвоката / Правила")]
    ],
    resize_keyboard=True
)

tos_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ ПОДПИСАТЬ КОНТРАКТ", callback_data="accept_tos")],
    [InlineKeyboardButton(text="❌ Я боюсь, пойду пешком", callback_data="decline_tos")]
])

# ==========================================
# 🛑 СТАРТ И ОТКАЗ ОТ ОТВЕТСТВЕННОСТИ (КЛИЕНТЫ)
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    disclaimer_text = (
        "⚠️ <b>ОФИЦИАЛЬНОЕ ПРЕДУПРЕЖДЕНИЕ</b> ⚠️\n\n"
        "ВНИМАНИЕ! Вы пытаетесь воспользоваться услугами <b>Crazy Taxi</b>.\n"
        "Салон этого автомобиля является юридически неприкосновенной зоной <b>Арт-перформанса</b>.\n\n"
        "<b>Нажимая «Подписать контракт», вы соглашаетесь с тем, что:</b>\n"
        "1. Любая дичь, происходящая внутри, классифицируется как 'современное искусство'.\n"
        "2. Вы заранее отказываетесь от любых судебных исков и претензий на моральный ущерб.\n"
        "3. Наш адвокат слишком хорош — он однажды выиграл дело у здравого смысла. Судиться с нами бесполезно.\n"
        "4. Ваша поездка может внезапно стать стендапом, триллером или мюзиклом.\n\n"
        "<i>Готов шагнуть в зону абсолютной юридической анархии?</i>"
    )
    await message.answer(disclaimer_text, reply_markup=tos_kb)

@dp.callback_query(F.data == "accept_tos")
async def tos_accepted(callback: types.CallbackQuery):
    accept_client_tos(callback.from_user.id)
    await callback.message.edit_text("🔥 <b>ДОБРО ПОЖАЛОВАТЬ В CRAZY TAXI!</b> 🔥\nКонтракт подписан кровью (шутка, цифровой подписью).")
    await callback.message.answer("Выбирай действие в меню ниже 👇", reply_markup=main_kb)

@dp.callback_query(F.data == "decline_tos")
async def tos_declined(callback: types.CallbackQuery):
    await callback.message.edit_text("🚶‍♂️ Очень жаль! Законы улиц суровы, но безопасны. Удачной пешей прогулки!")

# ==========================================
# 🚦 РЕГИСТРАЦИЯ ВОДИТЕЛЕЙ (ФРАНШИЗА)
# ==========================================
@dp.message(Command("driver"))
async def cmd_driver_register(message: types.Message, state: FSMContext):
    driver_status = get_driver(message.from_user.id)
    
    if driver_status:
        status = driver_status[0]
        if status == 'active':
            await message.answer("✅ Ты уже в деле! Ожидай новые заказы.")
        elif status == 'pending':
            await message.answer("⏳ Твоя заявка на рассмотрении у Босса. Ожидай.")
        elif status == 'blocked':
            await message.answer("❌ Твой аккаунт заблокирован. Свяжись с Боссом для оплаты долга.")
        return

    await message.answer(
        "🚕 <b>РЕГИСТРАЦИЯ ВОДИТЕЛЯ CRAZY TAXI</b>\n\n"
        "Хочешь творить хаос и зарабатывать? Отлично!\n"
        "Напиши марку своей машины, цвет и госномер (Например: <i>Желтый Kia Rio, А123ВВ76</i>):"
    )
    await state.set_state(DriverRegistration.waiting_for_car)

@dp.message(DriverRegistration.waiting_for_car)
async def process_car_info(message: types.Message, state: FSMContext):
    await state.update_data(car_info=message.text)
    await message.answer(
        "💳 Отлично. Теперь напиши свои <b>реквизиты для получения оплат от клиентов</b> (Например: <i>Сбербанк/Тинькофф +79991234567 Иван И.</i>):"
    )
    await state.set_state(DriverRegistration.waiting_for_payment_info)

@dp.message(DriverRegistration.waiting_for_payment_info)
async def process_payment_info(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    car_info = user_data['car_info']
    payment_info = message.text
    user_id = message.from_user.id
    username = message.from_user.username or "Без юзернейма"

    # Сохраняем заявку в БД со статусом 'pending'
    conn = sqlite3.connect("taxi_db.sqlite")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO drivers (user_id, username, car_info, payment_info, status) VALUES (?, ?, ?, ?, 'pending')",
        (user_id, username, car_info, payment_info)
    )
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(
        "📝 Заявка отправлена Боссу!\n\n"
        "⚠️ <b>ВНИМАНИЕ:</b> Для активации аккаунта предусмотрен стартовый взнос.\n"
        "Ожидай решения администрации."
    )

    # Уведомляем Босса (тебя)
    admin_text = (
        f"🚨 <b>НОВАЯ ЗАЯВКА ВОДИТЕЛЯ</b> 🚨\n\n"
        f"👤 @{username} (ID: <code>{user_id}</code>)\n"
        f"🚗 Авто: {car_info}\n"
        f"💳 Реквизиты: {payment_info}\n\n"
        f"<i>Прими решение о допуске:</i>"
    )
    
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"adm_approve_{user_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_reject_{user_id}")]
    ])
    
    await bot.send_message(chat_id=BOSS_ID, text=admin_text, reply_markup=admin_kb)

# ==========================================
# 👑 АДМИН-ПАНЕЛЬ БОССА
# ==========================================
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != BOSS_ID:
        return # Игнорируем всех, кроме тебя

    conn = sqlite3.connect("taxi_db.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM drivers WHERE status='active'")
    active_count = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(balance) FROM drivers")
    total_debt = cursor.fetchone()[0] or 0
    conn.close()

    admin_text = (
        "👑 <b>КАБИНЕТ БОССА</b> 👑\n\n"
        f"🟢 Активных водителей: <b>{active_count}</b>\n"
        f"💰 Общий долг водителей: <b>{total_debt}₽</b>\n\n"
        "<i>Используй кнопки ниже для управления сетью:</i>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Список водителей", callback_data="adm_list_drivers")],
        [InlineKeyboardButton(text="💸 Выставить счета всем", callback_data="adm_invoice_all")]
    ])
    
    await message.answer(admin_text, reply_markup=kb)

# Одобрение заявки Боссом
@dp.callback_query(F.data.startswith("adm_approve_"))
async def admin_approve_driver(callback: types.CallbackQuery):
    if callback.from_user.id != BOSS_ID: return
    
    driver_id = int(callback.data.split("_")[2])
    
    conn = sqlite3.connect("taxi_db.sqlite")
    cursor = conn.cursor()
    cursor.execute("UPDATE drivers SET status='active' WHERE user_id=?", (driver_id,))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(f"✅ Водитель {driver_id} <b>ОДОБРЕН</b> и добавлен в сеть.")
    
    try:
        await bot.send_message(
            chat_id=driver_id, 
            text="🎉 <b>ТВОЯ ЗАЯВКА ОДОБРЕНА!</b>\nДобро пожаловать во франшизу Crazy Taxi. Теперь ты будешь получать заказы от клиентов."
        )
    except: pass

# Отклонение заявки Боссом
@dp.callback_query(F.data.startswith("adm_reject_"))
async def admin_reject_driver(callback: types.CallbackQuery):
    if callback.from_user.id != BOSS_ID: return
    
    driver_id = int(callback.data.split("_")[2])
    
    conn = sqlite3.connect("taxi_db.sqlite")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM drivers WHERE user_id=?", (driver_id,))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(f"❌ Водитель {driver_id} <b>ОТКЛОНЕН</b>.")
    try:
        await bot.send_message(chat_id=driver_id, text="❌ К сожалению, Босс отклонил твою заявку в Crazy Taxi.")
    except: pass


# Заглушка для меню, чтобы бот не выдавал ошибок, пока мы пишем вторую часть
@dp.message(F.text.in_(["📜 CRAZY ХАОС-МЕНЮ", "💡 Свой вариант (Предложить идею)", "🚕 Заказать такси (Торг)"]))
async def temp_menu_stub(message: types.Message):
    if not is_client_accepted(message.from_user.id):
        await message.answer("Сначала нужно принять правила! Нажми /start")
        return
    await message.answer("🛠 Раздел в процессе перенастройки для работы сети водителей. Скоро вернется!")


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
