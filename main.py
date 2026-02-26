import os
import logging
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice

# --- КОНФИГУРАЦИЯ ---
# Бот ищет эти имена в разделе "Переменные" на Amvera
API_TOKEN = os.getenv('API_TOKEN')
PAYMENT_TOKEN = os.getenv('PAYMENT_TOKEN')
DRIVER_ID = os.getenv('DRIVER_ID')
LAWYER_URL = "https://t.me/Ai_advokatrobot"

logging.basicConfig(level=logging.INFO)

# Проверка наличия токена, чтобы бот не падал без ошибки
if not API_TOKEN:
    logging.error("API_TOKEN не найден! Проверьте переменные в Amvera.")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# --- МЕНЮ УСЛУГ ---
MENU = {
    "BASE": {
        "title": "🛌 БЫТОВОЙ СЮРРЕАЛИЗМ",
        "items": {
            "sleep": ("Сон на заднем (15 мин)", 150, "Подушка включена"),
            "fairy": ("Сказка на ночь", 300, "Инструкция к освежителю"),
            "unboxing": ("Распаковка покупок", 500, "Восхищаюсь едой"),
            "grandma": ("Заботливая бабушка", 800, "Почему без шапки?"),
        }
    },
    "CRAZY": {
        "title": "🔞 ДРАЙВЕР-ХАРДКОР",
        "items": {
            "naked": ("Полностью голый водитель", 15000, "Свобода"),
            "dance": ("Танцы на светофоре", 15000, "Шоу на красный"),
            "tarzan": ("Водитель-Тарзан", 50000, "Голый + крик в окно"),
        }
    },
    "VIP": {
        "title": "💎 VIP УСЛУГИ",
        "items": {
            "escort": ("Кортеж из 1 авто", 25000, "По центру двух полос"),
            "carpet": ("Красная дорожка", 15000, "Скатерти у двери"),
            "interview": ("Интервью", 20000, "Весь путь с микрофоном"),
        }
    },
    "FINAL": {
        "title": "🔥 ТОТАЛЬНОЕ БЕЗУМИЕ",
        "items": {
            "burn": ("СЖЕЧЬ МАШИНУ", 1000000, "Уходим красиво"),
            "ditch": ("Съехать в кювет", 150000, "Для сторис"),
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
        kb.add(InlineKeyboardButton(f"{data[0]} — {data[1]}₽", callback_data=f"buy_{item_id}"))
    kb.add(InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu"))
    return kb

def get_decision_kb(user_id, item_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ ПРИНЯТЬ", callback_data=f"decide_ok_{user_id}_{item_id}"),
        InlineKeyboardButton("❌ ОТКАЗАТЬ", callback_data=f"decide_no_{user_id}_{item_id}")
    )
    return kb

# --- ОБРАБОТЧИКИ ---
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    text = "⚠️ **ОТКАЗ ОТ ОТВЕТСТВЕННОСТИ**\n\nВы согласны на безумный арт-перформанс?"
    await message.answer(text, reply_markup=get_policy_kb(), parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data == "accept_policy")
async def start_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("🔥 Выбирай категорию:", reply_markup=get_main_kb())

@dp.callback_query_handler(lambda c: c.data == "main_menu")
async def main_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("Выбирай категорию:", reply_markup=get_main_kb())

@dp.callback_query_handler(lambda c: c.data.startswith("cat_"))
async def show_cat(callback: types.CallbackQuery):
    cat_id = callback.data.split("_")[1]
    await callback.message.edit_text(f"🚀 {MENU[cat_id]['title']}:", reply_markup=get_category_kb(cat_id))

@dp.callback_query_handler(lambda c: c.data.startswith("buy_"))
async def handle_buy(callback: types.CallbackQuery):
    item_id = callback.data.split("_")[1]
    item_data = None
    for cat in MENU.values():
        if item_id in cat["items"]:
            item_data = cat["items"][item_id]
            break
    
    if PAYMENT_TOKEN:
        await bot.send_invoice(
            callback.from_user.id,
            title=item_data[0],
            description=item_data[2],
            provider_token=PAYMENT_TOKEN,
            currency="rub",
            prices=[LabeledPrice(label="Crazy Service", amount=item_data[1] * 100)],
            payload=f"{callback.from_user.id}_{item_id}"
        )
    else:
        await callback.answer("Оплата недоступна (нет токена)", show_alert=True)

@dp.pre_checkout_query_handler(lambda q: True)
async def checkout_confirm(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message_handler(content_types=types.ContentType.SUCCESSFUL_PAYMENT)
async def payment_done(message: types.Message):
    user_id, item_id = message.successful_payment.invoice_payload.split("_")
    await message.answer("⌛ Ждем подтверждения от водителя...")
    await bot.send_message(
        DRIVER_ID, 
        f"💰 **ЗАКАЗ!**\nУслуга: {item_id}\nКлиент: @{message.from_user.username}",
        reply_markup=get_decision_kb(user_id, item_id)
    )

@dp.callback_query_handler(lambda c: c.data.startswith("decide_"))
async def driver_action(callback: types.CallbackQuery):
    _, action, user_id, item_id = callback.data.split("_")
    if action == "ok":
        await bot.send_message(user_id, "✅ **ВОДИТЕЛЬ ПРИНЯЛ!**")
    else:
        await bot.send_message(user_id, "❌ **ОТКАЗАНО.** Деньги вернутся.")
    await callback.message.edit_text(f"Решение принято: {action}")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
