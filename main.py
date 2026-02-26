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

# --- ПОЛНОЕ МЕНЮ С ОПИСАНИЯМИ ---
MENU = {
    "BASE": {
        "title": "🛌 БЫТОВОЙ СЮРРЕАЛИЗМ",
        "items": {
            "sleep": ("Сон на заднем", 150, "Я выключу музыку, прикрою шторки и буду шепотом объявлять ямы. Подушка из моей куртки включена."),
            "fairy": ("Сказка на ночь", 300, "Читаю томным голосом инструкцию к освежителю воздуха или состав освежителя 'Морской бриз'."),
            "unboxing": ("Распаковка покупок", 500, "Вы достаете продукты из пакета, а я искренне восхищаюсь каждой сосиской и пачкой пельменей."),
            "grandma": ("Заботливая бабушка", 800, "Всю дорогу ворчу, что вы без шапки, предлагаю поесть и спрашиваю, когда вы уже найдете нормальную работу."),
        }
    },
    "CRAZY": {
        "title": "🔞 ДРАЙВЕР-ХАРДКОР",
        "items": {
            "naked": ("Голый водитель", 15000, "Еду абсолютно без одежды. Полная свобода и единение с машиной. Окна затонированы."),
            "dance": ("Танцы на светофоре", 15000, "На каждом красном выхожу из машины и танцую тектоник или лезгинку прямо перед капотом."),
            "tarzan": ("Водитель-Тарзан", 50000, "Еду голым, периодически бью себя в грудь и издаю победный крик в окно на прохожих."),
        }
    },
    "VIP": {
        "title": "💎 VIP УСЛУГИ",
        "items": {
            "escort": ("Кортеж из 1 авто", 25000, "Еду строго посередине двух полос с аварийкой, создавая иллюзию очень важного кортежа."),
            "carpet": ("Красная дорожка", 15000, "По приезду выстилаю перед вашей дверью скатерти из Ашана. Выход под фанфары из колонки."),
            "interview": ("Интервью", 20000, "Всю дорогу держу перед вами импровизированный микрофон и спрашиваю о планах на мировое господство."),
        }
    },
    "FINAL": {
        "title": "🔥 ТОТАЛЬНОЕ БЕЗУМИЕ",
        "items": {
            "burn": ("СЖЕЧЬ МАШИНУ", 1000000, "Выходим на пустыре, обливаем колымагу бензином и уходим в закат, не оборачиваясь на взрыв."),
            "ditch": ("Съехать в кювет", 150000, "На небольшой скорости эффектно съезжаем в мягкий кювет. Идеально для сторис в соцсетях."),
        }
    }
}

# --- КЛАВИАТУРЫ ---
def get_main_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    for cat_id, cat_data in MENU.items():
        kb.add(InlineKeyboardButton(cat_data["title"], callback_data=f"cat_{cat_id}"))
    kb.add(InlineKeyboardButton("🌟 СВОЙ ВАРИАНТ (ИНДИВИДУАЛЬНО)", callback_data="custom_order"))
    return kb

def get_category_kb(cat_id):
    kb = InlineKeyboardMarkup(row_width=1)
    for item_id, data in MENU[cat_id]["items"].items():
        kb.add(InlineKeyboardButton(f"{data[0]} — {data[1]}₽", callback_data=f"info_{item_id}"))
    kb.add(InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu"))
    return kb

def get_payment_kb(item_id, is_custom=False):
    prefix = "paid_custom" if is_custom else f"paid_{item_id}"
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("✅ ОПЛАЧЕНО", callback_data=prefix))
    kb.add(InlineKeyboardButton("❌ ОТМЕНА", callback_data="main_menu"))
    return kb

# --- ОБРАБОТЧИКИ ---
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer("🚕 <b>Crazy Taxi Bot</b>\nЗдесь можно заказать шоу, которое вы не забудете никогда.", reply_markup=get_main_kb())

@dp.callback_query_handler(lambda c: c.data == "main_menu")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text("🔥 <b>ВЫБИРАЙТЕ КАТЕГОРИЮ БЕЗУМИЯ:</b>", reply_markup=get_main_kb())

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
        f"<i>После оплаты нажмите кнопку ниже.</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_payment_kb(item_id))

# --- ЛОГИКА ИНДИВИДУАЛЬНОЙ УСЛУГИ ---
@dp.callback_query_handler(lambda c: c.data == "custom_order")
async def custom_step_1(callback: types.CallbackQuery):
    await callback.message.edit_text("✍️ <b>Опишите ваше пожелание и цену.</b>\n\nНапишите в ответном сообщении, что я должен сделать и сколько вы готовы за это заплатить.\n<i>Пример: Покрасить волосы в синий прямо за рулем — 5000р</i>")

@dp.message_handler(lambda m: not m.text.startswith('/'))
async def handle_custom_text(message: types.Message):
    # Пересылаем ваше пожелание водителю
    await bot.send_message(
        DRIVER_ID,
        f"🧩 <b>ПРЕДЛОЖЕНИЕ ОТ КЛИЕНТА!</b>\n"
        f"👤 От: {md.quote_html(message.from_user.full_name)}\n"
        f"💬 Текст: <i>{md.quote_html(message.text)}</i>\n\n"
        f"Если согласны — напишите клиенту в личку или ждите оплаты (если указана цена).",
        reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("✅ ПРЕДЛОЖИТЬ ОПЛАТИТЬ", callback_data=f"askpay_{message.from_user.id}"))
    )
    await message.answer("✅ <b>Ваше предложение передано водителю!</b>\nЕсли он согласится, он выставит счет или свяжется с вами.")

@dp.callback_query_handler(lambda c: c.data.startswith("askpay_"))
async def ask_payment(callback: types.CallbackQuery):
    user_id = callback.data.split("_")[1]
    text = (
        f"🎯 <b>ВОДИТЕЛЬ СОГЛАСЕН!</b>\n\n"
        f"Для выполнения вашей индивидуальной услуги переведите согласованную сумму на реквизиты:\n"
        f"<code>{REQUISITES}</code>\n\n"
        f"И нажмите кнопку подтверждения."
    )
    await bot.send_message(user_id, text, reply_markup=get_payment_kb("custom", is_custom=True))
    await callback.answer("Запрос на оплату отправлен клиенту.")

# --- ПОДТВЕРЖДЕНИЕ ОПЛАТЫ ---
@dp.callback_query_handler(lambda c: c.data.startswith("paid_"))
async def final_notify(callback: types.CallbackQuery):
    is_custom = "custom" in callback.data
    await callback.message.edit_text("⌛ <b>Запрос отправлен водителю.</b> Дождитесь подтверждения в чате.")
    
    msg = "💰 <b>КЛИЕНТ УТВЕРЖДАЕТ, ЧТО ОПЛАТИЛ!</b>"
    if is_custom:
        msg += "\n(Индивидуальный заказ)"
    
    await bot.send_message(DRIVER_ID, msg)

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
