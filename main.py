import os
import json
import asyncio
import requests
import aiohttp

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    FSInputFile
)
from aiogram.filters import (
    Command,
    CommandStart
)
from aiogram.client.default import (
    DefaultBotProperties
)
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import (
    AiohttpSession
)

# ==================================================
# CONFIG
# ==================================================

BOT_TOKEN = "8373412574:AAHr9YtdIxVfxfNz6LTdYrfJepO47S2OmB4"

OWNER_ID = 5961230510

DEFAULT_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"

MODEL_ID = "eleven_multilingual_v2"

# ==================================================
# BOT
# ==================================================

session = AiohttpSession()

bot = Bot(
    token=BOT_TOKEN,
    session=session,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    )
)

dp = Dispatcher()

# ==================================================
# FILES
# ==================================================

TEMP_DIR = "temp"

API_FILE = "api_keys.json"

USER_FILE = "users.json"

os.makedirs(TEMP_DIR, exist_ok=True)

# ==================================================
# CREATE FILES
# ==================================================

if not os.path.exists(API_FILE):

    with open(API_FILE, "w") as f:

        json.dump([], f)

if not os.path.exists(USER_FILE):

    with open(USER_FILE, "w") as f:

        json.dump({}, f)

# ==================================================
# JSON HELPERS
# ==================================================

def load_json(path):

    with open(path, "r", encoding="utf-8") as f:

        return json.load(f)

def save_json(path, data):

    with open(path, "w", encoding="utf-8") as f:

        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False
        )

# ==================================================
# USER SETTINGS
# ==================================================

def get_users():

    return load_json(USER_FILE)

def save_users(data):

    save_json(USER_FILE, data)

def get_user_voice(user_id):

    users = get_users()

    user_id = str(user_id)

    if user_id not in users:

        users[user_id] = {
            "voice_id": DEFAULT_VOICE_ID
        }

        save_users(users)

    return users[user_id]["voice_id"]

def set_user_voice(user_id, voice_id):

    users = get_users()

    user_id = str(user_id)

    if user_id not in users:

        users[user_id] = {}

    users[user_id]["voice_id"] = voice_id

    save_users(users)

# ==================================================
# API HELPERS
# ==================================================

def load_keys():

    return load_json(API_FILE)

def save_keys(keys):

    save_json(API_FILE, keys)

# ==================================================
# GET WORKING API
# ==================================================

def get_working_key():

    keys = load_keys()

    for key in keys:

        try:

            url = (
                "https://api.elevenlabs.io/"
                "v1/user/subscription"
            )

            headers = {
                "xi-api-key": key
            }

            response = requests.get(
                url,
                headers=headers,
                timeout=20
            )

            if response.status_code != 200:

                continue

            data = response.json()

            used = data.get(
                "character_count",
                0
            )

            limit_ = data.get(
                "character_limit",
                0
            )

            if used < limit_:

                return key

        except:
            continue

    return None

# ==================================================
# START
# ==================================================

@dp.message(CommandStart())
async def start(message: Message):

    text = (
        "🎙 <b>Advanced ElevenLabs Bot</b>\n\n"

        "✅ Multi Language TTS\n"
        "✅ Voice To Text\n"
        "✅ Multi API Rotation\n"
        "✅ Auto Working API Detect\n"
        "✅ API Usage Checker\n"
        "✅ User Voice Selection\n"
        "✅ VPS Ready\n"
        "✅ Error Protected\n\n"

        "📌 Send text for voice.\n"
        "📌 Send voice for text.\n\n"

        "📚 /help"
    )

    await message.answer(text)

# ==================================================
# HELP
# ==================================================

@dp.message(Command("help"))
async def help_cmd(message: Message):

    text = (
        "📚 <b>Commands</b>\n\n"

        "👤 USER:\n"
        "/voices → voice list\n"
        "/setvoice ID → set voice\n"
        "/myvoice → current voice\n"
        "/limit → API stats\n\n"

        "👑 OWNER:\n"
        "/addapi KEY\n"
        "/removeapi KEY\n"
        "/apis"
    )

    await message.answer(text)

# ==================================================
# VOICES
# ==================================================

@dp.message(Command("voices"))
async def voices(message: Message):

    text = (
        "🎤 <b>Available Voices</b>\n\n"

        "🇺🇸 Rachel\n"
        "<code>21m00Tcm4TlvDq8ikWAM</code>\n\n"

        "🇺🇸 Adam\n"
        "<code>pNInz6obpgDQGcFmaJgB</code>\n\n"

        "🇺🇸 Bella\n"
        "<code>EXAVITQu4vr4xnSDxMaL</code>\n\n"

        "🇬🇧 Antoni\n"
        "<code>ErXwobaYiN019PkySvjV</code>\n\n"

        "🌍 Supports:\n"
        "Bangla\n"
        "English\n"
        "Hindi\n"
        "Arabic\n"
        "Spanish\n"
        "French\n"
        "Japanese\n"
        "Korean\n"
        "Urdu\n"
        "And More..."
    )

    await message.answer(text)

# ==================================================
# SET VOICE
# ==================================================

@dp.message(Command("setvoice"))
async def set_voice(message: Message):

    args = message.text.split(maxsplit=1)

    if len(args) < 2:

        await message.answer(
            "Usage:\n"
            "/setvoice VOICE_ID"
        )
        return

    voice_id = args[1].strip()

    set_user_voice(
        message.from_user.id,
        voice_id
    )

    await message.answer(
        "✅ Voice Updated."
    )

# ==================================================
# MY VOICE
# ==================================================

@dp.message(Command("myvoice"))
async def myvoice(message: Message):

    voice_id = get_user_voice(
        message.from_user.id
    )

    await message.answer(
        f"🎤 Current Voice:\n\n"
        f"<code>{voice_id}</code>"
    )

# ==================================================
# API LIMIT
# ==================================================

@dp.message(Command("limit"))
async def limit(message: Message):

    keys = load_keys()

    if not keys:

        await message.answer(
            "❌ No APIs Added."
        )
        return

    text = (
        "📊 <b>API Status</b>\n\n"
    )

    for i, key in enumerate(keys, start=1):

        try:

            url = (
                "https://api.elevenlabs.io/"
                "v1/user/subscription"
            )

            headers = {
                "xi-api-key": key
            }

            response = requests.get(
                url,
                headers=headers,
                timeout=20
            )

            if response.status_code != 200:

                text += (
                    f"{i}. ❌ Invalid API\n\n"
                )

                continue

            data = response.json()

            used = data.get(
                "character_count",
                0
            )

            limit_ = data.get(
                "character_limit",
                0
            )

            remain = limit_ - used

            text += (
                f"🔑 API {i}\n"
                f"📌 Used: {used}\n"
                f"📌 Limit: {limit_}\n"
                f"📌 Left: {remain}\n\n"
            )

        except:

            text += (
                f"{i}. ❌ Error\n\n"
            )

    await message.answer(text)

# ==================================================
# ADD API
# ==================================================

@dp.message(Command("addapi"))
async def add_api(message: Message):

    if message.from_user.id != OWNER_ID:

        return

    args = message.text.split(maxsplit=1)

    if len(args) < 2:

        await message.answer(
            "Usage:\n/addapi API_KEY"
        )
        return

    key = args[1].strip()

    keys = load_keys()

    if key in keys:

        await message.answer(
            "⚠️ API Already Exists."
        )
        return

    keys.append(key)

    save_keys(keys)

    await message.answer(
        "✅ API Added."
    )

# ==================================================
# REMOVE API
# ==================================================

@dp.message(Command("removeapi"))
async def remove_api(message: Message):

    if message.from_user.id != OWNER_ID:

        return

    args = message.text.split(maxsplit=1)

    if len(args) < 2:

        await message.answer(
            "Usage:\n/removeapi API_KEY"
        )
        return

    key = args[1].strip()

    keys = load_keys()

    if key not in keys:

        await message.answer(
            "❌ API Not Found."
        )
        return

    keys.remove(key)

    save_keys(keys)

    await message.answer(
        "🗑 API Removed."
    )

# ==================================================
# API LIST
# ==================================================

@dp.message(Command("apis"))
async def apis(message: Message):

    if message.from_user.id != OWNER_ID:

        return

    keys = load_keys()

    if not keys:

        await message.answer(
            "❌ No APIs."
        )
        return

    text = (
        "🔑 <b>Saved APIs</b>\n\n"
    )

    for i, key in enumerate(keys, start=1):

        short = (
            key[:10] + "..."
        )

        text += (
            f"{i}. <code>{short}</code>\n"
        )

    await message.answer(text)

# ==================================================
# TEXT TO SPEECH
# ==================================================

@dp.message(F.text)
async def text_to_speech(message: Message):

    if message.text.startswith("/"):

        return

    msg = await message.answer(
        "🎧 Generating Voice..."
    )

    api_key = get_working_key()

    if not api_key:

        await msg.edit_text(
            "❌ No Working API."
        )
        return

    voice_id = get_user_voice(
        message.from_user.id
    )

    url = (
        "https://api.elevenlabs.io/"
        f"v1/text-to-speech/{voice_id}"
    )

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }

    payload = {
        "text": message.text,
        "model_id": MODEL_ID
    }

    try:

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=120
        )

        if response.status_code != 200:

            await msg.edit_text(
                f"❌ Error:\n\n"
                f"{response.text}"
            )
            return

        file_path = (
            f"{TEMP_DIR}/"
            f"{message.message_id}.mp3"
        )

        with open(file_path, "wb") as f:

            f.write(response.content)

        voice = FSInputFile(file_path)

        await message.answer_voice(
            voice=voice
        )

        try:
            os.remove(file_path)
        except:
            pass

        await msg.delete()

    except Exception as e:

        await msg.edit_text(
            f"❌ Failed:\n\n{e}"
        )

# ==================================================
# VOICE TO TEXT
# ==================================================

@dp.message(F.voice)
async def speech_to_text(message: Message):

    msg = await message.answer(
        "📝 Converting Speech..."
    )

    api_key = get_working_key()

    if not api_key:

        await msg.edit_text(
            "❌ No Working API."
        )
        return

    try:

        tg_file = await bot.get_file(
            message.voice.file_id
        )

        ogg_path = (
            f"{TEMP_DIR}/"
            f"{message.message_id}.ogg"
        )

        await bot.download_file(
            tg_file.file_path,
            destination=ogg_path
        )

        url = (
            "https://api.elevenlabs.io/"
            "v1/speech-to-text"
        )

        headers = {
            "xi-api-key": api_key
        }

        data = {
            "model_id": "scribe_v1"
        }

        with open(
            ogg_path,
            "rb"
        ) as audio_file:

            files = {
                "file": audio_file
            }

            response = requests.post(
                url,
                headers=headers,
                files=files,
                data=data,
                timeout=180
            )

        try:
            os.remove(ogg_path)
        except:
            pass

        if response.status_code != 200:

            await msg.edit_text(
                f"❌ Error:\n\n"
                f"{response.text}"
            )
            return

        result = response.json()

        text = result.get(
            "text",
            "No Text Found"
        )

        await msg.edit_text(
            f"📝 <b>Text:</b>\n\n{text}"
        )

    except Exception as e:

        await msg.edit_text(
            f"❌ Failed:\n\n{e}"
        )

# ==================================================
# MAIN
# ==================================================

async def main():

    print("Bot Running...")

    while True:

        try:

            await dp.start_polling(
                bot,
                polling_timeout=60
            )

        except Exception as e:

            print(
                f"Restarting Bot: {e}"
            )

            await asyncio.sleep(5)

# ==================================================

if __name__ == "__main__":

    asyncio.run(main())
