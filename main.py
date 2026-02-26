import os
import logging
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- КОНФИГУРАЦИЯ ---
# Эти переменные должны быть прописаны в панели Amvera
API_TOKEN = os.getenv('API_TOKEN')
DRIVER_ID = os.getenv('DRIVER_ID')
REQUISITES = "+79012723729 Яндекс Банк"
LAWYER_URL = "https://t.me/Ai_advokatrobot"

logging.basicConfig(level=logging.INFO)

if not API_TOKEN:
    logging.error("API_TOKEN не найден в настройках Amvera!")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# --- МЕНЮ УСЛУГ ---
MENU = {
    "BASE": {
        "title": "🛌 БЫТОВОЙ СЮРРЕАЛИЗМ",
        "items": {
            "sleep": ("Сон на заднем (15 мин)", 150),
            "fairy": ("Сказка на ночь", 300),
            "unboxing": ("Распаковка покупок", 500),
            "grandma": ("Заботливая бабушка", 800),
        }
    },
    "CRAZY": {
        "title": "🔞 ДРАЙВЕР-ХАРДКОР",
        "items": {
            "naked": ("Полностью голый водитель", 15000),
            "dance": ("Танцы на светофоре", 15000),
            "tarzan": ("Водитель-Тарзан", 50000),
        }
    },
    "VIP": {
        "title": "💎 VIP УСЛУГИ",
        "items": {
            "escort": ("Кортеж из 1 авто", 25000),
            "carpet": ("Красная дорожка", 15000),
            "interview": ("Интервью", 20000),
        }
    },
    "FINAL": {
        "title": "🔥 ТОТАЛЬНОЕ БЕЗУМИЕ",
        "items": {
            "burn": ("СЖЕЧЬ МАШИНУ", 1000000),
            "ditch": ("Съехать в кювет", 150000),
        }
    }
}

# --- КЛАВИАТУРЫ ---
def get_policy_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("✅ Я СОГЛАСЕН НА ВСЁ", callback_data="accept_policy"),
        InlineKeyboardButton("⚖️ МОЙ АДВОКАТ", url=LAWYER_URL)
    )
    return kb

def get_main_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    for cat_id, cat_data in MENU.items():
        kb.add(InlineKeyboardButton(cat_data["title"], callback_data=f"cat_{cat_id}"))
    return kb

def get_category_kb(cat_id):
    kb = InlineKeyboardMarkup(row_width=1)
    for item_id, data in MENU[cat_id]["items"].items():
        kb.add(InlineKeyboardButton(f"{data[0]} — {data[1]}₽", callback_data=f"prebuy_{item_id}"))
    kb.add(InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu"))
    return kb

def get_payment_kb(item_id):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("✅ ОПЛАЧЕНО", callback_data=f"paid_{item_id}"))
    kb.add(InlineKeyboardButton("❌ ОТМЕНА", callback_data="main_menu"))
    return kb

def get_decision_kb(user_id, item_name):
    kb = InlineKeyboardMarkup(row_width=2)
    # Кодируем данные для водителя
    kb.add(
        InlineKeyboardButton("✅ ПРИНЯТЬ", callback_data=f"drvok_{user_id}"),
        InlineKeyboardButton("❌ ОТКАЗАТЬ", callback_data=f"drvno_{user_id}")
    )
    return kb

# --- ОБРАБОТЧИКИ ---
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    text = "⚠️ **ОТКАЗ ОТ ОТВЕТСТВЕННОСТИ**\n\nВы подтверждаете, что согласны на арт-перформанс и осознаете все риски?"
    await message.answer(text, reply_markup=get_policy_kb(), parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data == "accept_policy" or c.data == "main_menu")
async def show_main_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("🔥 **ВЫБИРАЙТЕ КАТЕГОРИЮ БЕЗУМИЯ:**", reply_markup=get_main_kb(), parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data.startswith("cat_"))
async def show_category(callback: types.CallbackQuery):
    cat_id = callback.data.split("_")[1]
    await callback.message.edit_text(f"🚀 **{MENU[cat_id]['title']}:**", reply_markup=get_category_kb(cat_id), parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data.startswith("prebuy_"))
async def prebuy_step(callback: types.CallbackQuery):
    item_id = callback.data.split("_")[1]
    
    # Ищем название и цену услуги
    item_data = None
    for cat in MENU.values():
        if item_id in cat["items"]:
            item_data = cat["items"][item_id]
            break
            
    text = (
        f"💳 **ОПЛАТА УСЛУГИ:**\n_{item_data[0]}_\n\n"
        f"💰 К оплате: **{item_data[1]}₽**\n\n"
        f"📌 Реквизиты: `{REQUISITES}`\n\n"
        f"Переведите сумму и нажмите кнопку ниже. Водитель получит уведомление сразу после нажатия."
    )
    await callback.message.edit_text(text, reply_markup=get_payment_kb(item_id), parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data.startswith("paid_"))
async def notify_driver(callback: types.CallbackQuery):
    item_id = callback.data.split("_")[1]
    user = callback.from_user
    
    # Ищем название услуги для уведомления
    item_name = "Неизвестная услуга"
    for cat in MENU.values():
        if item_id in cat["items"]:
            item_name = cat["items"][item_id][0]
            break

    await callback.message.edit_text("⌛ **Запрос отправлен водителю.**\nОжидайте подтверждения выполнения услуги.", parse_mode="Markdown")
    
    # Уведомляем водителя
    await bot.send_message(
        DRIVER_ID,
        f"💰 **НОВЫЙ ЗАКАЗ (ОПЛАТА ПОДТВЕРЖДЕНА КЛИЕНТОМ)!**\n\n"
        f"👤 Клиент: {user.mention} (ID: {user.id})\n"
        f"🛠 Услуга: **{item_name}**\n\n"
        f"Проверьте поступление средств и подтвердите готовность:",
        reply_markup=get_decision_kb(user.id, item_name),
        parse_mode="Markdown"
    )

@dp.callback_query_handler(lambda c: c.data.startswith("drv"))
async def driver_decision(callback: types.CallbackQuery):
    data = callback.data.split("_")
    action = data[0]
    user_id = data[1]
    
    if action == "drvok":
        await bot.send_message(user_id, "✅ **Водитель подтвердил оплату!** Начинаем шоу! 🚀")
        await callback.message.edit_text(callback.message.text + "\n\n🟢 **ВЫ ПРИНЯЛИ ЗАКАЗ**")
    else:
        await bot.send_message(user_id, "❌ **Водитель отклонил запрос.** Свяжитесь с водителем, если произошла ошибка оплаты.")
        await callback.message.edit_text(callback.message.text + "\n\n🔴 **ВЫ ОТКЛОНИЛИ ЗАКАЗ**")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
