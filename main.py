import asyncio
import logging
import os
import json
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import WebAppInfo, MenuButtonWebApp
from aiogram.client.default import DefaultBotProperties
from aiohttp import web

# --- НАСТРОЙКИ ---
logging.basicConfig(level=logging.INFO)
API_TOKEN = os.getenv("API_TOKEN")
OWNER_ID = os.getenv("DRIVER_ID") # ID Старосты

# Ссылка на ваш веб-сервер (в Amvera это будет https://your-app-url.amvera.io)
# Пока ставим заглушку, позже заменим на реальный URL
WEBAPP_HOST = '0.0.0.0'
WEBAPP_PORT = 8080
BASE_URL = os.getenv("APP_URL", "https://your-domain.com") 

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# --- ТЕКСТЫ "ИЗВОЗЧИКА" ---
WELCOME_TEXT = (
    "🐎 <b>Здравия желаю, Барин!</b>\n\n"
    "Добро пожаловать в артель <b>«Весёлый Извозчик»</b>!\n"
    "У нас не просто телега с мотором, у нас — душа нараспашку.\n\n"
    "📜 <b>В программе:</b>\n"
    "• Ямщик-Психолог (выслушает кручину)\n"
    "• Пляски на тракте (на светофоре)\n"
    "• Огненная Масленица (сжигание повозки)\n\n"
    "Жми кнопку внизу, выбирай потеху и погнали!"
)

# --- БОТ ЛОГИКА ---
@dp.message(Command("start"))
async def start(message: types.Message):
    # Кнопка, открывающая Mini App
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🚪 ОТКРЫТЬ ЛАВКУ", web_app=WebAppInfo(url=f"{BASE_URL}/"))]
    ])
    await message.answer(WELCOME_TEXT, reply_markup=kb)
    
    # Устанавливаем кнопку меню (слева внизу)
    await bot.set_chat_menu_button(
        chat_id=message.chat.id,
        menu_button=MenuButtonWebApp(text="🚖 Вызвать Извозчика", web_app=WebAppInfo(url=f"{BASE_URL}/"))
    )

# --- ВЕБ-СЕРВЕР (ФРОНТЕНД) ---
async def web_handler(request):
    # Отдаем HTML страницу (код ниже)
    with open('index.html', 'r', encoding='utf-8') as f:
        content = f.read()
    return web.Response(text=content, content_type='text/html')

async def order_handler(request):
    # Принимаем заказ из Mini App
    data = await request.json()
    user_id = data.get('user_id')
    service = data.get('service')
    price = data.get('price')
    
    # Уведомляем в чат
    await bot.send_message(
        chat_id=user_id,
        text=f"✅ <b>Заказ принят!</b>\nПотеха: {service}\nМзда: {price} руб.\n\nИщем свободного ямщика..."
    )
    return web.json_response({"status": "ok"})

# --- ЗАПУСК ---
async def on_startup(app):
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))

def main():
    app = web.Application()
    app.router.add_get('/', web_handler)
    app.router.add_post('/order', order_handler)
    app.on_startup.append(on_startup)
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)

if __name__ == "__main__":
    main()
