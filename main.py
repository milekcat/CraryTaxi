import os
import logging
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice

# --- КОНФИГУРАЦИЯ ---
# Подтягиваем данные из настроек хостинга (Amvera)
API_TOKEN = os.getenv('API_TOKEN')
PAYMENT_TOKEN = os.getenv('PAYMENT_TOKEN')
DRIVER_ID = os.getenv('DRIVER_ID')
LAWYER_URL = "https://t.me/Ai_advokatrobot"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# --- ПОЛНЫЙ ПЕРЕЧЕНЬ УСЛУГ ---
MENU = {
    "BASE": {
        "title": "🛌 БЫТОВОЙ СЮРРЕАЛИЗМ",
        "items": {
            "sleep": ("Сон на заднем (15 мин)", 150, "Подушка из куртки включена"),
            "fairy": ("Сказка на ночь", 300, "Инструкция к освежителю томным голосом"),
            "unboxing": ("Распаковка покупок", 500, "Восхищаюсь каждой сосиской"),
            "grandma": ("Заботливая бабушка", 800, "Ворчу, что вы без шапки"),
            "philosophy": ("Поиск смысла жизни", 1000, "Диспут о тленности бытия"),
            "scent": ("Ароматерапия 'Успех'", 600, "Пшикаю елочкой прямо в лицо"),
            "silent_super": ("Резервное молчание", 2000, "Делаю вид, что меня нет"),
        }
    },
    "HARDCORE": {
        "title": "🔞 ДРАЙВЕР-ХАРДКОР",
        "items": {
            "naked_top": ("Без футболки", 2000, "Летний вайб"),
            "hand_strip": ("Стриптиз руки", 2500, "Эротичное КПП"),
            "dance": ("Танцы на светофоре", 15000, "Шоу на каждом красном"),
            "tarzan": ("Водитель-Тарзан", 50000, "Голый + крик в окно"),
            "naked_full": ("Полностью голый", 15000, "Абсолютная свобода"),
            "champagne": ("Облить водителя", 20000, "Ваше шампанское — мой салон"),
            "slap": ("Дать подзатыльник", 10000, "Легкий, для стимула"),
        }
    },
    "SHOW": {
        "title": "🎭 ШОУ И ТРЮКИ",
        "items": {
            "shashki": ("Режим 'Шашки'", 3500, "Фонк + агрессивная езда"),
            "rockstar": ("Звезда рок-н-ролла", 15000, "Разбиваю гитару на финише"),
            "space": ("Выход в космос", 3000, "Окна настежь на 100 км/ч"),
            "kidnap": ("Имитация похищения", 7000, "Орем в окна вместе"),
            "stunt": ("Руление ногами", 12000, "5 секунд адреналина"),
            "love_mall": ("Крик 'Я ТЕБЯ ЛЮБЛЮ!'", 4000, "У ТЦ на всю парковку"),
        }
    },
    "VIP": {
        "title": "💎 VIP / ULTRA RICH",
        "items": {
            "escort": ("Кортеж (1 авто)", 25000, "По центру двух полос"),
            "carpet": ("Красная дорожка", 15000, "Скатерти из Ашана у двери"),
            "interview": ("Интервью со звездой", 20000, "Держу микрофон всю дорогу"),
            "shield": ("Живой щит", 40000, "Закрываю телом от ветра"),
            "alibi": ("Алиби для семьи", 3000, "Имитирую совещание по связи"),
            "hatiko": ("Услуга Хатико", 5000, "Грущу у окна 20 минут"),
            "gold": ("Золотой дождь", 20000, "Хлопушки с блестками в салоне"),
        }
    },
    "FINAL": {
        "title": "🔥 TOTAL DESTRUCTION",
        "items": {
            "burn_car": ("СЖЕЧЬ МАШИНУ", 1000000, "Уходим в закат красиво"),
            "ditch": ("Съехать в кювет", 150000, "Для эффектных сторис"),
            "trash": ("Протаранить бак", 50000, "Мусорный бак в щепки"),
            "one_way": ("Билет в один конец", 300000, "Едем, пока есть бензин"),
        }
    }
}

# --- КЛАВИАТУРЫ ---
def get_policy_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("✅ Я СОГЛАСЕН НА ВСЁ", callback_data="accept_policy"),
        InlineKeyboardButton("⚖️ СВЯЗЬ С АДВОКАТОМ", url=LAWYER_URL),
        InlineKeyboardButton("❌ Я СКУЧНЫЙ", callback_data="reject_policy")
    )
    return kb

def get_main_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    for cat_id, cat_data in MENU.items():
        kb.add(InlineKeyboardButton(cat_data["title"], callback_data=f"cat_{cat_id}"))
    kb.add(InlineKeyboardButton("🤫 ШЕПНУТЬ ВОДИТЕЛЮ", callback_data="whisper"))
    kb.add(InlineKeyboardButton("⚖️ АДВОКАТ", url=LAWYER_URL))
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
    text = (
        "⚠️ **ОТКАЗ ОТ ОТВЕТСТВЕННОСТИ (ОФЕРТА)**\n\n"
        "Нажимая кнопку, вы подтверждаете: вам 18+, вы вменяемы и согласны на "
        "арт-перформанс. Водитель может отказать в услуге.\n\n"
        "Юридическая поддержка: AI Адвокат."
    )
    await message.answer(text, reply_markup=get_policy_kb(), parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data == "accept_policy")
async def start_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("🔥 **ВЫ В ЗОНЕ БЕЗУМИЯ.** Категории:", reply_markup=get_main_kb())

@dp.callback_query_handler(lambda c: c.data == "main_menu")
async def main_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("Категории безумия:", reply_markup=get_main_kb())

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
    
    if item_data:
        await bot.send_invoice(
            callback.from_user.id,
            title=item_data[0],
            description=item_data[2],
            provider_token=PAYMENT_TOKEN,
            currency="rub",
            prices=[LabeledPrice(label="Crazy Service", amount=item_data[1] * 100)],
            payload=f"{callback.from_user.id}_{item_id}"
        )

@dp.pre_checkout_query_handler(lambda q: True)
async def checkout_confirm(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message_handler(content_types=types.ContentType.SUCCESSFUL_PAYMENT)
async def payment_done(message: types.Message):
    user_id, item_id = message.successful_payment.invoice_payload.split("_")
    await message.answer("⌛ Ждем подтверждения от водителя... Если он откажется, деньги вернутся.")
    
    await bot.send_message(
        DRIVER_ID, 
        f"💰 **НОВЫЙ ЗАКАЗ!**\nУслуга: {item_id}\nКлиент: @{message.from_user.username}",
        reply_markup=get_decision_kb(user_id, item_id)
    )

@dp.callback_query_handler(lambda c: c.data.startswith("decide_"))
async def driver_action(callback: types.CallbackQuery):
    _, action, user_id, item_id = callback.data.split("_")
    if action == "ok":
        await bot.send_message(user_id, "✅ **ВОДИТЕЛЬ ПРИНЯЛ ЗАКАЗ!** Шоу начинается.")
        await callback.message.edit_text(f"🟢 Выполняешь: {item_id}")
    else:
        await bot.send_message(user_id, "❌ **ВОДИТЕЛЬ ОТКАЗАЛСЯ.** Средства будут возвращены.")
        await callback.message.edit_text(f"🔴 Отказано: {item_id}")

@dp.callback_query_handler(lambda c: c.data == "whisper")
async def whisper(callback: types.CallbackQuery):
    await callback.message.answer("📝 Пиши анонимно, я передам водителю:")

@dp.message_handler(lambda m: not m.text.startswith('/'))
async def forward_msg(message: types.Message):
    if str(message.from_user.id) != str(DRIVER_ID):
        await bot.send_message(DRIVER_ID, f"🤫 **Шепот:** {message.text}")
        await message.answer("Передано.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
