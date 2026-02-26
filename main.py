import os
import logging
from aiogram import Bot, Dispatcher, types, executor
from aiogram.utils import markdown as md
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- КОНФИГУРАЦИЯ ---
API_TOKEN = os.getenv('API_TOKEN')
DRIVER_ID = os.getenv('DRIVER_ID')
REQUISITES = "+79012723729 Яндекс Банк"
LAWYER_URL = "https://t.me/Ai_advokatrobot"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# Словарь для хранения временных данных (кто запрашивает цену)
pending_custom_orders = {}

# --- МЕНЮ УСЛУГ ---
MENU = {
    "BASE": {
        "title": "🛌 БЫТОВОЙ СЮРРЕАЛИЗМ",
        "items": {
            "sleep": ("Сон на заднем", 150, "Я выключу музыку и буду шепотом объявлять ямы. Подушка включена."),
            "fairy": ("Сказка на ночь", 300, "Читаю состав освежителя воздуха томным голосом."),
            "unboxing": ("Распаковка покупок", 500, "Искренне восхищаюсь каждой сосиской из вашего пакета."),
            "grandma": ("Заботливая бабушка", 800, "Ворчу, что вы без шапки, и спрашиваю про работу."),
        }
    },
    "CRAZY": {
        "title": "🔞 ДРАЙВЕР-ХАРДКОР",
        "items": {
            "naked": ("Голый водитель", 15000, "Еду абсолютно без одежды. Окна затонированы."),
            "dance": ("Танцы на светофоре", 15000, "На красном выхожу и танцую перед капотом."),
            "tarzan": ("Водитель-Тарзан", 50000, "Голый, бью себя в грудь и кричу на прохожих."),
        }
    },
    "VIP": {
        "title": "💎 VIP УСЛУГИ",
        "items": {
            "escort": ("Кортеж из 1 авто", 25000, "Еду строго посередине двух полос с аварийкой."),
            "carpet": ("Красная дорожка", 15000, "Выстилаю перед дверью скатерти. Выход под фанфары."),
            "interview": ("Интервью", 20000, "Спрашиваю о ваших планах на мировое господство."),
        }
    },
    "FINAL": {
        "title": "🔥 ТОТАЛЬНОЕ БЕЗУМИЕ",
        "items": {
            "burn": ("СЖЕЧЬ МАШИНУ", 1000000, "Обливаем бензином и уходим, не оборачиваясь на взрыв."),
            "ditch": ("Съехать в кювет", 150000, "Эффектно съезжаем в мягкий кювет для ваших сторис."),
        }
    }
}

# --- КЛАВИАТУРЫ ---
def get_main_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    for cat_id, cat_data in MENU.items():
        kb.add(InlineKeyboardButton(cat_data["title"], callback_data=f"cat_{cat_id}"))
    kb.add(InlineKeyboardButton("🌟 СВОЙ ВАРИАНТ", callback_data="custom_order"))
    return kb

def get_category_kb(cat_id):
    kb = InlineKeyboardMarkup(row_width=1)
    for item_id, data in MENU[cat_id]["items"].items():
        kb.add(InlineKeyboardButton(f"{data[0]} — {data[1]}₽", callback_data=f"info_{item_id}"))
    kb.add(InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu"))
    return kb

def get_payment_kb(item_name, price):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("✅ ОПЛАЧЕНО", callback_data=f"paid_{item_name[:15]}_{price}"))
    kb.add(InlineKeyboardButton("❌ ОТМЕНА", callback_data="main_menu"))
    return kb

def get_driver_decision_kb(user_id):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("✅ ПОДТВЕРДИТЬ", callback_data=f"dr_ok_{user_id}"),
        InlineKeyboardButton("⚠️ ОПЛАТА НЕ ПОЛУЧЕНА", callback_data=f"dr_nopay_{user_id}"),
        InlineKeyboardButton("❌ ОТКЛОНИТЬ ЗАКАЗ", callback_data=f"dr_cancel_{user_id}")
    )
    return kb

# --- ОБРАБОТЧИКИ ---
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer("🚕 <b>Crazy Taxi Bot</b>\nЗакажите шоу, которое невозможно забыть!", reply_markup=get_main_kb())

@dp.callback_query_handler(lambda c: c.data == "main_menu")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text("🔥 <b>ВЫБИРАЙТЕ КАТЕГОРИЮ:</b>", reply_markup=get_main_kb())

@dp.callback_query_handler(lambda c: c.data.startswith("cat_"))
async def show_category(callback: types.CallbackQuery):
    cat_id = callback.data.split("_")[1]
    await callback.message.edit_text(f"🚀 <b>{MENU[cat_id]['title']}:</b>", reply_markup=get_category_kb(cat_id))

@dp.callback_query_handler(lambda c: c.data.startswith("info_"))
async def show_info(callback: types.CallbackQuery):
    item_id = callback.data.split("_")[1]
    item_data = next((cat["items"][item_id] for cat in MENU.values() if item_id in cat["items"]), None)
    
    text = (
        f"🛠 <b>УСЛУГА:</b> {item_data[0]}\n"
        f"📝 <b>ОПИСАНИЕ:</b> {item_data[2]}\n\n"
        f"💰 <b>ЦЕНА:</b> {item_data[1]}₽\n\n"
        f"📌 <b>РЕКВИЗИТЫ:</b> <code>{REQUISITES}</code>\n"
        f"<i>Оплатите и нажмите кнопку ниже.</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_payment_kb(item_data[0], item_data[1]))

@dp.callback_query_handler(lambda c: c.data == "custom_order")
async def custom_order(callback: types.CallbackQuery):
    await callback.message.edit_text("✍️ <b>Опишите ваше пожелание.</b>\nВодитель рассмотрит его и назначит цену.")

# --- ЛОГИКА ИНДИВИДУАЛЬНОГО ЗАКАЗА ---
@dp.message_handler(lambda m: not m.text.startswith('/'))
async def handle_messages(message: types.Message):
    user_id = str(message.from_user.id)
    driver_id_str = str(DRIVER_ID)

    # Если пишет водитель (назначает цену)
    if user_id == driver_id_str:
        if pending_custom_orders:
            # Берем последнего клиента, которому нужно назначить цену
            target_user_id = list(pending_custom_orders.keys())[-1]
            custom_description = pending_custom_orders.pop(target_user_id)
            
            price = message.text.strip()
            
            await bot.send_message(
                target_user_id,
                f"🎯 <b>Водитель оценил ваш заказ!</b>\n\n"
                f"🛠 Услуга: <i>{custom_description}</i>\n"
                f"💰 Цена: <b>{price}</b>\n\n"
                f"Реквизиты для оплаты: <code>{REQUISITES}</code>",
                reply_markup=get_payment_kb("Свой вариант", price)
            )
            await message.answer(f"✅ Цена {price} отправлена клиенту.")
        else:
            await message.answer("Пока нет активных запросов на индивидуальную услугу.")
    
    # Если пишет клиент (предлагает услугу)
    else:
        pending_custom_orders[user_id] = message.text
        await bot.send_message(
            DRIVER_ID,
            f"🧩 <b>ИНДИВИДУАЛЬНЫЙ ЗАКАЗ!</b>\n"
            f"От: {md.quote_html(message.from_user.full_name)} (@{message.from_user.username})\n"
            f"Текст: <i>{md.quote_html(message.text)}</i>\n\n"
            f"<b>ПРОСТО НАПИШИТЕ ЦЕНУ (числом) в ответ на это сообщение:</b>"
        )
        await message.answer("✅ <b>Ваша идея отправлена водителю!</b> Он скоро назначит цену.")

# --- ЛОГИКА ОПЛАТЫ И РЕШЕНИЯ ---
@dp.callback_query_handler(lambda c: c.data.startswith("paid_"))
async def client_paid(callback: types.CallbackQuery):
    data = callback.data.split("_")
    item_name = data[1]
    price = data[2]
    user = callback.from_user
    
    await callback.message.edit_text("⌛ <b>Запрос отправлен.</b> Ожидайте подтверждения.")
    
    await bot.send_message(
        DRIVER_ID,
        f"💰 <b>КЛИЕНТ ОПЛАТИЛ {price}₽!</b>\n👤 {md.quote_html(user.full_name)}\n🛠 Услуга: {item_name}\n\n<b>Проверьте банк!</b>",
        reply_markup=get_driver_decision_kb(user.id)
    )

@dp.callback_query_handler(lambda c: c.data.startswith("dr_"))
async def driver_action(callback: types.CallbackQuery):
    _, action, user_id = callback.data.split("_")
    
    if action == "ok":
        await bot.send_message(user_id, "✅ <b>ОПЛАТА ПОДТВЕРЖДЕНА!</b> Начинаем шоу! 🚀")
        status = "🟢 ВЫ ПОДТВЕРДИЛИ"
    elif action == "nopay":
        await bot.send_message(user_id, "⚠️ <b>ОПЛАТА НЕ ПОЛУЧЕНА!</b> Водитель не видит денег. Проверьте перевод.")
        status = "🟡 ВЫ ОТВЕТИЛИ, ЧТО ДЕНЕГ НЕТ"
    else:
        await bot.send_message(user_id, "❌ <b>ОТКЛОНЕНО.</b> Водитель отменил заказ.")
        status = "🔴 ВЫ ОТМЕНИЛИ ЗАКАЗ"
    
    await callback.message.edit_text(f"{callback.message.text}\n\n{status}")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
    
