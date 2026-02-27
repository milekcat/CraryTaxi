import asyncio
import logging
import os
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
DRIVER_ID = os.getenv("DRIVER_ID")

if not API_TOKEN or not DRIVER_ID:
    logging.error("ВНИМАНИЕ: API_TOKEN или DRIVER_ID не найдены!")

DRIVER_ID = int(DRIVER_ID)

# Инициализация бота для новых версий aiogram (3.7.0+)
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# Временные БД в памяти
accepted_users = set() # Те, кто принял условия
active_orders = {}

# --- СОСТОЯНИЯ FSM ---
class OrderRide(StatesGroup):
    waiting_for_from = State()
    waiting_for_to = State()
    waiting_for_price = State()

class DriverOffer(StatesGroup):
    waiting_for_offer = State()

class CustomIdea(StatesGroup):
    waiting_for_idea = State()

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
    [InlineKeyboardButton(text="✅ Я ПРИНИМАЮ ВСЕ РИСКИ", callback_data="accept_tos")],
    [InlineKeyboardButton(text="❌ Я боюсь, пойду пешком", callback_data="decline_tos")]
])

# ==========================================
# 🛑 СТАРТ И ОТКАЗ ОТ ОТВЕТСТВЕННОСТИ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    disclaimer_text = (
        "⚠️ <b>ОТКАЗ ОТ ОТВЕТСТВЕННОСТИ</b> ⚠️\n\n"
        "ВНИМАНИЕ! Вы пытаетесь воспользоваться услугами <b>Crazy Taxi</b>.\n"
        "Данный автомобиль является зоной действия <b>Арт-перформанса</b>.\n\n"
        "<b>Нажимая «Принять», вы соглашаетесь с тем, что:</b>\n"
        "1. Водитель может оказаться безумцем в гавайской рубашке.\n"
        "2. Ваша поездка может превратиться в шоу, концерт или психологический триллер.\n"
        "3. Вы добровольно отказываетесь от претензий на моральный ущерб, если водитель начнет петь колыбельные или танцевать на светофоре.\n"
        "4. Законы логики внутри салона могут не работать.\n\n"
        "<i>Готов шагнуть в хаос?</i>"
    )
    await message.answer(disclaimer_text, reply_markup=tos_kb)

@dp.callback_query(F.data == "accept_tos")
async def tos_accepted(callback: types.CallbackQuery):
    accepted_users.add(callback.from_user.id)
    await callback.message.edit_text("🔥 <b>ДОБРО ПОЖАЛОВАТЬ В CRAZY TAXI!</b> 🔥\nВы официально стали участником перформанса.")
    await callback.message.answer("Выбирай действие в меню ниже 👇", reply_markup=main_kb)

@dp.callback_query(F.data == "decline_tos")
async def tos_declined(callback: types.CallbackQuery):
    await callback.message.edit_text("🚶‍♂️ Очень жаль! Но безопасность превыше всего. Удачной пешей прогулки!")

# Проверка, принял ли пользователь правила
async def check_tos(message: types.Message) -> bool:
    if message.from_user.id not in accepted_users:
        await message.answer("Сначала нужно принять правила! Нажми /start")
        return False
    return True

# ==========================================
# ⚖️ ЮРИДИЧЕСКИЙ РАЗДЕЛ И АДВОКАТ
# ==========================================
@dp.message(F.text == "⚖️ Вызвать адвоката / Правила")
async def lawyer_menu(message: types.Message):
    if not await check_tos(message): return
    
    lawyer_text = (
        "⚖️ <b>ЮРИДИЧЕСКИЙ ХАЙП И ЗАЩИТА</b> ⚖️\n\n"
        "Спокойно! Если перформанс зашел слишком далеко, у нас есть связи.\n\n"
        "<b>Правила салона:</b>\n"
        "• Клиент всегда прав, пока водитель не решит иначе.\n"
        "• Чаевые снижают градус безумия на 15%.\n"
        "• Попытка покинуть движущееся авто расценивается как слабость.\n\n"
        "<i>Нужен адвокат, чтобы вытащить тебя из багажника? Жми кнопку!</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚨 СВЯЗАТЬСЯ С АДВОКАТОМ 🚨", callback_data="call_lawyer")]
    ])
    await message.answer(lawyer_text, reply_markup=kb)

@dp.callback_query(F.data == "call_lawyer")
async def alert_lawyer(callback: types.CallbackQuery):
    await callback.answer("🚨 Адвокат уже выехал... шучу, он в отпуске. Договаривайся с водителем!", show_alert=True)
    await bot.send_message(chat_id=DRIVER_ID, text=f"⚖️ Клиент @{callback.from_user.username} пытается вызвать адвоката! Кажется, ты переборщил.")

# ==========================================
# 📜 РАСШИРЕННОЕ ХАОС-МЕНЮ
# ==========================================
@dp.message(F.text == "📜 CRAZY ХАОС-МЕНЮ")
async def crazy_menu(message: types.Message):
    if not await check_tos(message): return
    
    text = (
        "🔥 <b>CRAZY DRIVER'S CHAOS MENU</b> 🔥\n"
        "<i>Выбирай свое приключение на сегодня:</i>\n\n"
        "🛌 <b>Сон под шепот ям (150₽)</b> - Аккуратная езда, расслабляющая музыка, водитель молчит.\n"
        "📖 <b>Сказка на ночь (300₽)</b> - Водитель расскажет захватывающую историю из жизни таксиста.\n"
        "👵 <b>Бабушка-ворчунья (800₽)</b> - Всю дорогу буду бубнить, как ты плохо одет и что 'в наше время было лучше'.\n"
        "🕺 <b>Танцы на светофоре (15 000₽)</b> - Красный свет? Я выхожу из машины и танцую макарену!\n"
        "🦍 <b>Тарзан-шоу (50 000₽)</b> - Перформанс с раздеванием, криками и биением себя в грудь.\n"
        "🔥 <b>Сжечь машину (1 000 000₽)</b> - Приезжаем на пустырь, ты даешь лям, я даю канистру с бензином. Конец.\n"
    )
    
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛌 Сон (150₽)", callback_data="crazy_sleep"), InlineKeyboardButton(text="📖 Сказка (300₽)", callback_data="crazy_tale")],
        [InlineKeyboardButton(text="👵 Бабушка (800₽)", callback_data="crazy_granny"), InlineKeyboardButton(text="🕺 Танцы (15к₽)", callback_data="crazy_dance")],
        [InlineKeyboardButton(text="🦍 Тарзан (50к₽)", callback_data="crazy_tarzan"), InlineKeyboardButton(text="🔥 Сжечь авто (1млн₽)", callback_data="crazy_burn")]
    ])
    await message.answer(text, reply_markup=ikb)

@dp.callback_query(F.data.startswith("crazy_"))
async def process_crazy_order(callback: types.CallbackQuery):
    service = callback.data.split("_")[1]
    client_id = callback.from_user.id
    username = callback.from_user.username or "Без юзернейма"
    
    services_dict = {
        "sleep": "Сон под шепот ям", "tale": "Сказка на ночь", "granny": "Бабушка-ворчунья",
        "dance": "Танцы на светофоре", "tarzan": "Тарзан-шоу", "burn": "Сжечь машину"
    }
    
    service_name = services_dict.get(service, "Неизвестная дичь")
    
    await callback.message.answer(f"✅ Заказ на <b>«{service_name}»</b> улетел водителю! Готовься.")
    await bot.send_message(
        chat_id=DRIVER_ID,
        text=f"🎭 <b>ВНИМАНИЕ! ЗАКАЗ ИЗ ХАОС-МЕНЮ!</b> 🎭\n\n👤 Клиент: @{username}\n🎪 Выбрал: <b>{service_name}</b>\n\nСвяжись с ним для уточнения деталей!"
    )
    await callback.answer()

# ==========================================
# 💡 СВОЙ ВАРИАНТ (ИНДИВИДУАЛЬНЫЙ ЗАКАЗ)
# ==========================================
@dp.message(F.text == "💡 Свой вариант (Предложить идею)")
async def custom_idea_start(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    await message.answer("У тебя есть безумная идея для поездки? Опиши её здесь, а водитель назовет свою цену!", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(CustomIdea.waiting_for_idea)

@dp.message(CustomIdea.waiting_for_idea)
async def process_custom_idea(message: types.Message, state: FSMContext):
    idea = message.text
    client_id = message.from_user.id
    username = message.from_user.username or "Без юзернейма"
    
    await message.answer("🧠 Идея отправлена! Ждем, во сколько водитель оценит этот хаос...", reply_markup=main_kb)
    await state.clear()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Назначить цену", callback_data=f"priceidea_{client_id}")]
    ])
    await bot.send_message(chat_id=DRIVER_ID, text=f"💡 <b>НОВАЯ ИДЕЯ ОТ КЛИЕНТА</b> 💡\n\n👤 @{username}\n📝 Суть: {idea}", reply_markup=kb)

# ==========================================
# 🚕 ОБЫЧНОЕ ТАКСИ (С ТОРГОМ) - ЛОГИКА СОХРАНЕНА
# ==========================================
@dp.message(F.text == "🚕 Заказать такси (Торг)")
async def start_ride_order(message: types.Message, state: FSMContext):
    if not await check_tos(message): return
    await message.answer("📍 <b>Откуда тебя забрать?</b> Напиши адрес:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(OrderRide.waiting_for_from)

@dp.message(OrderRide.waiting_for_from)
async def process_from_address(message: types.Message, state: FSMContext):
    await state.update_data(from_address=message.text)
    await message.answer("🏁 <b>Куда мчим?</b> Напиши адрес:")
    await state.set_state(OrderRide.waiting_for_to)

@dp.message(OrderRide.waiting_for_to)
async def process_to_address(message: types.Message, state: FSMContext):
    await state.update_data(to_address=message.text)
    await message.answer("💰 <b>Сколько готов заплатить?</b> (Сумма в рублях):")
    await state.set_state(OrderRide.waiting_for_price)

@dp.message(OrderRide.waiting_for_price)
async def process_price(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    client_id = message.from_user.id
    
    active_orders[client_id] = {
        "from": user_data['from_address'],
        "to": user_data['to_address'],
        "price": message.text,
        "username": message.from_user.username or "Без юзернейма",
        "offer": ""
    }

    await message.answer("⏳ <b>Заказ отправлен!</b> Ждем ответа водителя...", reply_markup=main_kb)
    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{client_id}")],
        [InlineKeyboardButton(text="✍️ Предложить цену", callback_data=f"counter_{client_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{client_id}")]
    ])
    
    driver_text = (
        f"🚕 <b>НОВЫЙ ЗАКАЗ</b> 🚕\n\n"
        f"👤 Клиент: @{active_orders[client_id]['username']}\n"
        f"📍 Откуда: {active_orders[client_id]['from']}\n"
        f"🏁 Куда: {active_orders[client_id]['to']}\n"
        f"💰 Цена клиента: <b>{active_orders[client_id]['price']}₽</b>"
    )
    await bot.send_message(chat_id=DRIVER_ID, text=driver_text, reply_markup=keyboard)

# --- РЕАКЦИИ ВОДИТЕЛЯ И ОПЛАТА ---
@dp.callback_query(F.data.startswith("reject_"))
async def driver_rejects(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[1])
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Отклонено")
    try: await bot.send_message(chat_id=client_id, text="😔 Водитель не может принять заказ. Попробуй позже!")
    except: pass

@dp.callback_query(F.data.startswith("accept_"))
async def driver_accepts(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[1])
    await callback.message.edit_reply_markup(reply_markup=None)
    
    order = active_orders.get(client_id, {})
    pay_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Оплатил, поехали!", callback_data=f"paid_{client_id}")]
    ])
    
    success_text = (
        f"🚕 <b>ВОДИТЕЛЬ ПРИНЯЛ ЗАКАЗ!</b>\n\n"
        f"💰 К оплате: <b>{order.get('price', '?')}</b>\n\n"
        f"💳 <b>Реквизиты для перевода:</b>\n"
        f"Яндекс Банк: <code> +79012723729</code> (Андрей Игоревич)\n\n"
        f"Жми кнопку ниже, как переведешь!"
    )
    try: await bot.send_message(chat_id=client_id, text=success_text, reply_markup=pay_keyboard)
    except: pass

@dp.callback_query(F.data.startswith("counter_") | F.data.startswith("priceidea_"))
async def driver_counteroffer(callback: types.CallbackQuery, state: FSMContext):
    client_id = int(callback.data.split("_")[1])
    await state.update_data(target_client_id=client_id)
    await callback.message.answer("Напиши свою цену и условия для клиента:")
    await state.set_state(DriverOffer.waiting_for_offer)
    await callback.answer()

@dp.message(DriverOffer.waiting_for_offer)
async def send_offer_to_client(message: types.Message, state: FSMContext):
    data = await state.get_data()
    client_id = data.get('target_client_id')
    driver_offer = message.text
    
    if client_id in active_orders: active_orders[client_id]['offer'] = driver_offer
    
    client_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Согласен", callback_data=f"client_accept_{client_id}")],
        [InlineKeyboardButton(text="❌ Отказаться", callback_data=f"client_reject_{client_id}")]
    ])
    
    try:
        await bot.send_message(chat_id=client_id, text=f"⚡️ <b>Встречные условия от водителя:</b>\n\n{driver_offer}\n\nСогласен?", reply_markup=client_keyboard)
        await message.answer("✅ Отправлено клиенту!")
    except:
        await message.answer("❌ Ошибка отправки.")
    await state.clear()

@dp.callback_query(F.data.startswith("client_reject_"))
async def client_rejects(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Вы отказались. Будем ждать снова!")
    await bot.send_message(chat_id=DRIVER_ID, text=f"❌ Клиент отказался от твоих условий.")

@dp.callback_query(F.data.startswith("client_accept_"))
async def client_accepts_offer(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    await callback.message.edit_reply_markup(reply_markup=None)
    
    pay_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Оплатил, поехали!", callback_data=f"paid_{client_id}")]
    ])
    
    await callback.message.answer(
        text=f"🚕 <b>ДОГОВОРИЛИСЬ!</b>\n\n💳 <b>Реквизиты:</b>\nСбер/Тинькофф: <code>+79990000000</code> (Ярослав)\n\nЖми кнопку после перевода!", 
        reply_markup=pay_keyboard
    )
    await bot.send_message(chat_id=DRIVER_ID, text="✅ Клиент согласился на твои условия и переводит деньги!")

@dp.callback_query(F.data.startswith("paid_"))
async def payment_notif(callback: types.CallbackQuery):
    username = callback.from_user.username or "Без юзернейма"
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✅ Уведомление об оплате отправлено! Водитель заводит мотор 💨")
    await bot.send_message(chat_id=DRIVER_ID, text=f"💸 <b>ОПЛАТА ПОСТУПИЛА?</b>\nКлиент @{username} нажал 'Оплатил'. Проверь баланс!")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
