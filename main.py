"""
Advanced TTS / STT Telegram Bot
ElevenLabs-powered · aiogram v3 · Render-ready

Environment variables:
    BOT_TOKEN       – Telegram bot token
    OWNER_IDS       – comma-separated Telegram user IDs (e.g. 123,456)
    PORT            – web server port (default 10000)
    DATABASE_FILE   – SQLite file path (default bot.db)
    DEFAULT_VOICE_ID– fallback ElevenLabs voice ID
    DEFAULT_MODEL_ID– ElevenLabs model (default eleven_multilingual_v2)
    BROADCAST_DELAY – seconds between broadcast messages (default 0.05)
"""
from __future__ import annotations

import asyncio
import logging

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import db
from config import BOT_TOKEN, OWNER_IDS, PORT
from handlers import admin_router, user_router
import handlers.admin as admin_mod
import handlers.user  as user_mod

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("bot.main")


# ─── Startup checks ──────────────────────────────────────────────────────────

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Set it in environment variables.")
if not OWNER_IDS:
    raise RuntimeError("OWNER_IDS is missing. Set at least one owner Telegram ID.")


# ─── Bot / Dispatcher ────────────────────────────────────────────────────────

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher(storage=MemoryStorage())
dp.include_router(admin_router)
dp.include_router(user_router)


# ─── Health-check web server (Render requirement) ────────────────────────────

async def _health(_: web.Request) -> web.Response:
    return web.Response(text="OK")


async def _run_web() -> None:
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("Health-check server listening on port %s", PORT)
    await asyncio.Event().wait()          # block forever


# ─── Bot polling loop (auto-restart on error) ────────────────────────────────

async def _run_bot() -> None:
    while True:
        try:
            logger.info("Starting bot polling…")
            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
                polling_timeout=60,
                drop_pending_updates=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Polling crashed: %s", exc)
            await db.write_log("ERROR", f"Polling crashed: {exc}")
            await asyncio.sleep(5)


# ─── Entry point ─────────────────────────────────────────────────────────────

async def main() -> None:
    await db.init_db()

    # Attach DB log handler to capture WARNING+ into bot_logs table
    db_handler = db.DBLogHandler()
    db_handler.setLevel(logging.WARNING)
    logging.getLogger().addHandler(db_handler)

    # Shared aiohttp session
    timeout   = aiohttp.ClientTimeout(total=180)
    connector = aiohttp.TCPConnector(limit=30, ttl_dns_cache=300)
    session   = aiohttp.ClientSession(timeout=timeout, connector=connector)

    # Inject session into handlers
    admin_mod.set_session(session)
    user_mod.set_session(session)

    try:
        await asyncio.gather(_run_web(), _run_bot())
    finally:
        logger.info("Shutting down…")
        await session.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
