"""
ElevenLabs API helpers.
All functions require an active aiohttp.ClientSession passed in.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import aiohttp

from config import DEFAULT_MODEL_ID

logger = logging.getLogger("bot.api")

TIMEOUT = aiohttp.ClientTimeout(total=120)


# ─── Subscription ────────────────────────────────────────────────────────────

async def get_subscription(session: aiohttp.ClientSession, api_key: str) -> Optional[dict]:
    url = "https://api.elevenlabs.io/v1/user/subscription"
    try:
        async with session.get(
            url,
            headers={"xi-api-key": api_key},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                return None
            return await resp.json()
    except Exception as exc:
        logger.warning("get_subscription failed for key %s…: %s", api_key[:8], exc)
        return None


def parse_quota(sub: dict) -> tuple[int, int]:
    """Returns (used, limit)."""
    used  = int(sub.get("character_count", 0) or 0)
    limit = int(sub.get("character_limit", 0) or 0)
    return used, limit


def has_quota(sub: dict) -> bool:
    used, limit = parse_quota(sub)
    if limit <= 0:
        return True
    return used < limit


# ─── Key rotation ─────────────────────────────────────────────────────────────

async def get_working_key(
    session: aiohttp.ClientSession, keys: list[str]
) -> tuple[Optional[str], Optional[dict]]:
    """Return first active key that still has quota."""
    for key in keys:
        sub = await get_subscription(session, key)
        if sub and has_quota(sub):
            return key, sub
    return None, None


# ─── Text-to-Speech ──────────────────────────────────────────────────────────

async def tts(
    session: aiohttp.ClientSession,
    api_key: str,
    voice_id: str,
    text: str,
    model_id: str = DEFAULT_MODEL_ID,
) -> tuple[bool, Optional[bytes], str]:
    """Returns (ok, audio_bytes, error_msg)."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {"text": text, "model_id": model_id}
    try:
        async with session.post(url, headers=headers, json=payload, timeout=TIMEOUT) as resp:
            body = await resp.read()
            if resp.status != 200:
                err = body.decode("utf-8", errors="ignore")[:500]
                return False, None, f"HTTP {resp.status}: {err}"
            return True, body, ""
    except Exception as exc:
        return False, None, str(exc)


# ─── Speech-to-Text ──────────────────────────────────────────────────────────

async def stt(
    session: aiohttp.ClientSession,
    api_key: str,
    audio_bytes: bytes,
    filename: str = "voice.ogg",
) -> tuple[bool, str]:
    """Returns (ok, text_or_error)."""
    url = "https://api.elevenlabs.io/v1/speech-to-text"
    form = aiohttp.FormData()
    form.add_field(
        "file", audio_bytes, filename=filename, content_type="application/octet-stream"
    )
    form.add_field("model_id", "scribe_v1")
    try:
        async with session.post(
            url,
            headers={"xi-api-key": api_key},
            data=form,
            timeout=TIMEOUT,
        ) as resp:
            body = await resp.json()
            if resp.status != 200:
                return False, str(body)[:500]
            text = body.get("text", "").strip()
            return True, text or "(no speech detected)"
    except Exception as exc:
        return False, str(exc)


# ─── Voices list ─────────────────────────────────────────────────────────────

async def list_voices(
    session: aiohttp.ClientSession, api_key: str
) -> Optional[list[dict]]:
    url = "https://api.elevenlabs.io/v1/voices"
    try:
        async with session.get(
            url,
            headers={"xi-api-key": api_key},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get("voices", [])
    except Exception:
        return None
