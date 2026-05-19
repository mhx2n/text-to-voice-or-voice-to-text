"""
Admin / Owner message handlers.
Commands work with both / and . prefix.
"""
from __future__ import annotations

import asyncio
import html
import logging
import platform
import time
from io import BytesIO

import psutil
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

import api as eleven
import db
import keyboards as kb
from config import OWNER_IDS, VOICE_LIBRARY

logger  = logging.getLogger("bot.admin")
router  = Router()

# ─── Session proxy (set from main) ───────────────────────────────────────────
_session = None

def set_session(session) -> None:
    global _session
    _session = session


# ─── FSM States ──────────────────────────────────────────────────────────────

class AddKeyState(StatesGroup):
    waiting_key = State()

class BroadcastState(StatesGroup):
    waiting_msg = State()
    confirm     = State()

# ─── Guards ──────────────────────────────────────────────────────────────────

def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS


async def owner_only(msg_or_cb, state: FSMContext | None = None) -> bool:
    uid = (msg_or_cb.from_user or msg_or_cb.message.from_user).id
    if is_owner(uid):
        return True
    if isinstance(msg_or_cb, CallbackQuery):
        await msg_or_cb.answer("⛔ Owner only.", show_alert=True)
    else:
        await msg_or_cb.answer("⛔ Owner only.")
    return False


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _mask(k: str) -> str:
    return f"{k[:6]}...{k[-4:]}" if len(k) > 12 else k[:4] + "****"


def _fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except Exception:
        return "0"


async def _build_stats_text() -> str:
    keys    = await db.get_all_api_keys()
    _, total_users = await db.get_all_users(0, 1)
    mem     = psutil.virtual_memory()
    cpu     = psutil.cpu_percent(interval=0.1)
    up      = time.time() - psutil.boot_time()
    up_h    = int(up // 3600)
    up_m    = int((up % 3600) // 60)

    valid = invalid = active_keys = 0
    total_chars = 0
    for k in keys:
        if not k["is_active"]:
            invalid += 1
            continue
        sub = await eleven.get_subscription(_session, k["key_value"]) if _session else None
        if not sub:
            invalid += 1
        else:
            valid += 1
            used, limit = eleven.parse_quota(sub)
            total_chars += limit - used
            if eleven.has_quota(sub):
                active_keys += 1

    return (
        "📊 <b>Bot Statistics</b>\n\n"
        f"👥 <b>Total Users:</b> {_fmt(total_users)}\n"
        f"🔑 <b>API Keys:</b> {len(keys)} total  |  "
        f"{valid} valid  |  {invalid} invalid  |  {active_keys} active\n"
        f"📝 <b>Remaining Chars:</b> {_fmt(total_chars)}\n\n"
        f"🖥 <b>CPU:</b> {cpu:.1f}%\n"
        f"💾 <b>RAM:</b> {mem.used // 1024 // 1024} MB / {mem.total // 1024 // 1024} MB "
        f"({mem.percent:.1f}%)\n"
        f"⏱ <b>Uptime:</b> {up_h}h {up_m}m\n"
        f"🐍 <b>Python:</b> {platform.python_version()}"
    )


# ─── /owner  .owner  /panel  .panel ──────────────────────────────────────────

@router.message(Command(commands=["owner", "panel"]))
async def cmd_owner_panel(msg: Message) -> None:
    if not await owner_only(msg):
        return
    await db.upsert_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    await msg.answer(
        "🏠 <b>Owner Panel</b>\n\nSelect an action:",
        reply_markup=kb.owner_main(),
    )


@router.message(F.text.regexp(r"^[./]panel$|^[./]owner$"))
async def cmd_dot_owner(msg: Message) -> None:
    await cmd_owner_panel(msg)


# ─── Owner callbacks ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "op:main")
async def cb_owner_main(cb: CallbackQuery) -> None:
    if not await owner_only(cb):
        return
    await cb.message.edit_text("🏠 <b>Owner Panel</b>\n\nSelect an action:", reply_markup=kb.owner_main())
    await cb.answer()


@router.callback_query(F.data == "op:stats")
async def cb_stats(cb: CallbackQuery) -> None:
    if not await owner_only(cb):
        return
    await cb.answer("Loading stats…")
    text = await _build_stats_text()
    await cb.message.edit_text(text, reply_markup=kb.owner_stats_kb())


@router.callback_query(F.data == "op:voices")
async def cb_voice_preview(cb: CallbackQuery) -> None:
    if not await owner_only(cb):
        return
    lines = ["🎭 <b>Voice Library</b>\n"]
    for cat_key, cat in VOICE_LIBRARY.items():
        lines.append(f"\n<b>{cat['label']}</b>")
        for v in cat["voices"]:
            lines.append(f"  • {v['name']} – {v['desc']} │ <code>{v['id']}</code>")
    await cb.message.edit_text(
        "\n".join(lines), reply_markup=kb.back_to_menu()
    )
    await cb.answer()


# ─── API Keys ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "op:apikeys")
async def cb_apikeys(cb: CallbackQuery, state: FSMContext) -> None:
    if not await owner_only(cb):
        return
    await state.clear()
    keys = await db.get_all_api_keys()
    txt  = f"🔑 <b>API Keys</b>  ({len(keys)} saved)"
    await cb.message.edit_text(txt, reply_markup=kb.apikeys_menu(keys))
    await cb.answer()


@router.callback_query(F.data.startswith("ak:info:"))
async def cb_key_info(cb: CallbackQuery) -> None:
    if not await owner_only(cb):
        return
    key_id = int(cb.data.split(":")[2])
    keys   = await db.get_all_api_keys()
    k      = next((x for x in keys if x["id"] == key_id), None)
    if not k:
        await cb.answer("Key not found.", show_alert=True)
        return
    sub = await eleven.get_subscription(_session, k["key_value"]) if _session else None
    if sub:
        used, limit = eleven.parse_quota(sub)
        pct  = f"{used / limit * 100:.1f}%" if limit else "N/A"
        info = (
            f"✅ Valid\n"
            f"Used: <b>{_fmt(used)}</b> / <b>{_fmt(limit)}</b> chars\n"
            f"Usage: <b>{pct}</b>"
        )
    else:
        info = "❌ Invalid or unreachable"

    text = (
        f"🔑 <b>Key #{key_id}</b>\n"
        f"<code>{_mask(k['key_value'])}</code>\n\n"
        f"{info}\n\n"
        f"Added: {k['added_at']}\n"
        f"Last used: {k['last_used'] or 'Never'}"
    )
    await cb.message.edit_text(text, reply_markup=kb.apikeys_menu(keys))
    await cb.answer()


@router.callback_query(F.data == "ak:add")
async def cb_key_add_start(cb: CallbackQuery, state: FSMContext) -> None:
    if not await owner_only(cb):
        return
    await state.set_state(AddKeyState.waiting_key)
    await cb.message.edit_text(
        "🔑 <b>Add API Key</b>\n\nSend the ElevenLabs API key now:\n"
        "<i>(starts with <code>sk_</code>)</i>",
        reply_markup=kb.cancel_kb("op:apikeys"),
    )
    await cb.answer()


@router.message(AddKeyState.waiting_key)
async def receive_api_key(msg: Message, state: FSMContext) -> None:
    if not is_owner(msg.from_user.id):
        return
    await state.clear()
    key = msg.text.strip() if msg.text else ""
    if not key:
        await msg.answer("❌ Empty input. Cancelled.", reply_markup=kb.owner_main())
        return
    ok = await db.add_api_key(key)
    keys = await db.get_all_api_keys()
    if ok:
        await msg.answer(
            f"✅ API key added: <code>{_mask(key)}</code>",
            reply_markup=kb.apikeys_menu(keys),
        )
        await db.write_log("INFO", f"Owner added API key {_mask(key)}")
    else:
        await msg.answer(
            "⚠️ Key already exists.", reply_markup=kb.apikeys_menu(keys)
        )


@router.callback_query(F.data.startswith("ak:del:"))
async def cb_key_del_confirm(cb: CallbackQuery) -> None:
    if not await owner_only(cb):
        return
    key_id = int(cb.data.split(":")[2])
    await cb.message.edit_text(
        "⚠️ <b>Are you sure?</b>\n\nThis will permanently remove the API key.",
        reply_markup=kb.apikey_confirm_delete(key_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("ak:delok:"))
async def cb_key_del_ok(cb: CallbackQuery) -> None:
    if not await owner_only(cb):
        return
    key_id = int(cb.data.split(":")[2])
    await db.remove_api_key(key_id)
    await db.write_log("INFO", f"Owner removed API key id={key_id}")
    keys = await db.get_all_api_keys()
    await cb.message.edit_text(
        f"🗑 Key #{key_id} removed.\n\n🔑 <b>API Keys</b>  ({len(keys)} saved)",
        reply_markup=kb.apikeys_menu(keys),
    )
    await cb.answer("Removed.")


@router.callback_query(F.data.startswith("ak:tog:"))
async def cb_key_toggle(cb: CallbackQuery) -> None:
    if not await owner_only(cb):
        return
    key_id    = int(cb.data.split(":")[2])
    new_state = await db.toggle_api_key(key_id)
    state_str = "enabled" if new_state else "disabled"
    await cb.answer(f"Key {state_str}.")
    keys = await db.get_all_api_keys()
    await cb.message.edit_reply_markup(reply_markup=kb.apikeys_menu(keys))


# ─── Logs ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "op:logs")
async def cb_logs_menu(cb: CallbackQuery) -> None:
    if not await owner_only(cb):
        return
    await cb.message.edit_text(
        "📋 <b>Bot Logs</b>\n\nChoose log level and time range:",
        reply_markup=kb.logs_kb(10),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("lg:"))
async def cb_logs_view(cb: CallbackQuery) -> None:
    if not await owner_only(cb):
        return
    _, level_key, mins = cb.data.split(":")
    minutes = int(mins)
    level   = "ERROR" if level_key == "err" else None
    logs    = await db.get_recent_logs(minutes=minutes, level=level, limit=50)

    if not logs:
        text = f"📋 <b>Logs – last {minutes} min</b>\n\n<i>No entries found.</i>"
    else:
        lvl_label = level or "ALL"
        lines     = [f"📋 <b>Logs – last {minutes} min ({lvl_label})</b>  [{len(logs)} entries]\n"]
        for log in logs[:30]:
            ts   = log["created_at"][11:19]
            lvl  = log["level"][:4]
            icon = {"ERRO": "🔴", "WARN": "🟡", "INFO": "🔵", "DEBU": "⚪"}.get(lvl, "•")
            msg  = html.escape(log["message"][:120])
            lines.append(f"{icon} <code>{ts}</code> [{lvl}] {msg}")
        if len(logs) > 30:
            lines.append(f"\n<i>… {len(logs) - 30} more entries truncated.</i>")
        text = "\n".join(lines)

    await cb.message.edit_text(text, reply_markup=kb.logs_kb(minutes))
    await cb.answer("Refreshed.")


# ─── Users ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("op:users:"))
async def cb_users_list(cb: CallbackQuery) -> None:
    if not await owner_only(cb):
        return
    page    = int(cb.data.split(":")[2])
    per_pg  = 8
    users, total = await db.get_all_users(page, per_pg)

    lines = [f"👥 <b>Users</b>  (Total: {total})\n"]
    for u in users:
        ban   = " 🚫" if u["is_banned"] else ""
        uname = f"@{u['username']}" if u["username"] else f"ID:{u['user_id']}"
        name  = html.escape(u["full_name"] or "")
        lines.append(
            f"• {uname} {html.escape(name)}{ban}\n"
            f"  TTS: {u['tts_count']}  STT: {u['stt_count']}  "
            f"Voice: {u['voice_name']}\n"
            f"  <code>/userbio {u['user_id']}</code>"
        )

    await cb.message.edit_text(
        "\n".join(lines) or "No users yet.",
        reply_markup=kb.users_list_kb(page, total, per_pg),
    )
    await cb.answer()


@router.message(Command("userbio"))
async def cmd_userbio(msg: Message) -> None:
    if not is_owner(msg.from_user.id):
        return
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.answer("Usage: /userbio USER_ID")
        return
    try:
        uid = int(parts[1])
    except ValueError:
        await msg.answer("Invalid user ID.")
        return
    user = await db.get_user(uid)
    if not user:
        await msg.answer("User not found.")
        return
    is_banned = bool(user["is_banned"])
    text = (
        f"👤 <b>User Profile</b>\n\n"
        f"ID: <code>{user['user_id']}</code>\n"
        f"Username: @{user['username'] or 'N/A'}\n"
        f"Name: {html.escape(user['full_name'] or '')}\n"
        f"Status: {'🚫 Banned' if is_banned else '✅ Active'}\n"
        f"Voice: {user['voice_name']} ({user['voice_cat']})\n"
        f"TTS used: {user['tts_count']}\n"
        f"STT used: {user['stt_count']}\n"
        f"Joined: {user['joined_at']}\n"
        f"Last seen: {user['last_seen']}"
    )
    await msg.answer(text, reply_markup=kb.user_action_kb(uid, is_banned))


@router.callback_query(F.data.startswith("bn:"))
async def cb_ban_user(cb: CallbackQuery) -> None:
    if not await owner_only(cb):
        return
    uid = int(cb.data.split(":")[1])
    await db.ban_user(uid, True)
    await cb.answer("User banned.", show_alert=True)
    user = await db.get_user(uid)
    if user:
        await cb.message.edit_reply_markup(reply_markup=kb.user_action_kb(uid, True))


@router.callback_query(F.data.startswith("ub:"))
async def cb_unban_user(cb: CallbackQuery) -> None:
    if not await owner_only(cb):
        return
    uid = int(cb.data.split(":")[1])
    await db.ban_user(uid, False)
    await cb.answer("User unbanned.", show_alert=True)
    user = await db.get_user(uid)
    if user:
        await cb.message.edit_reply_markup(reply_markup=kb.user_action_kb(uid, False))


# ─── Broadcast ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "op:broadcast")
async def cb_broadcast_start(cb: CallbackQuery, state: FSMContext) -> None:
    if not await owner_only(cb):
        return
    await state.set_state(BroadcastState.waiting_msg)
    await cb.message.edit_text(
        "📢 <b>Broadcast</b>\n\n"
        "Send or forward the message you want to broadcast to all users.\n"
        "Supports: text, photo, video, audio, document, sticker.\n\n"
        "<i>You can also forward any message directly to the bot.</i>",
        reply_markup=kb.cancel_kb("op:main"),
    )
    await cb.answer()


@router.message(BroadcastState.waiting_msg)
async def receive_broadcast_msg(msg: Message, state: FSMContext) -> None:
    if not is_owner(msg.from_user.id):
        return
    await state.update_data(broadcast_msg_id=msg.message_id, broadcast_chat_id=msg.chat.id)
    await state.set_state(BroadcastState.confirm)

    preview = "<i>(media message)</i>"
    if msg.text:
        preview = html.escape(msg.text[:300])
    elif msg.caption:
        preview = html.escape(msg.caption[:300])

    users, total = await db.get_all_users(0, 1)
    await msg.answer(
        f"📢 <b>Broadcast Preview</b>\n\n{preview}\n\n"
        f"📬 Will be sent to <b>{total}</b> users.\n\nConfirm?",
        reply_markup=kb.broadcast_confirm_kb(),
    )


@router.callback_query(F.data == "bc:confirm")
async def cb_broadcast_confirm(cb: CallbackQuery, state: FSMContext) -> None:
    if not await owner_only(cb):
        return
    data = await state.get_data()
    await state.clear()

    src_msg_id   = data.get("broadcast_msg_id")
    src_chat_id  = data.get("broadcast_chat_id")
    if not src_msg_id or not src_chat_id:
        await cb.answer("Session expired. Please try again.", show_alert=True)
        return

    from config import BROADCAST_DELAY
    user_ids = await db.get_all_user_ids()
    sent = fail = 0
    prog_msg = await cb.message.edit_text(
        f"📢 Broadcasting… 0 / {len(user_ids)}", reply_markup=None
    )

    bot = cb.bot
    for i, uid in enumerate(user_ids, 1):
        try:
            await bot.copy_message(
                chat_id=uid,
                from_chat_id=src_chat_id,
                message_id=src_msg_id,
            )
            sent += 1
        except Exception:
            fail += 1
        if i % 25 == 0:
            try:
                await prog_msg.edit_text(f"📢 Broadcasting… {i} / {len(user_ids)}")
            except Exception:
                pass
        await asyncio.sleep(BROADCAST_DELAY)

    await db.save_broadcast(cb.from_user.id, "", "copy", sent, fail)
    await prog_msg.edit_text(
        f"✅ <b>Broadcast Complete</b>\n\n"
        f"✉️ Sent: <b>{sent}</b>\n❌ Failed: <b>{fail}</b>",
        reply_markup=kb.broadcast_done_kb(),
    )
    await cb.answer()


@router.callback_query(F.data == "bc:cancel")
async def cb_broadcast_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    if not await owner_only(cb):
        return
    await state.clear()
    await cb.message.edit_text("📢 Broadcast cancelled.", reply_markup=kb.owner_main())
    await cb.answer()


# ─── Settings ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "op:settings")
async def cb_settings(cb: CallbackQuery) -> None:
    if not await owner_only(cb):
        return
    maintenance = await db.get_setting("maintenance", "0") == "1"
    await cb.message.edit_text(
        "⚙️ <b>Bot Settings</b>", reply_markup=kb.settings_kb(maintenance)
    )
    await cb.answer()


@router.callback_query(F.data == "st:toggle_maintenance")
async def cb_toggle_maintenance(cb: CallbackQuery) -> None:
    if not await owner_only(cb):
        return
    current = await db.get_setting("maintenance", "0") == "1"
    await db.set_setting("maintenance", "0" if current else "1")
    maintenance = not current
    await cb.message.edit_reply_markup(reply_markup=kb.settings_kb(maintenance))
    await cb.answer(f"Maintenance {'ON' if maintenance else 'OFF'}")


# ─── Noop (pagination label buttons) ─────────────────────────────────────────

@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery) -> None:
    await cb.answer()
