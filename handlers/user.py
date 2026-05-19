"""
User-facing handlers: /start, TTS, STT, voice selection, inline query.
- Private chat: all users can use TTS and STT.
- Groups / channels: only the owner can use TTS and STT.
- Inline mode (@botname text): owner-only, converts text to voice in any chat.
"""
from __future__ import annotations

import html
import logging
import time
import uuid as _uuid
from io import BytesIO

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedAudio,
    InputTextMessageContent,
    Message,
)

import api as eleven
import db
import keyboards as kb
from config import DEFAULT_MODEL_ID, OWNER_IDS, VOICE_LIBRARY

logger  = logging.getLogger("bot.user")
router  = Router()

_session = None

# Simple in-memory TTS cache for inline queries: text → (file_id, timestamp)
_inline_cache: dict[str, tuple[str, float]] = {}
_INLINE_CACHE_TTL = 600  # 10 minutes


def set_session(session) -> None:
    global _session
    _session = session


# ─── FSM States ───────────────────────────────────────────────────────────────

class UserState(StatesGroup):
    last_tts_text = State()


# ─── Guards ───────────────────────────────────────────────────────────────────

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


# ─── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(msg: Message) -> None:
    if msg.chat.type != "private" and not is_owner(msg.from_user.id):
        return
    await db.upsert_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    if await check_banned(msg.from_user.id):
        await msg.answer("Access Denied\n\nYour account has been restricted from using this service.")
        return
    name = html.escape(msg.from_user.first_name or "")
    await msg.answer(
        f"Welcome, <b>{name}</b>.\n\n"
        "<b>Voice Studio</b> converts text to speech and speech to text using "
        "ElevenLabs — one of the most advanced voice synthesis engines available.\n\n"
        "▸ Send any text to receive a voice audio file\n"
        "▸ Send a voice message to receive a transcript\n\n"
        "Select an option below to get started:",
        reply_markup=kb.user_main_kb(),
    )


@router.message(Command("help"))
@router.message(F.text.regexp(r"^[./]help$"))
async def cmd_help(msg: Message) -> None:
    if msg.chat.type != "private" and not is_owner(msg.from_user.id):
        return
    await db.upsert_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    await msg.answer(
        "<b>Help &amp; Guide</b>\n\n"
        "<b>Text to Voice</b>\n"
        "Send any text in the chat and the bot will reply with an audio file.\n\n"
        "<b>Voice to Text</b>\n"
        "Send a voice message and the bot will return a full transcript.\n\n"
        "<b>Change Voice</b>\n"
        "Browse 25+ voices across Anime, Girl, Women, Men, Elder, and Child categories.\n\n"
        "<b>Owner Quick Commands</b> <i>(works in any chat)</i>\n"
        "Reply to a voice message with <code>.t</code> — transcribe it\n"
        "Reply to a text message with <code>.a</code> — convert it to voice\n"
        "Use <code>@botname your text</code> — inline TTS in any group",
        reply_markup=kb.back_to_menu(),
    )


# ─── User panel callbacks ──────────────────────────────────────────────────────

@router.callback_query(F.data == "up:main")
async def cb_user_main(cb: CallbackQuery) -> None:
    await cb.message.edit_text(
        "<b>Voice Studio</b>\n\nSelect an option:",
        reply_markup=kb.user_main_kb(),
    )
    await cb.answer()


@router.callback_query(F.data == "up:tts")
async def cb_user_tts_info(cb: CallbackQuery) -> None:
    await cb.message.edit_text(
        "<b>Text to Voice</b>\n\n"
        "Type or paste any text in the chat and the bot will convert it to speech automatically.\n\n"
        "▸ Supports all languages\n"
        "▸ Powered by ElevenLabs Multilingual v2",
        reply_markup=kb.back_to_menu(),
    )
    await cb.answer()


@router.callback_query(F.data == "up:stt")
async def cb_user_stt_info(cb: CallbackQuery) -> None:
    await cb.message.edit_text(
        "<b>Voice to Text</b>\n\n"
        "Send any voice message and the bot will transcribe it into text.\n\n"
        "▸ Supports multiple languages\n"
        "▸ Powered by ElevenLabs Scribe v1",
        reply_markup=kb.back_to_menu(),
    )
    await cb.answer()


@router.callback_query(F.data == "up:help")
async def cb_user_help(cb: CallbackQuery) -> None:
    await cb.message.edit_text(
        "<b>How to Use</b>\n\n"
        "<b>▸ Text to Voice</b>\n"
        "Send any text in the chat.\n\n"
        "<b>▸ Voice to Text</b>\n"
        "Send a voice message.\n\n"
        "<b>▸ Change Voice</b>\n"
        "Choose from Anime, Girl, Women, Men, Elder, or Child voices.\n\n"
        "<b>▸ Statistics</b>\n"
        "View your total conversions.",
        reply_markup=kb.back_to_menu(),
    )
    await cb.answer()


@router.callback_query(F.data == "up:stats")
async def cb_user_stats(cb: CallbackQuery) -> None:
    uid  = cb.from_user.id
    user = await db.get_user(uid)
    if not user:
        await cb.answer("No usage data yet.", show_alert=True)
        return
    text = (
        "<b>Your Statistics</b>\n\n"
        f"▸ Text to Voice conversions:  <b>{user['tts_count']}</b>\n"
        f"▸ Voice to Text transcriptions:  <b>{user['stt_count']}</b>\n"
        f"▸ Active voice:  <b>{user['voice_name']}</b> ({user['voice_cat']})\n"
        f"▸ Member since:  {user['joined_at'][:10]}"
    )
    await cb.message.edit_text(text, reply_markup=kb.back_to_menu())
    await cb.answer()


# ─── Voice selection ──────────────────────────────────────────────────────────

@router.message(Command("voice"))
@router.message(F.text.regexp(r"^[./]voice$"))
async def cmd_voice(msg: Message) -> None:
    if msg.chat.type != "private" and not is_owner(msg.from_user.id):
        return
    await db.upsert_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    await msg.answer(
        "<b>Voice Selection</b>\n\nChoose a voice category:",
        reply_markup=kb.voice_categories_kb(),
    )


@router.callback_query(F.data == "up:voice")
async def cb_voice_menu(cb: CallbackQuery) -> None:
    await cb.message.edit_text(
        "<b>Voice Selection</b>\n\nChoose a voice category:",
        reply_markup=kb.voice_categories_kb(),
    )
    await cb.answer()


@router.callback_query(F.data == "vc:cats")
async def cb_voice_cats(cb: CallbackQuery) -> None:
    await cb.message.edit_text(
        "<b>Voice Categories</b>\n\nChoose a category:",
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
    uid            = cb.from_user.id
    voice_id, _, _ = await db.get_user_voice(uid)
    await cb.message.edit_text(
        f"{cat['label']}  —  <b>Available Voices</b>\n\nSelect a voice to activate it:",
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
        "<b>Voice Updated</b>\n\n"
        f"▸ Category:  {cat['label']}\n"
        f"▸ Voice:  <b>{v['name']}</b>\n"
        f"▸ Style:  {v['desc']}\n\n"
        "Send any text to try your new voice.",
        reply_markup=kb.back_to_menu(),
    )
    await cb.answer(f"Voice set to {v['name']}")


# ─── Re-generate last TTS ──────────────────────────────────────────────────────

@router.callback_query(F.data == "up:regen")
async def cb_regen(cb: CallbackQuery, state: FSMContext) -> None:
    data      = await state.get_data()
    last_text = data.get("last_tts_text", "")
    if not last_text:
        await cb.answer("No previous text to regenerate. Send a new message.", show_alert=True)
        return

    await cb.answer("Regenerating audio…")
    uid          = cb.from_user.id
    voice_id, _, vname = await db.get_user_voice(uid)
    api_key, _   = await get_active_key()
    if not api_key:
        await cb.message.edit_text(
            "Service Unavailable\n\nNo active API key found. Please contact the bot administrator.",
            reply_markup=kb.back_to_menu(),
        )
        return

    ok, audio, err = await eleven.tts(_session, api_key, voice_id, last_text, DEFAULT_MODEL_ID)
    if not ok:
        logger.error("TTS regen error uid=%s: %s", uid, err)
        await cb.message.edit_text(
            f"<b>Conversion Failed</b>\n\n<code>{html.escape(err[:300])}</code>",
            reply_markup=kb.back_to_menu(),
        )
        return

    await db.increment_user_stat(uid, "tts_count")
    await db.mark_key_used(api_key, len(last_text))
    await cb.message.answer_audio(
        audio=BufferedInputFile(audio, filename="voice.mp3"),
        caption=f"▸ <b>{vname}</b>",
        reply_markup=kb.tts_result_kb(vname),
    )


# ─── STT → TTS ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "up:stt2tts")
async def cb_stt2tts(cb: CallbackQuery) -> None:
    """Extract transcribed text from the STT result message and convert to voice."""
    text = cb.message.text or cb.message.caption or ""

    # Robust extraction: look for the transcript block after the header line
    transcript = ""
    # Handle both possible formats of the transcript message
    for separator in ("\n\n", "\n"):
        if "Transcript" in text and separator in text:
            parts = text.split(separator, 1)
            if len(parts) == 2:
                candidate = parts[1].strip()
                if candidate and not candidate.startswith("<"):
                    transcript = candidate
                    break

    if not transcript:
        await cb.answer("Could not extract transcript text.", show_alert=True)
        return

    await cb.answer("Converting to voice…")
    uid          = cb.from_user.id
    voice_id, _, vname = await db.get_user_voice(uid)
    api_key, _   = await get_active_key()
    if not api_key:
        await cb.message.edit_text(
            "Service Unavailable\n\nNo active API key found.",
            reply_markup=kb.back_to_menu(),
        )
        return

    ok, audio, err = await eleven.tts(_session, api_key, voice_id, transcript, DEFAULT_MODEL_ID)
    if not ok:
        logger.error("TTS stt2tts error uid=%s: %s", uid, err)
        await cb.message.edit_text(
            f"<b>Conversion Failed</b>\n\n<code>{html.escape(err[:200])}</code>",
            reply_markup=kb.back_to_menu(),
        )
        return

    await db.increment_user_stat(uid, "tts_count")
    await db.mark_key_used(api_key, len(transcript))
    await cb.message.answer_audio(
        audio=BufferedInputFile(audio, filename="voice.mp3"),
        caption=f"▸ <b>{vname}</b>",
        reply_markup=kb.tts_result_kb(vname),
    )


# ─── Text → Voice (main message handler) ──────────────────────────────────────

@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(msg: Message, state: FSMContext) -> None:
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
        await msg.answer(
            "<b>Service Temporarily Unavailable</b>\n\n"
            "The system is currently under maintenance. Please try again shortly."
        )
        return

    if await check_banned(uid):
        await msg.answer("Access Denied\n\nYour account has been restricted from using this service.")
        return

    if not text:
        return

    await db.upsert_user(uid, msg.from_user.username, msg.from_user.full_name)
    proc = await msg.answer("Generating audio…")

    api_key, _ = await get_active_key()
    if not api_key:
        await proc.edit_text(
            "<b>Service Unavailable</b>\n\nNo active API key found. Please contact the bot administrator."
        )
        await db.write_log("ERROR", f"No working API key for TTS uid={uid}")
        return

    voice_id, _, vname = await db.get_user_voice(uid)
    ok, audio, err     = await eleven.tts(_session, api_key, voice_id, text, DEFAULT_MODEL_ID)
    if not ok:
        logger.error("TTS error uid=%s voice=%s: %s", uid, voice_id, err)
        await db.write_log("ERROR", f"TTS failed uid={uid}: {err[:200]}")
        await proc.edit_text(
            f"<b>Conversion Failed</b>\n\n<code>{html.escape(err[:300])}</code>"
        )
        return

    await db.increment_user_stat(uid, "tts_count")
    await db.mark_key_used(api_key, len(text))
    # Store for regeneration
    await state.update_data(last_tts_text=text)
    try:
        await proc.delete()
    except Exception:
        pass
    await msg.answer_audio(
        audio=BufferedInputFile(audio, filename="voice.mp3"),
        caption=f"▸ <b>{vname}</b>",
        reply_markup=kb.tts_result_kb(vname),
    )


# ─── Voice → Text (main voice handler) ────────────────────────────────────────

@router.message(F.voice | F.audio)
async def handle_voice(msg: Message) -> None:
    uid = msg.from_user.id

    if msg.chat.type != "private" and not is_owner(uid):
        return

    if await check_maintenance() and not is_owner(uid):
        await msg.answer(
            "<b>Service Temporarily Unavailable</b>\n\n"
            "The system is currently under maintenance. Please try again shortly."
        )
        return

    if await check_banned(uid):
        await msg.answer("Access Denied\n\nYour account has been restricted from using this service.")
        return

    await db.upsert_user(uid, msg.from_user.username, msg.from_user.full_name)
    proc = await msg.answer("Transcribing audio…")

    api_key, _ = await get_active_key()
    if not api_key:
        await proc.edit_text(
            "<b>Service Unavailable</b>\n\nNo active API key found. Please contact the bot administrator."
        )
        await db.write_log("ERROR", f"No working API key for STT uid={uid}")
        return

    try:
        file_obj    = msg.voice or msg.audio
        tg_file     = await msg.bot.get_file(file_obj.file_id)
        bio         = BytesIO()
        await msg.bot.download_file(tg_file.file_path, destination=bio)
        audio_bytes = bio.getvalue()

        ok, result = await eleven.stt(_session, api_key, audio_bytes)
        if not ok:
            logger.error("STT error uid=%s: %s", uid, result)
            await db.write_log("ERROR", f"STT failed uid={uid}: {result[:200]}")
            await proc.edit_text(
                f"<b>Transcription Failed</b>\n\n<code>{html.escape(result[:300])}</code>"
            )
            return

        await db.increment_user_stat(uid, "stt_count")
        await proc.edit_text(
            f"<b>Transcript</b>\n\n{html.escape(result)}",
            reply_markup=kb.stt_result_kb(),
        )
    except Exception as exc:
        logger.exception("Unexpected STT error uid=%s", uid)
        await db.write_log("ERROR", f"STT unexpected uid={uid}: {exc}")
        await proc.edit_text(
            f"<b>Unexpected Error</b>\n\n<code>{html.escape(str(exc)[:200])}</code>"
        )


# ─── Inline query — Owner-only TTS in any chat ────────────────────────────────

@router.inline_query()
async def handle_inline_query(query: InlineQuery) -> None:
    """
    Allows the owner to type @botname <text> in any chat to convert text to voice.
    Non-owners receive a prompt to open the bot privately instead.
    """
    uid  = query.from_user.id
    text = query.query.strip()

    if not is_owner(uid):
        # Non-owners: show a redirect prompt, do not process
        await query.answer(
            results=[
                InlineQueryResultArticle(
                    id="access_denied",
                    title="Owner-Exclusive Feature",
                    description="This inline mode is restricted to the bot owner.",
                    input_message_content=InputTextMessageContent(
                        message_text="Voice Studio inline mode is restricted to the bot owner."
                    ),
                )
            ],
            cache_time=300,
            is_personal=True,
        )
        return

    if not text:
        # Show usage hint
        await query.answer(
            results=[
                InlineQueryResultArticle(
                    id="usage_hint",
                    title="Text to Voice — Inline Mode",
                    description="Type any text after @botname to convert it to speech",
                    input_message_content=InputTextMessageContent(
                        message_text="<b>Voice Studio</b>\n\nType text after @botname to convert it to a voice message.",
                        parse_mode="HTML",
                    ),
                )
            ],
            cache_time=10,
            is_personal=True,
        )
        return

    # --- Inline TTS ---

    # Prune expired cache entries
    now = time.time()
    expired_keys = [k for k, (_, ts) in _inline_cache.items() if now - ts > _INLINE_CACHE_TTL]
    for k in expired_keys:
        del _inline_cache[k]

    # Return cached result if available
    cache_key = text[:200]
    if cache_key in _inline_cache:
        file_id, _ = _inline_cache[cache_key]
        await query.answer(
            results=[InlineQueryResultCachedAudio(id=str(_uuid.uuid4()), audio_file_id=file_id)],
            cache_time=120,
            is_personal=True,
        )
        return

    # Generate TTS
    if await check_maintenance():
        await query.answer(results=[], cache_time=5, is_personal=True)
        return

    api_key, _ = await get_active_key()
    if not api_key:
        logger.error("Inline TTS: no active API key for owner uid=%s", uid)
        await query.answer(results=[], cache_time=5, is_personal=True)
        return

    voice_id, _, vname = await db.get_user_voice(uid)
    ok, audio, err     = await eleven.tts(_session, api_key, voice_id, text[:500], DEFAULT_MODEL_ID)
    if not ok:
        logger.error("Inline TTS error uid=%s: %s", uid, err)
        await query.answer(results=[], cache_time=5, is_personal=True)
        return

    # Upload to owner's private chat to obtain a Telegram file_id,
    # then delete the message immediately.
    try:
        sent = await query.bot.send_audio(
            chat_id=uid,
            audio=BufferedInputFile(audio, filename="voice.mp3"),
            title=f"Voice — {vname}",
            disable_notification=True,
        )
        file_id = sent.audio.file_id
        try:
            await query.bot.delete_message(uid, sent.message_id)
        except Exception:
            pass

        _inline_cache[cache_key] = (file_id, now)

        await db.increment_user_stat(uid, "tts_count")
        await db.mark_key_used(api_key, len(text))

        await query.answer(
            results=[InlineQueryResultCachedAudio(id=str(_uuid.uuid4()), audio_file_id=file_id)],
            cache_time=120,
            is_personal=True,
        )
    except Exception as exc:
        logger.exception("Inline TTS upload error uid=%s: %s", uid, exc)
        await query.answer(results=[], cache_time=5, is_personal=True)


# ─── Dot-command dispatcher ────────────────────────────────────────────────────

async def _handle_dot_command(msg: Message, text: str) -> None:
    """
    .t — Owner replies to a voice/audio message to transcribe it (any chat)
    .a — Owner replies to a text message to convert it to voice (any chat)
    """
    uid = msg.from_user.id
    cmd = text.lstrip(".").strip().lower()

    if cmd == "t" and is_owner(uid):
        replied = msg.reply_to_message
        if not replied or (not replied.voice and not replied.audio):
            await msg.reply("Reply to a voice or audio message with .t to transcribe it.")
            return
        proc = await msg.reply("Transcribing…")
        api_key, _ = await get_active_key()
        if not api_key:
            await proc.edit_text("Service Unavailable\n\nNo active API key found.")
            return
        try:
            file_obj  = replied.voice or replied.audio
            tg_file   = await msg.bot.get_file(file_obj.file_id)
            bio       = BytesIO()
            await msg.bot.download_file(tg_file.file_path, destination=bio)
            ok, result = await eleven.stt(_session, api_key, bio.getvalue())
            if ok:
                await proc.edit_text(f"<b>Transcript</b>\n\n{html.escape(result)}")
            else:
                await proc.edit_text(
                    f"<b>Transcription Failed</b>\n\n<code>{html.escape(result[:200])}</code>"
                )
        except Exception as exc:
            await proc.edit_text(
                f"<b>Error</b>\n\n<code>{html.escape(str(exc)[:200])}</code>"
            )
        return

    if cmd == "a" and is_owner(uid):
        replied = msg.reply_to_message
        if not replied or not replied.text:
            await msg.reply("Reply to a text message with .a to convert it to voice.")
            return
        input_text = replied.text.strip()
        proc       = await msg.reply("Generating audio…")
        api_key, _ = await get_active_key()
        if not api_key:
            await proc.edit_text("Service Unavailable\n\nNo active API key found.")
            return
        voice_id, _, vname = await db.get_user_voice(uid)
        ok, audio, err     = await eleven.tts(_session, api_key, voice_id, input_text, DEFAULT_MODEL_ID)
        if ok and audio:
            try:
                await proc.delete()
            except Exception:
                pass
            await replied.reply_audio(
                audio=BufferedInputFile(audio, filename="voice.mp3"),
                caption=f"▸ <b>{vname}</b>",
            )
        else:
            await proc.edit_text(
                f"<b>Conversion Failed</b>\n\n<code>{html.escape(err[:200])}</code>"
            )
        return

    # Silently ignore unknown dot-commands in non-private chats
    if msg.chat.type == "private":
        pass  # let other handlers / FSM catch it
