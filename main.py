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

# --- МЕНЮ УСЛУГ ---
MENU = {
    "BASE": {
        "title": "🛌 БЫТОВОЙ СЮРРЕАЛИЗМ",
        "items": {
            "sleep": ("Сон на заднем", 150, "Я выключу музыку и буду шепотом объявлять ямы. Подушка включена."),
            "fairy": ("Сказка на ночь", 300, "Читаю состав освежителя воздуха томным голосом."),
            "unboxing": ("Распаковка покупок", 500, "Искренне восхищаюсь каждой сосиской из вашего пакета."),
            "grandma": ("Заботливая бабушка", 800, "Ворчу, что вы без шапки, и спрашиваю, когда вы найдете нормальную работу."),
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
            "interview": ("Интервью", 20000, "Всю дорогу спрашиваю о ваших планах на мировое господство."),
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

def get_payment_kb(item_name):
    kb = InlineKeyboardMarkup(row_width=1)
    # Передаем название услуги в callback для водителя
    kb.add(InlineKeyboardButton("✅ ОПЛАЧЕНО", callback_data=f"paid_{item_name[:15]}"))
    kb.add(InlineKeyboardButton("❌ ОТМЕНА", callback_data="main_menu"))
    return kb

def get_driver_decision_kb(user_id):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("✅ ПОДТВЕРДИТЬ (Деньги пришли)", callback_data=f"dr_ok_{user_id}"),
        InlineKeyboardButton("⚠️ ОПЛАТА НЕ ПОЛУЧЕНА", callback_data=f"dr_nopay_{user_id}"),
        InlineKeyboardButton("❌ ОТКЛОНИТЬ ЗАКАЗ", callback_data=f"dr_cancel_{user_id}")
    )
    return kb

# --- ОБРАБОТЧИКИ ---
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer("🚕 <b>Crazy Taxi Bot</b>\nГотовы к самому странному заказу в жизни?", reply_markup=get_main_kb())

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
    await callback.message.edit_text(text, reply_markup=get_payment_kb(item_data[0]))

@dp.callback_query_handler(lambda c: c.data == "custom_order")
async def custom_order(callback: types.CallbackQuery):
    await callback.message.edit_text("✍️ <b>Опишите ваше безумие и цену.</b>\nВодитель получит ваше сообщение напрямую.")

@dp.message_handler(lambda m: not m.text.startswith('/'))
async def handle_custom(message: types.Message):
    user = message.from_user
    await bot.send_message(
        DRIVER_ID,
        f"🧩 <b>ИНДИВИДУАЛЬНЫЙ ЗАКАЗ!</b>\nОт: {md.quote_html(user.full_name)} (@{user.username})\nТекст: <i>{md.quote_html(message.text)}</i>",
        reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("✅ ПРЕДЛОЖИТЬ ОПЛАТИТЬ", callback_data=f"ask_{user.id}"))
    )
    await message.answer("✅ <b>Ваша идея отправлена водителю!</b> Ждите ответа.")

@dp.callback_query_handler(lambda c: c.data.startswith("ask_"))
async def ask_pay(callback: types.CallbackQuery):
    user_id = callback.data.split("_")[1]
    await bot.send_message(user_id, f"🎯 <b>Водитель согласен!</b>\nПереводите сумму на <code>{REQUISITES}</code> и жмите кнопку.", reply_markup=get_payment_kb("Свой вариант"))
    await callback.answer("Запрос отправлен.")

# --- ЛОГИКА ДЛЯ ВОДИТЕЛЯ ---
@dp.callback_query_handler(lambda c: c.data.startswith("paid_"))
async def client_paid(callback: types.CallbackQuery):
    item_name = callback.data.split("_")[1]
    user = callback.from_user
    await callback.message.edit_text("⌛ <b>Уведомление отправлено.</b> Ожидайте подтверждения от водителя.")
    
    await bot.send_message(
        DRIVER_ID,
        f"💰 <b>КЛИЕНТ ЖМЕТ 'ОПЛАЧЕНО'!</b>\n👤 {md.quote_html(user.full_name)} (@{user.username})\n🛠 Услуга: {item_name}\n\n<b>Проверьте банк!</b>",
        reply_markup=get_driver_decision_kb(user.id)
    )

@dp.callback_query_handler(lambda c: c.data.startswith("dr_"))
async def driver_action(callback: types.CallbackQuery):
    _, action, user_id = callback.data.split("_")
    
    if action == "ok":
        await bot.send_message(user_id, "✅ <b>ОПЛАТА ПОДТВЕРЖДЕНА!</b> Водитель начинает выполнение. Приготовьтесь! 🚀")
        status = "🟢 ВЫ ПОДТВЕРДИЛИ ЗАКАЗ"
    elif action == "nopay":
        await bot.send_message(user_id, "⚠️ <b>ОШИБКА ОПЛАТЫ!</b> Водитель не видит денег на счету. Проверьте перевод или свяжитесь с водителем.")
        status = "🟡 ВЫ СООБЩИЛИ, ЧТО ОПЛАТЫ НЕТ"
    else:
        await bot.send_message(user_id, "❌ <b>ОТКАЗ.</b> Водитель отменил заказ. Если вы перевели деньги, они будут возвращены (свяжитесь с водителем).")
        status = "🔴 ВЫ ОТМЕНИЛИ ЗАКАЗ"
    
    await callback.message.edit_text(f"{callback.message.text}\n\n{status}")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
