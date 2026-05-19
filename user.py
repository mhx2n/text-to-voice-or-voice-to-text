"""
User-facing handlers: /start, TTS, STT, voice selection callbacks.
Users can only use the bot in private chat.
Owners can also use .t / .a in any chat.
"""
from __future__ import annotations

import html
import logging
from io import BytesIO

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

import api as eleven
import db
import keyboards as kb
from config import DEFAULT_MODEL_ID, OWNER_IDS, VOICE_LIBRARY

logger = logging.getLogger("bot.user")
router = Router()

_session = None


def set_session(session) -> None:
    global _session
    _session = session


# ─── Guards ──────────────────────────────────────────────────────────────────

def is_owner(uid: int) -> bool:
    return uid in OWNER_IDS


async def check_maintenance() -> bool:
    return await db.get_setting("maintenance", "0") == "1"


async def check_banned(user_id: int) -> bool:
    user = await db.get_user(user_id)
    return bool(user and user["is_banned"])


async def get_active_key() -> tuple[str | None, dict | None]:
    if not _session:
        return None, None
    keys = await db.get_all_api_keys()
    active_keys = [k["key_value"] for k in keys if k["is_active"]]
    return await eleven.get_working_key(_session, active_keys)


# ─── /start ──────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(msg: Message) -> None:
    if msg.chat.type != "private" and not is_owner(msg.from_user.id):
        return
    await db.upsert_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    if await check_banned(msg.from_user.id):
        await msg.answer("🚫 You are banned from using this bot.")
        return
    name = html.escape(msg.from_user.first_name or "")
    await msg.answer(
        f"👋 Welcome, <b>{name}</b>!\n\n"
        "🤖 I can convert text to voice and voice to text.\n"
        "• 🔊 Send any text to convert it to speech\n"
        "• 🎤 Send a voice message to transcribe it\n\n"
        "Use the menu below to get started:",
        reply_markup=kb.user_main_kb(),
    )


@router.message(Command("help"))
@router.message(F.text.regexp(r"^[./]help$"))
async def cmd_help(msg: Message) -> None:
    if msg.chat.type != "private" and not is_owner(msg.from_user.id):
        return
    await db.upsert_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    await msg.answer(
        "📖 <b>Bot Commands</b>\n\n"
        "<b>User Commands</b> (work with / or .)\n"
        "/start – Open main menu\n"
        "/voice – Change voice\n"
        "/stats – Your stats\n"
        "/help – This message\n\n"
        "<b>How to use</b>\n"
        "• Send any text → get voice audio\n"
        "• Send a voice message → get transcription\n"
        "• Use <b>🎭 Change Voice</b> to pick your preferred voice\n\n"
        "<b>Owner Quick Commands</b> (in any chat)\n"
        "Reply to a voice with <code>.t</code> → transcribe\n"
        "Reply to text with <code>.a</code> → convert to voice",
        reply_markup=kb.back_to_menu(),
    )


# ─── User panel callbacks ─────────────────────────────────────────────────────

@router.callback_query(F.data == "up:main")
async def cb_user_main(cb: CallbackQuery) -> None:
    await cb.message.edit_text(
        "🤖 <b>Voice Bot</b>\n\nChoose what to do:",
        reply_markup=kb.user_main_kb(),
    )
    await cb.answer()


@router.callback_query(F.data == "up:tts")
async def cb_user_tts_info(cb: CallbackQuery) -> None:
    await cb.message.edit_text(
        "🔊 <b>Text → Voice</b>\n\nJust type or paste any text in the chat and I'll convert it to speech automatically.",
        reply_markup=kb.back_to_menu(),
    )
    await cb.answer()


@router.callback_query(F.data == "up:stt")
async def cb_user_stt_info(cb: CallbackQuery) -> None:
    await cb.message.edit_text(
        "🎤 <b>Voice → Text</b>\n\nSend me any voice message and I'll transcribe it.",
        reply_markup=kb.back_to_menu(),
    )
    await cb.answer()


@router.callback_query(F.data == "up:help")
async def cb_user_help(cb: CallbackQuery) -> None:
    await cb.message.edit_text(
        "📖 <b>How to use</b>\n\n"
        "🔊 <b>Text to Voice</b>\nSend any text in the chat.\n\n"
        "🎤 <b>Voice to Text</b>\nSend a voice message.\n\n"
        "🎭 <b>Change Voice</b>\nChoose from anime, girl, women, men, old, or child voices.\n\n"
        "📊 <b>Stats</b>\nView your usage statistics.",
        reply_markup=kb.back_to_menu(),
    )
    await cb.answer()


@router.callback_query(F.data == "up:stats")
async def cb_user_stats(cb: CallbackQuery) -> None:
    uid  = cb.from_user.id
    user = await db.get_user(uid)
    if not user:
        await cb.answer("No data yet.")
        return
    text = (
        f"📊 <b>Your Stats</b>\n\n"
        f"🔊 TTS conversions: <b>{user['tts_count']}</b>\n"
        f"🎤 STT transcriptions: <b>{user['stt_count']}</b>\n"
        f"🎭 Current voice: <b>{user['voice_name']}</b> ({user['voice_cat']})\n"
        f"📅 Joined: {user['joined_at'][:10]}"
    )
    await cb.message.edit_text(text, reply_markup=kb.back_to_menu())
    await cb.answer()


# ─── Voice selection ─────────────────────────────────────────────────────────

@router.message(Command("voice"))
@router.message(F.text.regexp(r"^[./]voice$"))
async def cmd_voice(msg: Message) -> None:
    if msg.chat.type != "private" and not is_owner(msg.from_user.id):
        return
    await db.upsert_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    await msg.answer(
        "🎭 <b>Voice Selection</b>\n\nChoose a voice category:",
        reply_markup=kb.voice_categories_kb(),
    )


@router.callback_query(F.data == "up:voice")
async def cb_voice_menu(cb: CallbackQuery) -> None:
    await cb.message.edit_text(
        "🎭 <b>Voice Selection</b>\n\nChoose a voice category:",
        reply_markup=kb.voice_categories_kb(),
    )
    await cb.answer()


@router.callback_query(F.data == "vc:cats")
async def cb_voice_cats(cb: CallbackQuery) -> None:
    await cb.message.edit_text(
        "🎭 <b>Voice Categories</b>\n\nChoose a category:",
        reply_markup=kb.voice_categories_kb(),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("vc:cat:"))
async def cb_voice_category(cb: CallbackQuery) -> None:
    cat_key = cb.data.split(":")[2]
    cat     = VOICE_LIBRARY.get(cat_key)
    if not cat:
        await cb.answer("Unknown category.", show_alert=True)
        return
    uid          = cb.from_user.id
    voice_id, _, _ = await db.get_user_voice(uid)
    await cb.message.edit_text(
        f"{cat['label']} <b>Voices</b>\n\nSelect a voice:",
        reply_markup=kb.voice_list_kb(cat_key, voice_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("vc:set:"))
async def cb_voice_set(cb: CallbackQuery) -> None:
    parts   = cb.data.split(":")  # vc:set:cat_key:vi
    cat_key = parts[2]
    vi      = int(parts[3])
    cat     = VOICE_LIBRARY.get(cat_key)
    if not cat or vi >= len(cat["voices"]):
        await cb.answer("Invalid selection.", show_alert=True)
        return
    v = cat["voices"][vi]
    await db.upsert_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await db.set_user_voice(cb.from_user.id, v["id"], cat_key, v["name"])
    await cb.message.edit_text(
        f"✅ <b>Voice Updated!</b>\n\n"
        f"Category: {cat['label']}\n"
        f"Voice: <b>{v['name']}</b>\n"
        f"Style: {v['desc']}\n\n"
        f"Send any text now to try it out!",
        reply_markup=kb.back_to_menu(),
    )
    await cb.answer(f"✅ Voice set to {v['name']}")


# ─── Re-generate last TTS ─────────────────────────────────────────────────────

@router.callback_query(F.data == "up:regen")
async def cb_regen(cb: CallbackQuery) -> None:
    await cb.answer("Send text to regenerate.")
    await cb.message.edit_reply_markup(reply_markup=kb.back_to_menu())


# ─── STT → TTS ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "up:stt2tts")
async def cb_stt2tts(cb: CallbackQuery) -> None:
    """Extract transcribed text from the message and convert to voice."""
    text = cb.message.text or cb.message.caption or ""
    # Extract the actual transcript (after "📝 Transcript:\n\n")
    if "📝" in text and "\n\n" in text:
        transcript = text.split("\n\n", 1)[1].strip()
    else:
        await cb.answer("Could not extract text.", show_alert=True)
        return
    if not transcript:
        await cb.answer("No text to convert.", show_alert=True)
        return

    await cb.answer("Converting to voice…")
    uid          = cb.from_user.id
    voice_id, _, vname = await db.get_user_voice(uid)
    api_key, _   = await get_active_key()
    if not api_key:
        await cb.message.edit_text(
            "❌ No working API key available.",
            reply_markup=kb.back_to_menu(),
        )
        return

    ok, audio, err = await eleven.tts(_session, api_key, voice_id, transcript, DEFAULT_MODEL_ID)
    if not ok:
        logger.error("TTS stt2tts error uid=%s: %s", uid, err)
        await cb.message.edit_text(
            f"❌ TTS failed: <code>{html.escape(err[:200])}</code>",
            reply_markup=kb.back_to_menu(),
        )
        return

    await db.increment_user_stat(uid, "tts_count")
    await db.mark_key_used(api_key, len(transcript))
    await cb.message.answer_audio(
        audio=BufferedInputFile(audio, filename="voice.mp3"),
        caption=f"🎧 <b>{vname}</b>",
        reply_markup=kb.tts_result_kb(vname),
    )


# ─── Text → Voice (main message handler) ─────────────────────────────────────

@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(msg: Message) -> None:
    uid  = msg.from_user.id
    text = msg.text.strip() if msg.text else ""

    # Dot-commands: only owner in groups; users in private
    if text.startswith("."):
        await _handle_dot_command(msg, text)
        return

    # Only private chat for regular users; owners can use anywhere
    if msg.chat.type != "private" and not is_owner(uid):
        return

    if await check_maintenance() and not is_owner(uid):
        await msg.answer("🔧 Bot is under maintenance. Please try again later.")
        return

    if await check_banned(uid):
        await msg.answer("🚫 You are banned from using this bot.")
        return

    if not text:
        return

    await db.upsert_user(uid, msg.from_user.username, msg.from_user.full_name)
    proc = await msg.answer("🎧 Generating audio…")

    api_key, _ = await get_active_key()
    if not api_key:
        await proc.edit_text("❌ No working API key available. Contact the bot owner.")
        await db.write_log("ERROR", f"No working API key for TTS uid={uid}")
        return

    voice_id, _, vname = await db.get_user_voice(uid)
    ok, audio, err = await eleven.tts(_session, api_key, voice_id, text, DEFAULT_MODEL_ID)
    if not ok:
        logger.error("TTS error uid=%s voice=%s: %s", uid, voice_id, err)
        await db.write_log("ERROR", f"TTS failed uid={uid}: {err[:200]}")
        await proc.edit_text(
            f"❌ TTS failed.\n<code>{html.escape(err[:300])}</code>"
        )
        return

    await db.increment_user_stat(uid, "tts_count")
    await db.mark_key_used(api_key, len(text))
    try:
        await proc.delete()
    except Exception:
        pass
    await msg.answer_audio(
        audio=BufferedInputFile(audio, filename="voice.mp3"),
        caption=f"🎧 <b>{vname}</b>",
        reply_markup=kb.tts_result_kb(vname),
    )


# ─── Voice → Text (main voice handler) ───────────────────────────────────────

@router.message(F.voice | F.audio)
async def handle_voice(msg: Message) -> None:
    uid = msg.from_user.id

    # Only private for regular users; owners anywhere
    if msg.chat.type != "private" and not is_owner(uid):
        return

    if await check_maintenance() and not is_owner(uid):
        await msg.answer("🔧 Bot is under maintenance. Please try again later.")
        return

    if await check_banned(uid):
        await msg.answer("🚫 You are banned from using this bot.")
        return

    await db.upsert_user(uid, msg.from_user.username, msg.from_user.full_name)
    proc = await msg.answer("🎤 Transcribing…")

    api_key, _ = await get_active_key()
    if not api_key:
        await proc.edit_text("❌ No working API key available. Contact the bot owner.")
        await db.write_log("ERROR", f"No working API key for STT uid={uid}")
        return

    try:
        file_obj  = msg.voice or msg.audio
        tg_file   = await msg.bot.get_file(file_obj.file_id)
        bio       = BytesIO()
        await msg.bot.download_file(tg_file.file_path, destination=bio)
        audio_bytes = bio.getvalue()

        ok, result = await eleven.stt(_session, api_key, audio_bytes)
        if not ok:
            logger.error("STT error uid=%s: %s", uid, result)
            await db.write_log("ERROR", f"STT failed uid={uid}: {result[:200]}")
            await proc.edit_text(
                f"❌ Transcription failed.\n<code>{html.escape(result[:300])}</code>"
            )
            return

        await db.increment_user_stat(uid, "stt_count")
        await proc.edit_text(
            f"📝 <b>Transcript:</b>\n\n{html.escape(result)}",
            reply_markup=kb.stt_result_kb(),
        )
    except Exception as exc:
        logger.exception("Unexpected STT error uid=%s", uid)
        await db.write_log("ERROR", f"STT unexpected uid={uid}: {exc}")
        await proc.edit_text(f"❌ Unexpected error: <code>{html.escape(str(exc)[:200])}</code>")


# ─── Dot-command dispatcher ───────────────────────────────────────────────────

async def _handle_dot_command(msg: Message, text: str) -> None:
    """
    .t – owner replies to a voice/audio message to transcribe it
    .a – owner replies to a text message to convert to voice
    Other .commands handled elsewhere.
    """
    uid = msg.from_user.id
    cmd = text.lstrip(".").strip().lower()

    if cmd == "t" and is_owner(uid):
        # Transcribe replied voice
        replied = msg.reply_to_message
        if not replied or (not replied.voice and not replied.audio):
            await msg.reply("⚠️ Reply to a voice or audio message with .t")
            return
        proc = await msg.reply("🎤 Transcribing…")
        api_key, _ = await get_active_key()
        if not api_key:
            await proc.edit_text("❌ No working API key.")
            return
        try:
            file_obj  = replied.voice or replied.audio
            tg_file   = await msg.bot.get_file(file_obj.file_id)
            bio       = BytesIO()
            await msg.bot.download_file(tg_file.file_path, destination=bio)
            ok, result = await eleven.stt(_session, api_key, bio.getvalue())
            if ok:
                await proc.edit_text(f"📝 <b>Transcript:</b>\n\n{html.escape(result)}")
            else:
                await proc.edit_text(f"❌ STT failed: <code>{html.escape(result[:200])}</code>")
        except Exception as exc:
            await proc.edit_text(f"❌ Error: <code>{html.escape(str(exc)[:200])}</code>")
        return

    if cmd == "a" and is_owner(uid):
        # Convert replied text to voice
        replied = msg.reply_to_message
        if not replied or not replied.text:
            await msg.reply("⚠️ Reply to a text message with .a")
            return
        input_text = replied.text.strip()
        proc = await msg.reply("🎧 Generating audio…")
        api_key, _ = await get_active_key()
        if not api_key:
            await proc.edit_text("❌ No working API key.")
            return
        voice_id, _, vname = await db.get_user_voice(uid)
        ok, audio, err = await eleven.tts(_session, api_key, voice_id, input_text, DEFAULT_MODEL_ID)
        if ok and audio:
            try:
                await proc.delete()
            except Exception:
                pass
            await replied.reply_audio(
                audio=BufferedInputFile(audio, filename="voice.mp3"),
                caption=f"🎧 <b>{vname}</b>",
            )
        else:
            await proc.edit_text(f"❌ TTS failed: <code>{html.escape(err[:200])}</code>")
        return

    # Ignore other dot-commands silently unless in private
    if msg.chat.type == "private":
        pass  # let other handlers / FSM catch it
