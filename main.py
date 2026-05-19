import asyncio
import html
import json
import logging
import os
import time
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, Message

# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DEFAULT_VOICE_ID = os.getenv("DEFAULT_VOICE_ID", "EXAVITQu4vr4xnSDxMaL").strip()
DEFAULT_MODEL_ID = os.getenv("DEFAULT_MODEL_ID", "eleven_multilingual_v2").strip()
PORT = int(os.getenv("PORT", "10000"))

API_FILE = "api_keys.json"
USER_FILE = "users.json"

TEMP_DIR = "temp"  # kept for compatibility, not heavily used
os.makedirs(TEMP_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("elevenlabs-bot")

# =========================================================
# SAFETY CHECKS
# =========================================================

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Set it in environment variables.")
if OWNER_ID == 0:
    raise RuntimeError("OWNER_ID is missing or invalid. Set your Telegram numeric ID.")

# =========================================================
# BOT / DP
# =========================================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

# =========================================================
# FILE HELPERS
# =========================================================

def _ensure_json_file(path: str, default_data: Any) -> None:
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=2, ensure_ascii=False)

_ensure_json_file(API_FILE, [])
_ensure_json_file(USER_FILE, {})


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_keys() -> List[str]:
    data = load_json(API_FILE)
    return data if isinstance(data, list) else []


def save_keys(keys: List[str]) -> None:
    save_json(API_FILE, keys)


def load_users() -> Dict[str, Any]:
    data = load_json(USER_FILE)
    return data if isinstance(data, dict) else {}


def save_users(users: Dict[str, Any]) -> None:
    save_json(USER_FILE, users)

# =========================================================
# USER VOICE SETTINGS
# =========================================================

def get_user_voice(user_id: int) -> str:
    users = load_users()
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"voice_id": DEFAULT_VOICE_ID}
        save_users(users)
    voice_id = users[uid].get("voice_id", DEFAULT_VOICE_ID)
    return str(voice_id).strip() or DEFAULT_VOICE_ID


def set_user_voice(user_id: int, voice_id: str) -> None:
    users = load_users()
    uid = str(user_id)
    if uid not in users:
        users[uid] = {}
    users[uid]["voice_id"] = voice_id.strip()
    save_users(users)

# =========================================================
# HTTP SESSION
# =========================================================

http_session: Optional[aiohttp.ClientSession] = None

def get_http_session() -> aiohttp.ClientSession:
    if http_session is None or http_session.closed:
        raise RuntimeError("HTTP session is not ready.")
    return http_session

# =========================================================
# HELPERS
# =========================================================

def is_owner(message: Message) -> bool:
    return bool(message.from_user) and message.from_user.id == OWNER_ID


def mask_key(key: str) -> str:
    if len(key) <= 12:
        return key[:4] + "..." if len(key) > 4 else "****"
    return f"{key[:8]}...{key[-4:]}"


def split_text(text: str, limit: int = 3800) -> List[str]:
    parts = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        parts.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts


async def safe_answer(message: Message, text: str) -> None:
    for chunk in split_text(text):
        await message.answer(chunk)


async def safe_edit(message: Message, text: str) -> None:
    try:
        await message.edit_text(text)
    except Exception:
        await message.answer(text)


def fmt_num(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except Exception:
        return "0"

# =========================================================
# ELEVENLABS API
# =========================================================

async def eleven_get_subscription(api_key: str) -> Optional[Dict[str, Any]]:
    session = get_http_session()
    url = "https://api.elevenlabs.io/v1/user/subscription"
    headers = {"xi-api-key": api_key}

    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                return None
            return await resp.json()
    except Exception:
        return None


async def get_working_key() -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Returns the first API key that is valid and still has quota.
    """
    keys = load_keys()
    if not keys:
        return None, None

    for key in keys:
        data = await eleven_get_subscription(key)
        if not data:
            continue
        used = int(data.get("character_count", 0) or 0)
        limit_ = int(data.get("character_limit", 0) or 0)
        if limit_ <= 0:
            # Some plans may behave differently; treat as usable if API responds.
            return key, data
        if used < limit_:
            return key, data

    return None, None


async def eleven_tts(api_key: str, voice_id: str, text: str, model_id: str = DEFAULT_MODEL_ID) -> Tuple[bool, Optional[bytes], str]:
    """
    Generates MP3 audio bytes.
    """
    session = get_http_session()
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": model_id,
    }

    try:
        async with session.post(
            url,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            body = await resp.read()
            if resp.status != 200:
                try:
                    error_text = body.decode("utf-8", errors="ignore")
                except Exception:
                    error_text = f"HTTP {resp.status}"
                return False, None, error_text
            return True, body, ""
    except Exception as e:
        return False, None, str(e)


async def eleven_stt(api_key: str, audio_bytes: bytes, filename: str = "voice.ogg") -> Tuple[bool, str]:
    session = get_http_session()
    url = "https://api.elevenlabs.io/v1/speech-to-text"
    headers = {"xi-api-key": api_key}

    form = aiohttp.FormData()
    form.add_field(
        "file",
        audio_bytes,
        filename=filename,
        content_type="application/octet-stream",
    )
    form.add_field("model_id", "scribe_v1")

    try:
        async with session.post(
            url,
            headers=headers,
            data=form,
            timeout=aiohttp.ClientTimeout(total=180),
        ) as resp:
            text_body = await resp.text()
            if resp.status != 200:
                return False, text_body
            try:
                data = json.loads(text_body)
                return True, str(data.get("text", ""))
            except Exception:
                return True, text_body
    except Exception as e:
        return False, str(e)

# =========================================================
# COMMANDS
# =========================================================

@dp.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(
        "🎙 <b>Advanced ElevenLabs Bot</b>\n\n"
        "✅ Text → Audio\n"
        "✅ Voice → Text\n"
        "✅ Bangla + many languages\n"
        "✅ Multi API rotation\n"
        "✅ Owner API management\n"
        "✅ Render-friendly health route\n\n"
        "Send any text for voice.\n"
        "Send any voice note for transcription.\n\n"
        "Use /help"
    )


@dp.message(Command("help"))
async def help_cmd(message: Message) -> None:
    text = (
        "📚 <b>Commands</b>\n\n"
        "<b>User</b>\n"
        "/start\n"
        "/help\n"
        "/voices\n"
        "/setvoice VOICE_ID\n"
        "/myvoice\n"
        "/ping\n\n"
        "<b>Owner</b>\n"
        "/addapi API_KEY\n"
        "/removeapi API_KEY\n"
        "/apis\n"
        "/limit\n"
        "/stats\n\n"
        "<b>Notes</b>\n"
        "• Text is converted using <code>eleven_multilingual_v2</code>\n"
        "• Output is sent as audio for stability\n"
        "• Voice transcription uses <code>scribe_v1</code>"
    )
    await message.answer(text)


@dp.message(Command("ping"))
async def ping(message: Message) -> None:
    await message.answer("✅ Alive")


@dp.message(Command("voices"))
async def voices(message: Message) -> None:
    text = (
        "🎤 <b>Default voice IDs</b>\n\n"
        "Rachel  → <code>21m00Tcm4TlvDq8ikWAM</code>\n"
        "Adam    → <code>pNInz6obpgDQGcFmaJgB</code>\n"
        "Bella   → <code>EXAVITQu4vr4xnSDxMaL</code>\n"
        "Antoni  → <code>ErXwobaYiN019PkySvjV</code>\n\n"
        "You can also use any valid ElevenLabs voice ID with /setvoice.\n\n"
        "🌍 The model supports Bangla and many other languages."
    )
    await message.answer(text)


@dp.message(Command("myvoice"))
async def myvoice(message: Message) -> None:
    voice_id = get_user_voice(message.from_user.id)
    await message.answer(f"🎤 Current voice:\n\n<code>{html.escape(voice_id)}</code>")


@dp.message(Command("setvoice"))
async def setvoice(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage:\n/setvoice VOICE_ID")
        return

    voice_id = parts[1].strip()
    if not voice_id:
        await message.answer("Voice ID cannot be empty.")
        return

    set_user_voice(message.from_user.id, voice_id)
    await message.answer("✅ Voice updated.")


@dp.message(Command("addapi"))
async def addapi(message: Message) -> None:
    if not is_owner(message):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage:\n/addapi API_KEY")
        return

    key = parts[1].strip()
    if not key.startswith("sk_"):
        await message.answer("⚠️ That does not look like an ElevenLabs API key.")
        return

    keys = load_keys()
    if key in keys:
        await message.answer("⚠️ API already saved.")
        return

    keys.append(key)
    save_keys(keys)
    await message.answer("✅ API added.")


@dp.message(Command("removeapi"))
async def removeapi(message: Message) -> None:
    if not is_owner(message):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage:\n/removeapi API_KEY")
        return

    key = parts[1].strip()
    keys = load_keys()
    if key not in keys:
        await message.answer("❌ API not found.")
        return

    keys.remove(key)
    save_keys(keys)
    await message.answer("🗑 API removed.")


@dp.message(Command("apis"))
async def apis(message: Message) -> None:
    if not is_owner(message):
        return

    keys = load_keys()
    if not keys:
        await message.answer("❌ No API keys saved.")
        return

    text = ["🔑 <b>Saved API keys</b>\n"]
    for i, key in enumerate(keys, start=1):
        text.append(f"{i}. <code>{html.escape(mask_key(key))}</code>")
    await safe_answer(message, "\n".join(text))


@dp.message(Command("limit"))
async def limit(message: Message) -> None:
    if not is_owner(message):
        return

    keys = load_keys()
    if not keys:
        await message.answer("❌ No API keys saved.")
        return

    lines = ["📊 <b>API Usage / Limits</b>\n"]
    for i, key in enumerate(keys, start=1):
        data = await eleven_get_subscription(key)
        if not data:
            lines.append(f"{i}. ❌ Invalid / unreachable API → <code>{html.escape(mask_key(key))}</code>\n")
            continue

        used = int(data.get("character_count", 0) or 0)
        limit_ = int(data.get("character_limit", 0) or 0)
        remaining = max(limit_ - used, 0)
        percent = (used / limit_ * 100.0) if limit_ > 0 else 0.0

        lines.append(
            f"{i}. <code>{html.escape(mask_key(key))}</code>\n"
            f"   Used: <b>{fmt_num(used)}</b>\n"
            f"   Limit: <b>{fmt_num(limit_)}</b>\n"
            f"   Left: <b>{fmt_num(remaining)}</b>\n"
            f"   Used %: <b>{percent:.2f}%</b>\n"
        )

    await safe_answer(message, "\n".join(lines))


@dp.message(Command("stats"))
async def stats(message: Message) -> None:
    if not is_owner(message):
        return

    keys = load_keys()
    valid = 0
    invalid = 0
    active = 0

    for key in keys:
        data = await eleven_get_subscription(key)
        if not data:
            invalid += 1
            continue
        valid += 1
        used = int(data.get("character_count", 0) or 0)
        limit_ = int(data.get("character_limit", 0) or 0)
        if limit_ <= 0 or used < limit_:
            active += 1

    await message.answer(
        "📈 <b>Bot Stats</b>\n\n"
        f"Saved keys: <b>{len(keys)}</b>\n"
        f"Valid keys: <b>{valid}</b>\n"
        f"Invalid keys: <b>{invalid}</b>\n"
        f"Active keys: <b>{active}</b>\n"
        f"Registered users file: <b>{len(load_users())}</b>"
    )

# =========================================================
# MESSAGE HANDLERS
# =========================================================

@dp.message(F.text)
async def text_to_speech(message: Message) -> None:
    if not message.text or message.text.startswith("/"):
        return

    processing = await message.answer("🎧 Generating audio...")

    api_key, sub_data = await get_working_key()
    if not api_key:
        await processing.edit_text("❌ No working ElevenLabs API key available.")
        return

    voice_id = get_user_voice(message.from_user.id)
    safe_text = message.text.strip()
    if not safe_text:
        await processing.edit_text("⚠️ Empty text.")
        return

    ok, audio_bytes, error = await eleven_tts(api_key, voice_id, safe_text, DEFAULT_MODEL_ID)
    if not ok or not audio_bytes:
        await processing.edit_text(f"❌ TTS failed.\n\n<code>{html.escape(error[:1500])}</code>")
        return

    try:
        audio = BufferedInputFile(audio_bytes, filename="elevenlabs.mp3")
        await message.answer_audio(
            audio=audio,
            caption="🎧 Generated by ElevenLabs",
        )
        await processing.delete()
    except Exception as e:
        await processing.edit_text(f"❌ Failed to send audio.\n\n<code>{html.escape(str(e))}</code>")


@dp.message(F.voice)
async def voice_to_text(message: Message) -> None:
    processing = await message.answer("📝 Transcribing voice...")

    api_key, sub_data = await get_working_key()
    if not api_key:
        await processing.edit_text("❌ No working ElevenLabs API key available.")
        return

    try:
        tg_file = await bot.get_file(message.voice.file_id)
        bio = BytesIO()
        await bot.download_file(tg_file.file_path, destination=bio)
        audio_bytes = bio.getvalue()

        ok, result = await eleven_stt(api_key, audio_bytes, filename="voice.ogg")
        if not ok:
            await processing.edit_text(f"❌ STT failed.\n\n<code>{html.escape(result[:1500])}</code>")
            return

        clean = result.strip() or "No text found"
        await processing.edit_text(f"📝 <b>Text:</b>\n\n{html.escape(clean)}")
    except Exception as e:
        await processing.edit_text(f"❌ Failed.\n\n<code>{html.escape(str(e))}</code>")

# =========================================================
# WEB SERVER FOR RENDER / HEALTH CHECK
# =========================================================

async def root(_: web.Request) -> web.Response:
    return web.Response(text="Bot is running.")

async def run_web_server() -> None:
    app = web.Application()
    app.router.add_get("/", root)
    app.router.add_get("/health", root)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("Web server started on port %s", PORT)

    # keep the task alive
    await asyncio.Event().wait()

# =========================================================
# BOT LOOP
# =========================================================

async def run_bot() -> None:
    update_types = dp.resolve_used_update_types()
    while True:
        try:
            logger.info("Starting bot polling...")
            await dp.start_polling(bot, allowed_updates=update_types, polling_timeout=60)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("Polling crashed: %s", e)
            await asyncio.sleep(5)

# =========================================================
# MAIN
# =========================================================

async def main() -> None:
    global http_session
    timeout = aiohttp.ClientTimeout(total=180)
    connector = aiohttp.TCPConnector(limit=20, ttl_dns_cache=300)
    http_session = aiohttp.ClientSession(timeout=timeout, connector=connector)

    try:
        await asyncio.gather(
            run_web_server(),
            run_bot(),
        )
    finally:
        if http_session and not http_session.closed:
            await http_session.close()

if __name__ == "__main__":
    asyncio.run(main())
