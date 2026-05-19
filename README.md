# Voice Studio — Telegram Bot

ElevenLabs-powered Text-to-Speech and Speech-to-Text bot built with aiogram v3, deployable on Render.

---

## What Was Fixed (v2)

### Critical Bug Fix
- **Broken voice ID removed**: `nu9bn7ambTzvv3MFShMm` (the "Amy" voice in the Girl category) is a private cloned
  voice that returns `HTTP 404: voice_not_found`. It has been replaced with `21m00Tcm4TlvDq8ikWAM` (Rachel),
  a verified ElevenLabs pre-made public voice. This eliminates the recurring TTS failure.

### New Feature: Inline Mode (Owner-Only)
- The bot now supports Telegram inline queries.
- Only the owner can use it. In any group or chat, type `@yourbotname some text` and select the result to
  send a voice audio file instantly.
- Results are cached in memory for 10 minutes to avoid redundant API calls.
- To enable inline mode in BotFather: `/setinline` → set placeholder text (e.g. "Type text to convert…").

### New Feature: Bot On / Off Toggle
- Under **Owner Panel → Bot Settings**, the owner can now clearly toggle the system online or offline.
- When offline, all regular users receive a maintenance notice. The owner retains full access.

### Landing Page
- Visiting the bot's Render URL now displays a professional HTML status page instead of plain "OK".

### UI / UX Overhaul
- All messages rewritten in professional English — no informal phrasing.
- All emoji replaced with Unicode symbols (◆ ▸ ● ○ ◈ ✓ ✗ ⊕ ⊗ ⟳ ◀ ▶) for a premium aesthetic.
- Regenerate button now actually regenerates the last TTS text (stored in FSM state).
- STT → TTS conversion uses a more robust text extraction parser.

---

## Setup

### Environment Variables

```
BOT_TOKEN        = your Telegram bot token
OWNER_IDS        = comma-separated Telegram user IDs (e.g. 123456,789012)
DEFAULT_VOICE_ID = 21m00Tcm4TlvDq8ikWAM   (Rachel — reliable default)
DEFAULT_MODEL_ID = eleven_multilingual_v2
PORT             = 10000
DATABASE_FILE    = bot.db
BROADCAST_DELAY  = 0.05
```

### Enable Inline Mode in BotFather

1. Open BotFather and send `/setinline`
2. Choose your bot
3. Set placeholder: `Type text to convert to voice…`

### Deploy on Render

Push to GitHub and connect the repo to Render. The `render.yaml` is pre-configured.

---

## Owner Commands

| Command | Where | Description |
|---------|-------|-------------|
| `/owner` or `.owner` | Any chat | Open owner panel |
| `/panel` or `.panel` | Any chat | Open owner panel |
| `.t` (reply to voice) | Any chat | Transcribe the replied voice message |
| `.a` (reply to text)  | Any chat | Convert the replied text to voice |
| `@botname text`       | Any chat | Inline TTS (owner-only) |

---

## Voice Categories

All voices use verified ElevenLabs pre-made public voice IDs.

| Category | Voices |
|----------|--------|
| Anime    | Akemi, Yuki, Hana, Sakura |
| Girl     | Elli, Lily, Rachel, Freya |
| Women    | Bella, Dorothy, Domi, Grace, Serena |
| Men      | Josh, Arnold, Adam, Sam, Callum, Liam |
| Elder    | Clyde, Dave, Fin |
| Child    | Charlie, Matilda, Mia |
