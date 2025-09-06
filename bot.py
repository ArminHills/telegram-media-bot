import logging
import json
import asyncio
import secrets
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from dotenv import load_dotenv
load_dotenv()


# === CONFIG ===
import os

API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
AD_CHANNELS_FILE = 'ad_channels.json'
MEDIA_INDEX_FILE = 'media_index.json'
CHANNEL_JOINS_FILE = 'channel_joins.json'

# === INIT ===
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# === HELPERS ===
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

async def get_admin_channels():
    bot_id = (await bot.get_me()).id
    return [ch for ch in ad_channels if await is_bot_admin(ch, bot_id)]

async def is_bot_admin(channel, bot_id):
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=bot_id)
        return member.status == 'administrator'
    except:
        return False

async def get_enforced_channels():
    bot_id = (await bot.get_me()).id
    enforced = {}
    for channel, limit in ad_channels.items():
        if await is_bot_admin(channel, bot_id):
            current = channel_joins.get(channel, 0)
            if current < limit:
                enforced[channel] = limit
    return enforced

async def increment_channel_joins(user_id):
    for channel in await get_admin_channels():
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ['left', 'kicked']:
                channel_joins[channel] = channel_joins.get(channel, 0) + 1
        except:
            continue
    save_json(CHANNEL_JOINS_FILE, channel_joins)

# === ADMIN: ADD MEDIA ===
@dp.message_handler(commands=['add'])
async def add_media(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) == 4:
        _, media_id, url, media_type = parts
    elif len(parts) == 3:
        _, url, media_type = parts
        while True:
            media_id = secrets.token_hex(4)
            if media_id not in media_index:
                break
    else:
        await message.reply("⚠️ Usage:\n/add <id> <url> <photo|video>\nOR\n/add <url> <photo|video>")
        return

    item = {"url": url, "type": media_type}
    media_index.setdefault(media_id, []).append(item)
    save_json(MEDIA_INDEX_FILE, media_index)

    bot_username = (await bot.get_me()).username
    await message.reply(
        f"✅ Added to `{media_id}`\n🔗 Link: https://t.me/{bot_username}?start={media_id}",
        parse_mode="Markdown"
    )

# === ADMIN: LIST MEDIA ===
@dp.message_handler(commands=['list'])
async def list_media(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not media_index:
        await message.reply("📂 No media indexed yet.")
        return
    text = "📁 Indexed Media:\n"
    for media_id, items in media_index.items():
        types_list = ", ".join([item['type'] for item in items])
        text += f"- {media_id}: {types_list}\n"
    await message.reply(text)

# === ADMIN: REMOVE MEDIA ===
@dp.message_handler(commands=['remove'])
async def remove_media(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        _, media_id = message.text.split()
        if media_id in media_index:
            del media_index[media_id]
            save_json(MEDIA_INDEX_FILE, media_index)
            await message.reply(f"🗑️ Removed media ID: {media_id}")
        else:
            await message.reply("⚠️ Media ID not found.")
    except:
        await message.reply("⚠️ Usage: /remove <id>")

# === ADMIN: CHANNEL COMMANDS ===
@dp.message_handler(commands=['channels'])
async def list_channels(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not ad_channels:
        await message.reply("📂 No ad channels configured.")
        return
    text = "📢 Ad Channels:\n"
    for ch, limit in ad_channels.items():
        count = channel_joins.get(ch, 0)
        text += f"- {ch}: {count}/{limit} joins\n"
    await message.reply(text)

@dp.message_handler(commands=['addchannel'])
async def add_channel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        _, channel, limit = message.text.split()
        limit = int(limit)
        if channel in ad_channels:
            ad_channels[channel] += limit
            await message.reply(f"🔁 Extended {channel} by {limit}. New limit: {ad_channels[channel]}")
        else:
            ad_channels[channel] = limit
            await message.reply(f"✅ Added channel: {channel} with limit {limit}")
        save_json(AD_CHANNELS_FILE, ad_channels)
    except:
        await message.reply("⚠️ Usage: /addchannel <@channel> <limit>")

@dp.message_handler(commands=['removechannel'])
async def remove_channel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        _, channel = message.text.split()
        if channel in ad_channels:
            del ad_channels[channel]
            save_json(AD_CHANNELS_FILE, ad_channels)
            await message.reply(f"🗑️ Removed channel: {channel}")
        else:
            await message.reply("⚠️ Channel not found.")
    except:
        await message.reply("⚠️ Usage: /removechannel <@channel>")

# === USER: START / DEEP LINK ===
@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    args = message.get_args()
    if not args:
        await message.reply("👋 Welcome! Visit our main channel @YourMainChannel")
        return

    enforced_channels = await get_enforced_channels()
    not_joined = []
    for channel in enforced_channels:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=message.from_user.id)
            if member.status in ['left', 'kicked']:
                not_joined.append(channel)
        except Exception as e:
            logging.warning(f"Membership check failed for {channel}: {e}")
            not_joined.append(channel)

    if not_joined:
        buttons = [types.InlineKeyboardButton(text=ch, url=f"https://t.me/{ch.lstrip('@')}") for ch in not_joined]
        buttons.append(types.InlineKeyboardButton(text="✅ I've Joined", callback_data=f"check:{args}"))
        markup = types.InlineKeyboardMarkup(row_width=1).add(*buttons)
        await message.reply("🚫 Please join the following channels to access this content:", reply_markup=markup)
        return

    await send_media(message.chat.id, args)

# === CALLBACK: CHECK MEMBERSHIP ===
@dp.callback_query_handler(lambda c: c.data.startswith("check:"))
async def check_membership(callback: types.CallbackQuery):
    media_id = callback.data.split("check:")[1]
    user_id = callback.from_user.id

    enforced_channels = await get_enforced_channels()
    not_joined = []
    for channel in enforced_channels:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_joined.append(channel)
        except Exception as e:
            logging.warning(f"Membership re-check failed for {channel}: {e}")
            not_joined.append(channel)

    if not_joined:
        await callback.answer("🚫 You're still missing some channels!", show_alert=True)
        return

    await callback.answer("✅ Verified! Sending media...")
    await increment_channel_joins(user_id)
    await callback.message.delete()
    await send_media(callback.message.chat.id, media_id)

# === SEND MEDIA ===
async def send_media(chat_id, media_id):
    items = media_index.get(media_id)
    if not items:
        await bot.send_message(chat_id, "❌ Media not found.")
        return

    media_group = []
    for item in items:
        if item['type'] == 'photo':
            media_group.append(types.InputMediaPhoto(media=item['url']))
        elif item['type'] == 'video':
            media_group.append(types.InputMediaVideo(media=item['url']))
        else:
            await bot.send_message(chat_id, f"⚠️ Unsupported media type: {item['type']}")
            return

    try:
        sent_messages = await bot.send_media_group(chat_id=chat_id, media=media_group)
        warning = await bot.send_message(chat_id, "⚠️ This media will be deleted in 15 seconds. Save it if needed.")
        await asyncio.sleep(15)
        for msg in sent_messages:
            await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
        await bot.delete_message(chat_id=chat_id, message_id=warning.message_id)

    except Exception as e:
        await bot.send_message(chat_id, f"⚠️ Failed to send media group: {e}")

# === ADMIN: commands ===
@dp.message_handler(commands=['adminhelp'])
async def admin_help(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    text = (
        "🛠️ *Admin Command Reference:*\n\n"
        "/add `<id?>` `<url>` `<photo|video>` — Add media to a collection (ID optional)\n"
        "/list — View all indexed media collections\n"
        "/remove `<id>` — Delete a media collection\n\n"
        "/addchannel `<@channel>` `<limit>` — Add or extend an ad channel with a join limit\n"
        "/removechannel `<@channel>` — Remove an ad channel\n"
        "/channels — View current ad channels and join stats\n\n"
        "/joinstats — View total verified joins per channel\n"
        "/adminhelp — Show this command reference"
    )

    await message.reply(text, parse_mode="Markdown")

from aiohttp import web
from aiogram.dispatcher.webhook import SimpleRequestHandler, setup_application

WEBHOOK_HOST = 'https://your-leapcell-domain.leapcell.dev'  # Replace with your actual Leapcell domain
WEBHOOK_PATH = f'/webhook/{API_TOKEN}'
WEBHOOK_URL = f'{WEBHOOK_HOST}{WEBHOOK_PATH}'

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app):
    await bot.delete_webhook()

app = web.Application()
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
setup_application(app, dp, bot=bot)

if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=8080)



# === RUN ===
#if __name__ == '__main__':
#    executor.start_polling(dp, skip_updates=True)

