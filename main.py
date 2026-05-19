"""
Voice Studio — Telegram Bot
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

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("bot.main")

# ─── Startup checks ───────────────────────────────────────────────────────────

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Set it in environment variables.")
if not OWNER_IDS:
    raise RuntimeError("OWNER_IDS is missing. Set at least one owner Telegram ID.")

# ─── Bot / Dispatcher ─────────────────────────────────────────────────────────

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher(storage=MemoryStorage())
dp.include_router(admin_router)
dp.include_router(user_router)

# ─── Landing page HTML ────────────────────────────────────────────────────────

_LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Voice Studio — Telegram Bot</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg: #0d0d0f;
      --surface: #16181c;
      --border: #2a2d35;
      --accent: #7c6af7;
      --accent2: #5ea7ff;
      --text: #e8eaf0;
      --muted: #8a8fa8;
    }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 2rem;
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 3rem 2.5rem;
      max-width: 520px;
      width: 100%;
      text-align: center;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(124,106,247,.15);
      border: 1px solid rgba(124,106,247,.3);
      border-radius: 999px;
      padding: 4px 14px;
      font-size: .78rem;
      font-weight: 600;
      letter-spacing: .06em;
      color: var(--accent);
      text-transform: uppercase;
      margin-bottom: 1.6rem;
    }
    .dot {
      width: 7px; height: 7px;
      background: #22c55e;
      border-radius: 50%;
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50%       { opacity: .4; }
    }
    h1 {
      font-size: 2.2rem;
      font-weight: 700;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      margin-bottom: .6rem;
      line-height: 1.2;
    }
    .subtitle {
      color: var(--muted);
      font-size: 1rem;
      margin-bottom: 2.4rem;
      line-height: 1.6;
    }
    .features {
      list-style: none;
      text-align: left;
      margin-bottom: 2.4rem;
      display: flex;
      flex-direction: column;
      gap: .75rem;
    }
    .features li {
      display: flex;
      align-items: flex-start;
      gap: .75rem;
      font-size: .95rem;
      color: var(--text);
    }
    .features li span.icon {
      color: var(--accent);
      font-style: normal;
      flex-shrink: 0;
      margin-top: 1px;
    }
    .btn {
      display: inline-block;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      color: #fff;
      font-weight: 700;
      font-size: 1rem;
      padding: .85rem 2.2rem;
      border-radius: 12px;
      text-decoration: none;
      transition: opacity .2s;
      letter-spacing: .02em;
    }
    .btn:hover { opacity: .88; }
    .footer {
      margin-top: 2rem;
      font-size: .78rem;
      color: var(--muted);
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="badge"><span class="dot"></span> Operational</div>
    <h1>Voice Studio</h1>
    <p class="subtitle">
      High-quality Text-to-Speech &amp; Speech-to-Text<br>
      powered by ElevenLabs &mdash; available on Telegram.
    </p>
    <ul class="features">
      <li><span class="icon">&#9670;</span> Convert any text message to natural-sounding audio</li>
      <li><span class="icon">&#9670;</span> Transcribe voice messages to text instantly</li>
      <li><span class="icon">&#9670;</span> Choose from 25+ premium voices across 6 categories</li>
      <li><span class="icon">&#9670;</span> Inline mode — use in any group via <code>@botname text</code></li>
      <li><span class="icon">&#9670;</span> Supports multilingual content with <em>eleven_multilingual_v2</em></li>
    </ul>
    <a class="btn" href="https://t.me/amarquizbossstlls_bot">Open in Telegram &rarr;</a>
    <p class="footer">Voice Studio &middot; Running on Render &middot; Health OK</p>
  </div>
</body>
</html>"""

# ─── Web server ───────────────────────────────────────────────────────────────

async def _index(_: web.Request) -> web.Response:
    return web.Response(text=_LANDING_HTML, content_type="text/html")


async def _health(_: web.Request) -> web.Response:
    return web.Response(text="OK")


async def _run_web() -> None:
    app = web.Application()
    app.router.add_get("/", _index)
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("Web server listening on port %s", PORT)
    await asyncio.Event().wait()

# ─── Bot polling loop ─────────────────────────────────────────────────────────

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

# ─── Entry point ──────────────────────────────────────────────────────────────

async def main() -> None:
    await db.init_db()

    db_handler = db.DBLogHandler()
    db_handler.setLevel(logging.WARNING)
    logging.getLogger().addHandler(db_handler)

    timeout   = aiohttp.ClientTimeout(total=180)
    connector = aiohttp.TCPConnector(limit=30, ttl_dns_cache=300)
    session   = aiohttp.ClientSession(timeout=timeout, connector=connector)

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
