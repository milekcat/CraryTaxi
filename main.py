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

# Инициализация бота
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# Временные БД в памяти
accepted_users = set()
active_orders = {}

# --- БАЗА CRAZY-УСЛУГ ---
CRAZY_SERVICES = {
    "sleep": {"name": "🛌 Сон под шепот ям", "price": 150, "desc": "Аккуратная езда, расслабляющая музыка, водитель молчит как рыба."},
    "tale": {"name": "📖 Сказка на ночь", "price": 300, "desc": "Водитель расскажет захватывающую, возможно выдуманную, историю из жизни таксиста."},
    "granny": {"name": "👵 Бабушка-ворчунья", "price": 800, "desc": "Всю дорогу буду бубнить, как ты плохо одет, почему без шапки и что 'в наше время было лучше'."},
    "spy": {"name": "🕵️‍♂️ Шпионская слежка", "price": 2000, "desc": "Едем за 'той машиной'. Водитель надевает черные очки, говорит по рации и нагнетает паранойю."},
    "karaoke": {"name": "🎤 Караоке-баттл", "price": 5000, "desc": "Поем во весь голос хиты 90-х. Светомузыка в салоне, водитель подпевает и жутко фальшивит."},
    "dance": {"name": "🕺 Танцы на светофоре", "price": 15000, "desc": "Красный свет? Я выхожу из машины и танцую безумный танец перед всеми участниками движения!"},
    "kidnap": {"name": "🎭 Дружеское похищение", "price": 30000, "desc": "Тебя 'жестко' пакуют в авто (по сценарию) и везут пить чай с баранками на природу."},
    "tarzan": {"name": "🦍 Тарзан-шоу", "price": 50000, "desc": "Перформанс с раздеванием, криками и биением себя в грудь. Максимальный кринж гарантирован!"},
    "burn": {"name": "🔥 Сжечь машину", "price": 1000000, "desc": "Приезжаем на пустырь, ты даешь лям, я даю канистру с бензином. Гори оно всё огнем."}
}

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
    [InlineKeyboardButton(text="✅ ПОДПИСАТЬ КОНТРАКТ", callback_data="accept_tos")],
    [InlineKeyboardButton(text="❌ Я боюсь, пойду пешком", callback_data="decline_tos")]
])

# ==========================================
# 🛑 СТАРТ И ОТКАЗ ОТ ОТВЕТСТВЕННОСТИ (НОВЫЙ ЛОР)
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
    accepted_users.add(callback.from_user.id)
    await callback.message.edit_text("🔥 <b>ДОБРО ПОЖАЛОВАТЬ В CRAZY TAXI!</b> 🔥\nКонтракт подписан кровью (шутка, цифровой подписью).")
    await callback.message.answer("Выбирай действие в меню ниже 👇", reply_markup=main_kb)

@dp.callback_query(F.data == "decline_tos")
async def tos_declined(callback: types.CallbackQuery):
    await callback.message.edit_text("🚶‍♂️ Очень жаль! Законы улиц суровы, но безопасны. Удачной пешей прогулки!")

async def check_tos(message: types.Message) -> bool:
    if message.from_user.id not in accepted_users:
        await message.answer("Сначала нужно принять правила! Нажми /start")
        return False
    return True

# ==========================================
# ⚖️ ЮРИДИЧЕСКИЙ РАЗДЕЛ И АДВОКАТ (НОВЫЙ ЛОР)
# ==========================================
@dp.message(F.text == "⚖️ Вызвать адвоката / Правила")
async def lawyer_menu(message: types.Message):
    if not await check_tos(message): return
    
    lawyer_text = (
        "⚖️ <b>НАШ НЕПОБЕДИМЫЙ АДВОКАТ</b> ⚖️\n\n"
        "Думаешь, что-то вышло из-под контроля? Хочешь пожаловаться?\n\n"
        "<b>Ознакомься с прецедентами:</b>\n"
        "• Наш юрист доказал в суде, что красный свет светофора — это 'субъективное восприятие цвета'.\n"
        "• Любой твой испуганный крик в салоне по договору классифицируется как 'активное участие в интерактиве'.\n"
        "• Читать права здесь будет только он, и то на латыни.\n\n"
        "<i>Все еще хочешь с ним связаться? Жми кнопку, если не боишься встречного иска за отрыв от важных дел!</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚨 СВЯЗАТЬСЯ С АДВОКАТОМ 🚨", callback_data="call_lawyer")]
    ])
    await message.answer(lawyer_text, reply_markup=kb)

@dp.callback_query(F.data == "call_lawyer")
async def alert_lawyer(callback: types.CallbackQuery):
    await callback.answer("🚨 Адвокат уже выехал... шучу, он занят подачей иска на твою скуку. Договаривайся с водителем!", show_alert=True)
    await bot.send_message(chat_id=DRIVER_ID, text=f"⚖️ Клиент @{callback.from_user.username} пытается вызвать адвоката! Скажи ему, что наш юрист сегодня берет отгул.")

# ==========================================
# 📜 РАСШИРЕННОЕ ХАОС-МЕНЮ (ПОЛНЫЙ ЦИКЛ ПРОДАЖ)
# ==========================================
@dp.message(F.text == "📜 CRAZY ХАОС-МЕНЮ")
async def show_crazy_menu(message: types.Message):
    if not await check_tos(message): return
    
    buttons = []
    for key, data in CRAZY_SERVICES.items():
        buttons.append([InlineKeyboardButton(text=f"{data['name']} - {data['price']}₽", callback_data=f"csel_{key}")])
        
    ikb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("🔥 <b>CRAZY DRIVER'S CHAOS MENU</b> 🔥\n\n<i>Выбирай свое приключение на сегодня:</i>", reply_markup=ikb)

@dp.callback_query(F.data.startswith("csel_"))
async def process_crazy_selection(callback: types.CallbackQuery):
    service_key = callback.data.split("_")[1]
    service = CRAZY_SERVICES[service_key]
    client_id = callback.from_user.id
    
    active_orders[client_id] = {"type": "crazy", "service_key": service_key}
    
    text = (
        f"🎪 <b>ВЫБРАНА УСЛУГА:</b> {service['name']}\n\n"
        f"📝 <b>Описание:</b> {service['desc']}\n\n"
        f"💰 <b>Стоимость:</b> {service['price']}₽\n\n"
        f"💳 <b>Реквизиты для оплаты:</b>\n"
        f"Яндекс Банк: <code>+79012723729</code> (Андрей Игоревич)\n\n"
        f"⚠️ <i>Услуга будет активирована только после перевода.</i>"
    )
    
    pay_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Я ОПЛАТИЛ УСЛУГУ", callback_data="cpay_done")],
        [InlineKeyboardButton(text="❌ Передумал", callback_data="cpay_cancel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=pay_kb)

@dp.callback_query(F.data == "cpay_cancel")
async def cancel_crazy_payment(callback: types.CallbackQuery):
    client_id = callback.from_user.id
    if client_id in active_orders: del active_orders[client_id]
    await callback.message.edit_text("❌ Заказ отменен. Наш адвокат одобряет твое благоразумие!")

@dp.callback_query(F.data == "cpay_done")
async def crazy_payment_done(callback: types.CallbackQuery):
    client_id = callback.from_user.id
    username = callback.from_user.username or "Без юзернейма"
    order = active_orders.get(client_id)
    
    if not order or order.get("type") != "crazy":
        await callback.answer("Заказ не найден. Начни заново.", show_alert=True)
        return

    service_key = order["service_key"]
    service = CRAZY_SERVICES[service_key]
    
    await callback.message.edit_text("⏳ <b>Уведомление отправлено водителю.</b>\nОжидаем подтверждения поступления средств и старта шоу...")
    
    driver_text = (
        f"🚨 <b>НОВЫЙ ЗАКАЗ ИЗ ХАОС-МЕНЮ (ОПЛАЧЕН?)</b> 🚨\n\n"
        f"👤 Клиент: @{username}\n"
        f"🎪 Услуга: <b>{service['name']}</b>\n"
        f"💰 Ожидаемая сумма: <b>{service['price']}₽</b>\n\n"
        f"<i>Клиент нажал кнопку «Оплатил». Проверь Яндекс Банк:</i>"
    )
    
    driver_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Деньги пришли, ВЫПОЛНЯЮ!", callback_data=f"cdrv_ok_{client_id}")],
        [InlineKeyboardButton(text="❌ Оплата НЕ получена", callback_data=f"cdrv_nopay_{client_id}")],
        [InlineKeyboardButton(text="↩️ Отказаться и ВЕРНУТЬ деньги", callback_data=f"cdrv_refund_{client_id}")]
    ])
    
    await bot.send_message(chat_id=DRIVER_ID, text=driver_text, reply_markup=driver_kb)

# --- ПУЛЬТ ВОДИТЕЛЯ (CRAZY-МЕНЮ) ---
@dp.callback_query(F.data.startswith("cdrv_ok_"))
async def cdrv_ok(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    order = active_orders.get(client_id)
    service_name = CRAZY_SERVICES[order["service_key"]]["name"] if order else "Услуга"
    
    await callback.message.edit_text(f"✅ Ты подтвердил оплату и взял в работу: {service_name}")
    try:
        await bot.send_message(chat_id=client_id, text=f"🎉 <b>ОПЛАТА ПОЛУЧЕНА!</b>\n\nВодитель подтвердил перевод. Услуга <b>«{service_name}»</b> активирована. Приготовься к шоу!")
    except: pass

@dp.callback_query(F.data.startswith("cdrv_nopay_"))
async def cdrv_nopay(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    await callback.message.edit_text("❌ Ты отметил, что оплата не поступила.")
    try:
        await bot.send_message(chat_id=client_id, text="🛑 <b>ВНИМАНИЕ!</b>\nВодитель сообщает, что оплата <b>не поступила</b> на счет Яндекс Банка. Проверь статус перевода или свяжись с водителем.")
    except: pass

@dp.callback_query(F.data.startswith("cdrv_refund_"))
async def cdrv_refund(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    await callback.message.edit_text("↩️ Ты отказался от выполнения. Не забудь перевести деньги обратно клиенту!")
    try:
        await bot.send_message(chat_id=client_id, text="⚠️ <b>ВОЗВРАТ СРЕДСТВ</b>\n\nВодитель в данный момент не может выполнить эту услугу. Заказ отменен. \nЕсли вы уже перевели деньги, <b>водитель оформит возврат по вашим реквизитам.</b>")
    except: pass

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
# 🚕 ОБЫЧНОЕ ТАКСИ (С ТОРГОМ)
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
        "type": "taxi",
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
        f"Яндекс Банк: <code>+79012723729</code> (Андрей Игоревич)\n\n"
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
    await callback.message.answer("Вы отказались. Наш адвокат закрывает дело.")
    await bot.send_message(chat_id=DRIVER_ID, text=f"❌ Клиент отказался от твоих условий.")

@dp.callback_query(F.data.startswith("client_accept_"))
async def client_accepts_offer(callback: types.CallbackQuery):
    client_id = int(callback.data.split("_")[2])
    await callback.message.edit_reply_markup(reply_markup=None)
    
    pay_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Оплатил, поехали!", callback_data=f"paid_{client_id}")]
    ])
    
    await callback.message.answer(
        text=f"🚕 <b>ДОГОВОРИЛИСЬ!</b>\n\n💳 <b>Реквизиты:</b>\nЯндекс Банк: <code>+79012723729</code> (Андрей Игоревич)\n\nЖми кнопку после перевода!", 
        reply_markup=pay_keyboard
    )
    await bot.send_message(chat_id=DRIVER_ID, text="✅ Клиент согласился на твои условия и переводит деньги!")

@dp.callback_query(F.data.startswith("paid_"))
async def payment_notif(callback: types.CallbackQuery):
    username = callback.from_user.username or "Без юзернейма"
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✅ Уведомление об оплате отправлено! Водитель заводит мотор 💨")
    await bot.send_message(chat_id=DRIVER_ID, text=f"💸 <b>ОПЛАТА ПОСТУПИЛА?</b>\nКлиент @{username} нажал 'Оплатил'. Проверь баланс Яндекс Банка!")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
