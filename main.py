import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# Включаем логирование
logging.basicConfig(level=logging.INFO)

# Получаем переменные окружения из Amvera
API_TOKEN = os.getenv("API_TOKEN")
DRIVER_ID = os.getenv("DRIVER_ID")

if not API_TOKEN or not DRIVER_ID:
    logging.error("ВНИМАНИЕ: API_TOKEN или DRIVER_ID не найдены в переменных!")

DRIVER_ID = int(DRIVER_ID)

# Инициализация бота
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher()

# Временное хранилище для заказов (чтобы бот помнил кто, куда и за сколько едет)
active_orders = {}

# --- СОСТОЯНИЯ FSM ---
class OrderRide(StatesGroup):
    waiting_for_from = State()
    waiting_for_to = State()
    waiting_for_price = State()

class DriverOffer(StatesGroup):
    waiting_for_offer = State()

# --- КЛАВИАТУРЫ ---
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚕 Заказать такси")],
        [KeyboardButton(text="📜 Меню Crazy-услуг")]
    ],
    resize_keyboard=True
)

# --- БАЗОВЫЕ КОМАНДЫ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Добро пожаловать в <b>Crazy Taxi</b> Ярославль! 🚕💨\n\n"
        "Выбирай: обычная поездка (но с сюрпризом) или наше фирменное Хаос-меню?",
        reply_markup=main_kb
    )

@dp.message(F.text == "📜 Меню Crazy-услуг")
async def crazy_menu(message: types.Message):
    text = (
        "🔥 <b>CRAZY DRIVER'S CHAOS MENU</b> 🔥\n\n"
        "🛌 Сон под шепот ям - 150₽\n"
        "🔞 Танцы на светофоре - 15 000₽\n"
        "🔥 Сжечь машину - 1 000 000₽\n\n"
        "Выбирай услугу ниже:"
    )
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Заказать 'Сон'", callback_data="crazy_sleep_150")],
        [InlineKeyboardButton(text="Заказать 'Танцы'", callback_data="crazy_dance_15000")],
        [InlineKeyboardButton(text="Заказать 'Сжечь авто'", callback_data="crazy_burn_1000000")]
    ])
    await message.answer(text, reply_markup=ikb)

# ==========================================
# 🚕 ЛОГИКА ЗАКАЗА ТАКСИ (КЛИЕНТ)
# ==========================================
@dp.message(F.text == "🚕 Заказать такси")
async def start_ride_order(message: types.Message, state: FSMContext):
    await message.answer("📍 <b>Откуда тебя забрать?</b> Напиши адрес (например: ул. Кирова, 10):", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(OrderRide.waiting_for_from)

@dp.message(OrderRide.waiting_for_from)
async def process_from_address(message: types.Message, state: FSMContext):
    await state.update_data(from_address=message.text)
    await message.answer("🏁 <b>Куда мчим?</b> Напиши адрес назначения:")
    await state.set_state(OrderRide.waiting_for_to)

@dp.message(OrderRide.waiting_for_to)
async def process_to_address(message: types.Message, state: FSMContext):
    await state.update_data(to_address=message.text)
    await message.answer("💰 <b>Сколько готов заплатить за поездку?</b> (Напиши сумму в рублях):")
    await state.set_state(OrderRide.waiting_for_price)

@dp.message(OrderRide.waiting_for_price)
async def process_price(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    client_id = message.from_user.id
    
    # Сохраняем заказ в памяти
    active_orders[client_id] = {
        "from": user_data['from_address'],
        "to": user_data['to_address'],
        "price": message.text,
        "username": message.from_user.username or "Без юзернейма",
        "offer": ""
    }

    await message.answer("⏳ <b>Заказ отправлен Crazy Водителю!</b> Ждем ответа...", reply_markup=main_kb)
    await state.clear()

    # Отправляем водителю
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{client_id}")],
        [InlineKeyboardButton(text="✍️ Предложить цену и время", callback_data=f"counter_{client_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{client_id}")]
    ])
    
    driver_text = (
        f"🔥 <b>НОВЫЙ ЗАКАЗ НА ТАКСИ</b> 🔥\n\n"
        f"👤 Клиент: @{active_orders[client_id]['username']}\n"
        f"📍 Откуда: {active_orders[client_id]['from']}\n"
        f"🏁 Куда: {active_orders[client_id]['to']}\n"
        f"💰 Предложенная цена: <b>{active_orders[client_id]['price']}₽</b>"
    )
    await bot.send_message(chat_id=DRIVER_ID, text=driver_text, reply_markup=keyboard)

# ==========================================
# 👨‍✈️ РЕАКЦИЯ ВОДИТЕЛЯ И ТОРГИ
# ==========================================
@dp.callback_query(F.data.startswith("reject_"))
async def driver_rejects(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[1])
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Заказ отклонен.")
    try:
        await bot.send_message(chat_id=client_id, text="😔 Водитель сейчас не может принять заказ. Попробуй позже!")
    except Exception:
        pass

@dp.callback_query(F.data.startswith("accept_"))
async def driver_accepts(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[1])
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Заказ принят!")
    
    order = active_orders.get(client_id, {})
    
    pay_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Оплатил, поехали!", callback_data=f"paid_{client_id}")]
    ])
    
    success_text = (
        f"🚕 <b>ВОДИТЕЛЬ ПРИНЯЛ ЗАКАЗ!</b>\n\n"
        f"📍 {order.get('from', '?')} ➡️ {order.get('to', '?')}\n"
        f"💰 Договоренная цена: <b>{order.get('price', '?')}</b>\n\n"
        f"💳 <b>Реквизиты для перевода:</b>\n"
        f" Яндекс Банк: <code>+79012723729</code> (Андрей Игоревич)\n\n" # <--- ВСТАВЬ ТУТ СВОЙ НОМЕР
        f"Жми кнопку ниже, когда переведешь!"
    )
    try:
        await bot.send_message(chat_id=client_id, text=success_text, reply_markup=pay_keyboard)
    except Exception:
        pass

@dp.callback_query(F.data.startswith("counter_"))
async def driver_counteroffer(callback: types.CallbackQuery, state: FSMContext):
    client_id = int(callback.data.split("_")[1])
    await state.update_data(target_client_id=client_id)
    
    await callback.message.answer("Напиши свою цену и время подачи (например: <code>500 руб, буду через 10 мин</code>):")
    await state.set_state(DriverOffer.waiting_for_offer)
    await callback.answer()

@dp.message(DriverOffer.waiting_for_offer)
async def send_offer_to_client(message: types.Message, state: FSMContext):
    data = await state.get_data()
    client_id = data.get('target_client_id')
    driver_offer = message.text
    
    if client_id in active_orders:
        active_orders[client_id]['offer'] = driver_offer
    
    client_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Согласен", callback_data=f"client_accept_{client_id}")],
        [InlineKeyboardButton(text="❌ Отказаться", callback_data=f"client_reject_{client_id}")]
    ])
    
    text_for_client = (
        f"⚡️ <b>Встречное предложение от водителя:</b>\n\n"
        f"{driver_offer}\n\n"
        f"Поедем?"
    )
    try:
        await bot.send_message(chat_id=client_id, text=text_for_client, reply_markup=client_keyboard)
        await message.answer("✅ Предложение отправлено клиенту!")
    except Exception:
        await message.answer("❌ Ошибка отправки. Возможно клиент заблокировал бота.")
        
    await state.clear()

# ==========================================
# 👤 ОТВЕТ КЛИЕНТА НА ТОРГ И ОПЛАТА
# ==========================================
@dp.callback_query(F.data.startswith("client_reject_"))
async def client_rejects(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Вы отказались от предложения. Будем ждать новых заказов!")
    await bot.send_message(chat_id=DRIVER_ID, text=f"❌ Клиент @{active_orders.get(client_id, {}).get('username', '')} отказался от твоих условий.")

@dp.callback_query(F.data.startswith("client_accept_"))
async def client_accepts_offer(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    await callback.message.edit_reply_markup(reply_markup=None)
    
    order = active_orders.get(client_id, {})
    
    pay_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Оплатил, поехали!", callback_data=f"paid_{client_id}")]
    ])
    
    success_text = (
        f"🚕 <b>ДОГОВОРИЛИСЬ!</b>\n\n"
        f"📍 {order.get('from', '?')} ➡️ {order.get('to', '?')}\n"
        f"Условия: <b>{order.get('offer', '?')}</b>\n\n"
        f"💳 <b>Реквизиты для перевода:</b>\n"
        f"Яндекс Банк: <code>+79012723729</code> (Андрей Игоревич)\n\n" # <--- ВСТАВЬ ТУТ СВОЙ НОМЕР
        f"Жми кнопку ниже после перевода!"
    )
    await callback.message.answer(text=success_text, reply_markup=pay_keyboard)
    await bot.send_message(chat_id=DRIVER_ID, text="✅ Клиент согласился на твои условия и сейчас переведет деньги!")

@dp.callback_query(F.data.startswith("paid_"))
async def payment_notif(callback: types.CallbackQuery):
    client_id = callback.from_user.id
    username = callback.from_user.username or "Без юзернейма"
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✅ Уведомление об оплате отправлено водителю. Водитель уже заводит мотор!")
    
    await bot.send_message(
        chat_id=DRIVER_ID, 
        text=f"💸 <b>ОПЛАТА ПОСТУПИЛА?</b>\nКлиент @{username} нажал кнопку 'Оплатил'. Проверь баланс!"
    )

# Обработка меню "Сжечь авто" и тд.
@dp.callback_query(F.data.startswith("crazy_"))
async def crazy_order(callback: types.CallbackQuery):
    service_data = callback.data.split("_")
    service_name = service_data[1]
    client_id = callback.from_user.id
    username = callback.from_user.username or "Без юзернейма"
    
    await callback.message.answer("Заказ сумасшедшей услуги отправлен водителю!")
    await bot.send_message(
        chat_id=DRIVER_ID,
        text=f"🔥 <b>ЗАКАЗ ИЗ ХАОС-МЕНЮ</b> 🔥\nУслуга: {service_name}\nКлиент: @{username}"
    )
    await callback.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
