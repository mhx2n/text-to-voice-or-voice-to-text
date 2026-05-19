"""
All InlineKeyboardMarkup builders for the bot.
Callback-data format: prefix:arg1[:arg2] — always ≤ 64 bytes.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import VOICE_LIBRARY


# ─── helpers ─────────────────────────────────────────────────────────────────

def _kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for row in rows:
        builder.row(*row)
    return builder.as_markup()


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


# ─── Owner Panel ─────────────────────────────────────────────────────────────

def owner_main() -> InlineKeyboardMarkup:
    return _kb(
        [_btn("📊 Stats", "op:stats"), _btn("🔑 API Keys", "op:apikeys")],
        [_btn("👥 Users", "op:users:0"), _btn("📋 Logs", "op:logs")],
        [_btn("📢 Broadcast", "op:broadcast"), _btn("🎭 Voice Preview", "op:voices")],
        [_btn("⚙️ Bot Settings", "op:settings")],
    )


def owner_stats_kb() -> InlineKeyboardMarkup:
    return _kb([_btn("🔄 Refresh", "op:stats"), _btn("🔙 Back", "op:main")])


# ─── API Keys ────────────────────────────────────────────────────────────────

def apikeys_menu(keys: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for k in keys:
        status = "✅" if k["is_active"] else "🔴"
        label  = k["label"] or _mask(k["key_value"])
        builder.row(
            _btn(f"{status} {label}", f"ak:info:{k['id']}"),
            _btn("🗑 Remove",          f"ak:del:{k['id']}"),
            _btn("⏸/▶",               f"ak:tog:{k['id']}"),
        )
    builder.row(_btn("➕ Add Key", "ak:add"), _btn("🔄 Refresh", "op:apikeys"))
    builder.row(_btn("🔙 Back", "op:main"))
    return builder.as_markup()


def apikey_confirm_delete(key_id: int) -> InlineKeyboardMarkup:
    return _kb(
        [_btn("✅ Yes, remove it", f"ak:delok:{key_id}"), _btn("❌ Cancel", "op:apikeys")],
    )


# ─── Logs ────────────────────────────────────────────────────────────────────

def logs_kb(minutes: int = 10) -> InlineKeyboardMarkup:
    return _kb(
        [_btn("⚠️ Errors only", f"lg:err:{minutes}"), _btn("📋 All levels", f"lg:all:{minutes}")],
        [_btn("⏱ Last 5 min",  "lg:all:5"),  _btn("⏱ Last 30 min", "lg:all:30")],
        [_btn("🔄 Refresh",     f"lg:all:{minutes}"), _btn("🔙 Back", "op:main")],
    )


# ─── Users ───────────────────────────────────────────────────────────────────

def users_list_kb(page: int, total: int, per_page: int = 8) -> InlineKeyboardMarkup:
    total_pages = max(1, (total + per_page - 1) // per_page)
    nav = []
    if page > 0:
        nav.append(_btn("◀ Prev", f"op:users:{page - 1}"))
    nav.append(_btn(f"📄 {page + 1}/{total_pages}", "noop"))
    if (page + 1) < total_pages:
        nav.append(_btn("Next ▶", f"op:users:{page + 1}"))
    return _kb(nav, [_btn("🔙 Back", "op:main")])


def user_action_kb(user_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    ban_btn = _btn("✅ Unban", f"ub:{user_id}") if is_banned else _btn("🚫 Ban", f"bn:{user_id}")
    return _kb([ban_btn, _btn("🔙 Users", "op:users:0")])


# ─── Broadcast ───────────────────────────────────────────────────────────────

def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    return _kb(
        [_btn("✅ Send to all", "bc:confirm"), _btn("❌ Cancel", "bc:cancel")],
    )


def broadcast_done_kb() -> InlineKeyboardMarkup:
    return _kb([_btn("🔙 Owner Panel", "op:main")])


# ─── Voice Selection ─────────────────────────────────────────────────────────

def voice_categories_kb(back: str = "up:main") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    cats = list(VOICE_LIBRARY.items())
    row: list[InlineKeyboardButton] = []
    for cat_key, cat_data in cats:
        row.append(_btn(cat_data["label"], f"vc:cat:{cat_key}"))
        if len(row) == 2:
            builder.row(*row)
            row = []
    if row:
        builder.row(*row)
    builder.row(_btn("🔙 Back", back))
    return builder.as_markup()


def voice_list_kb(cat_key: str, current_id: str = "") -> InlineKeyboardMarkup:
    cat = VOICE_LIBRARY.get(cat_key)
    if not cat:
        return _kb([_btn("🔙 Back", "vc:cats")])
    builder = InlineKeyboardBuilder()
    for vi, v in enumerate(cat["voices"]):
        tick = " ✅" if v["id"] == current_id else ""
        builder.row(_btn(f"{v['name']} – {v['desc']}{tick}", f"vc:set:{cat_key}:{vi}"))
    builder.row(_btn("🔙 Categories", "vc:cats"), _btn("🔙 Menu", "up:main"))
    return builder.as_markup()


# ─── User Panel ──────────────────────────────────────────────────────────────

def user_main_kb() -> InlineKeyboardMarkup:
    return _kb(
        [_btn("🔊 Text → Voice", "up:tts"), _btn("🎤 Voice → Text", "up:stt")],
        [_btn("🎭 Change Voice",  "up:voice"), _btn("📊 My Stats", "up:stats")],
        [_btn("ℹ️ Help",          "up:help")],
    )


def tts_result_kb(voice_name: str) -> InlineKeyboardMarkup:
    return _kb(
        [_btn("🎭 Change Voice", "up:voice"), _btn("🔁 Regenerate", "up:regen")],
        [_btn("🏠 Menu", "up:main")],
    )


def stt_result_kb() -> InlineKeyboardMarkup:
    return _kb(
        [_btn("🔊 Convert to Voice", "up:stt2tts"), _btn("🏠 Menu", "up:main")],
    )


def back_to_menu() -> InlineKeyboardMarkup:
    return _kb([_btn("🏠 Menu", "up:main")])


def cancel_kb(data: str = "up:main") -> InlineKeyboardMarkup:
    return _kb([_btn("❌ Cancel", data)])


# ─── Settings ────────────────────────────────────────────────────────────────

def settings_kb(maintenance: bool) -> InlineKeyboardMarkup:
    m_text = "🔧 Maintenance: ON" if maintenance else "🟢 Maintenance: OFF"
    return _kb(
        [_btn(m_text, "st:toggle_maintenance")],
        [_btn("🔙 Back", "op:main")],
    )


# ─── Misc ─────────────────────────────────────────────────────────────────────

def _mask(key: str) -> str:
    if len(key) <= 12:
        return key[:4] + "****"
    return f"{key[:6]}...{key[-4:]}"
