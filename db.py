"""
Async SQLite database layer.
All public functions are safe to call from async context.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite

from config import DATABASE_FILE, DEFAULT_VOICE_ID

logger = logging.getLogger("bot.db")
_lock = asyncio.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ─── Schema ──────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    full_name   TEXT,
    voice_id    TEXT    NOT NULL DEFAULT 'EXAVITQu4vr4xnSDxMaL',
    voice_cat   TEXT    NOT NULL DEFAULT 'women',
    voice_name  TEXT    NOT NULL DEFAULT 'Bella',
    is_banned   INTEGER NOT NULL DEFAULT 0,
    tts_count   INTEGER NOT NULL DEFAULT 0,
    stt_count   INTEGER NOT NULL DEFAULT 0,
    joined_at   TEXT    NOT NULL,
    last_seen   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key_value   TEXT    NOT NULL UNIQUE,
    label       TEXT    NOT NULL DEFAULT '',
    is_active   INTEGER NOT NULL DEFAULT 1,
    added_at    TEXT    NOT NULL,
    last_used   TEXT,
    chars_used  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bot_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    level       TEXT    NOT NULL,
    message     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bot_logs_time ON bot_logs(created_at);

CREATE TABLE IF NOT EXISTS broadcasts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_by  INTEGER NOT NULL,
    msg_text    TEXT,
    msg_type    TEXT    NOT NULL DEFAULT 'text',
    sent_count  INTEGER NOT NULL DEFAULT 0,
    fail_count  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.executescript(_SCHEMA)
        await db.commit()
    logger.info("Database initialised → %s", DATABASE_FILE)


# ─── Users ───────────────────────────────────────────────────────────────────

async def upsert_user(user_id: int, username: str | None, full_name: str) -> None:
    now = _now()
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, username, full_name, joined_at, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username  = excluded.username,
                full_name = excluded.full_name,
                last_seen = excluded.last_seen
            """,
            (user_id, username, full_name, now, now),
        )
        await db.commit()


async def get_user(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_user_voice(user_id: int) -> tuple[str, str, str]:
    """Returns (voice_id, voice_cat, voice_name)."""
    user = await get_user(user_id)
    if not user:
        return DEFAULT_VOICE_ID, "women", "Bella"
    return user["voice_id"], user["voice_cat"], user["voice_name"]


async def set_user_voice(user_id: int, voice_id: str, voice_cat: str, voice_name: str) -> None:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            "UPDATE users SET voice_id=?, voice_cat=?, voice_name=? WHERE user_id=?",
            (voice_id, voice_cat, voice_name, user_id),
        )
        await db.commit()


async def increment_user_stat(user_id: int, field: str) -> None:
    if field not in ("tts_count", "stt_count"):
        return
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            f"UPDATE users SET {field} = {field} + 1, last_seen = ? WHERE user_id = ?",
            (_now(), user_id),
        )
        await db.commit()


async def ban_user(user_id: int, ban: bool) -> None:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            "UPDATE users SET is_banned = ? WHERE user_id = ?", (1 if ban else 0, user_id)
        )
        await db.commit()


async def get_all_users(page: int = 0, per_page: int = 8) -> tuple[list[dict], int]:
    offset = page * per_page
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT * FROM users ORDER BY joined_at DESC LIMIT ? OFFSET ?",
            (per_page, offset),
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    return rows, total


async def get_all_user_ids() -> list[int]:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        async with db.execute(
            "SELECT user_id FROM users WHERE is_banned = 0"
        ) as cur:
            return [r[0] for r in await cur.fetchall()]


# ─── API Keys ────────────────────────────────────────────────────────────────

async def add_api_key(key_value: str, label: str = "") -> bool:
    """Returns True if inserted, False if already exists."""
    try:
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "INSERT INTO api_keys (key_value, label, added_at) VALUES (?, ?, ?)",
                (key_value, label, _now()),
            )
            await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def remove_api_key(key_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        cur = await db.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        await db.commit()
        return cur.rowcount > 0


async def toggle_api_key(key_id: int) -> bool:
    """Toggles active state. Returns new state."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        async with db.execute(
            "SELECT is_active FROM api_keys WHERE id = ?", (key_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return False
            new_state = 0 if row[0] else 1
        await db.execute(
            "UPDATE api_keys SET is_active = ? WHERE id = ?", (new_state, key_id)
        )
        await db.commit()
        return bool(new_state)


async def get_all_api_keys() -> list[dict]:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM api_keys ORDER BY id"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def mark_key_used(key_value: str, chars: int = 0) -> None:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            "UPDATE api_keys SET last_used = ?, chars_used = chars_used + ? WHERE key_value = ?",
            (_now(), chars, key_value),
        )
        await db.commit()


# ─── Logs ─────────────────────────────────────────────────────────────────────

async def write_log(level: str, message: str) -> None:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            "INSERT INTO bot_logs (level, message, created_at) VALUES (?, ?, ?)",
            (level.upper(), message, _now()),
        )
        await db.commit()


async def get_recent_logs(
    minutes: int = 10, level: str | None = None, limit: int = 50
) -> list[dict]:
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        if level:
            async with db.execute(
                "SELECT * FROM bot_logs WHERE created_at >= ? AND level = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (cutoff, level.upper(), limit),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        else:
            async with db.execute(
                "SELECT * FROM bot_logs WHERE created_at >= ? "
                "ORDER BY created_at DESC LIMIT ?",
                (cutoff, limit),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]


async def clear_old_logs(days: int = 7) -> None:
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("DELETE FROM bot_logs WHERE created_at < ?", (cutoff,))
        await db.commit()


# ─── Broadcasts ──────────────────────────────────────────────────────────────

async def save_broadcast(
    created_by: int, msg_text: str, msg_type: str, sent: int, fail: int
) -> int:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        cur = await db.execute(
            "INSERT INTO broadcasts (created_by, msg_text, msg_type, sent_count, fail_count, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (created_by, msg_text, msg_type, sent, fail, _now()),
        )
        await db.commit()
        return cur.lastrowid


# ─── Settings ────────────────────────────────────────────────────────────────

async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else default


async def set_setting(key: str, value: str) -> None:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await db.commit()


# ─── DB-backed log handler ────────────────────────────────────────────────────

class DBLogHandler(logging.Handler):
    """Writes WARNING+ logs to the database for the owner's log viewer."""

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.WARNING:
            return
        msg = self.format(record)
        asyncio.create_task(_async_write_log(record.levelname, msg))


async def _async_write_log(level: str, msg: str) -> None:
    try:
        await write_log(level, msg)
    except Exception:
        pass
