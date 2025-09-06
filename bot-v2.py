import os
import json
import logging
import secrets
from dotenv import load_dotenv
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import InputMediaPhoto, InputMediaVideo
from aiogram.dispatcher.webhook import get_new_configured_app

# === ENV & LOGGING ===
load_dotenv()
logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://yourdomain.com
WEBHOOK_PATH = "/webhook"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 8080))

ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))

MEDIA_INDEX_FILE = 'media_index.json'
AD_CHANNELS_FILE = 'ad_channels.json'
CHANNEL_JOINS_FILE = 'channel_joins.json'

# === INIT ===
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# === UTILS ===
def load_json(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f)

media_index = load_json(MEDIA_INDEX_FILE)
ad_channels = load_json(AD_CHANNELS_FILE)
channel_joins = load_json(CHANNEL_JOINS_FILE)

def is_admin(user_id):
    return user_id in ADMIN_IDS

# === HEALTHCHECK ===
async def healthcheck(request):
    return web.Response(text="OK")

# === WEBHOOK SETUP ===
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL + WEBHOOK_PATH)

async def on_shutdown(app):
    await bot.delete_webhook()

# === COMMAND HANDLERS ===
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.reply("👋 Welcome! This bot is ready to roll.")

@dp.message_handler(commands=['ping'])
async def ping(message: types.Message):
    await message.reply("🏓 Pong!")

@dp.message_handler(commands=['add'])
async def add_media(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.reply("🚫 You don't have permission to use this command.")

    if not message.reply_to_message or not message.reply_to_message.photo and not message.reply_to_message.video:
        return await message.reply("⚠️ Reply to a photo or video to add it.")

    media_id = secrets.token_hex(8)
    media_type = 'photo' if message.reply_to_message.photo else 'video'
    file_id = message.reply_to_message.photo[-1].file_id if media_type == 'photo' else message.reply_to_message.video.file_id

    media_index[media_id] = {'type': media_type, 'file_id': file_id}
    save_json(MEDIA_INDEX_FILE, media_index)

    await message.reply(f"✅ Media added with ID: `{media_id}`", parse_mode="Markdown")

@dp.message_handler(commands=['list'])
async def list_media(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.reply("🚫 You don't have permission to use this command.")

    if not media_index:
        return await message.reply("📭 No media indexed yet.")

    text = "\n".join([f"`{k}` - {v['type']}" for k, v in media_index.items()])
    await message.reply(f"📦 Indexed Media:\n{text}", parse_mode="Markdown")

@dp.message_handler(commands=['remove'])
async def remove_media(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.reply("🚫 You don't have permission to use this command.")

    args = message.get_args().strip()
    if args not in media_index:
        return await message.reply("❌ Invalid ID.")

    del media_index[args]
    save_json(MEDIA_INDEX_FILE, media_index)
    await message.reply(f"🗑️ Removed media with ID: `{args}`", parse_mode="Markdown")

@dp.message_handler(commands=['broadcast'])
async def broadcast(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.reply("🚫 You don't have permission to use this command.")

    args = message.get_args().strip()
    if args not in media_index:
        return await message.reply("❌ Invalid media ID.")

    media = media_index[args]
    for channel_id in ad_channels.values():
        try:
            if media['type'] == 'photo':
                await bot.send_photo(channel_id, media['file_id'])
            else:
                await bot.send_video(channel_id, media['file_id'])
        except Exception as e:
            logging.warning(f"Failed to send to {channel_id}: {e}")

    await message.reply("📢 Broadcast complete.")

@dp.message_handler(content_types=types.ContentType.NEW_CHAT_MEMBERS)
async def track_joins(message: types.Message):
    channel_id = str(message.chat.id)
    channel_joins[channel_id] = channel_joins.get(channel_id, 0) + len(message.new_chat_members)
    save_json(CHANNEL_JOINS_FILE, channel_joins)

# === MAIN ===
def main():
    app = web.Application()
    app.router.add_get("/kaithheathcheck", healthcheck)
    app.router.add_post(WEBHOOK_PATH, get_new_configured_app(dp, bot))
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)

if __name__ == "__main__":
    main()

