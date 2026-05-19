# 🤖 Advanced TTS / STT Telegram Bot

ElevenLabs-powered voice bot with a full owner panel, multi-key management, user management, broadcasting, and 6 voice categories — all via inline buttons.

---

## ✨ Features

| Feature | Detail |
|---|---|
| 🔊 Text → Voice | Any text in any language → ElevenLabs MP3 |
| 🎤 Voice → Text | Any voice/audio message → transcript |
| 🎭 6 Voice Categories | Anime · Girl · Women · Men · Old · Child |
| 🔑 Multi-API Keys | Add / remove / toggle / view quota per key |
| 📢 Broadcast | Forward any message type to all users |
| 📋 Live Logs | Last N minutes · all levels or errors only · refresh |
| 👥 User Manager | Paginated list · ban / unban · per-user stats |
| 📊 Stats | CPU · RAM · uptime · key quota summary |
| ⚙️ Maintenance Mode | Disable bot for users without affecting owner |
| 🔘 Inline UI | Everything works via inline buttons — no typing |
| . prefix | All commands work with both `/` and `.` |
| Group support | Owner can use `.t` / `.a` in any group |

---

## 🚀 Deploy to Render

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "initial"
git remote add origin https://github.com/YOUR_NAME/YOUR_REPO.git
git push -u origin main
```

### 2. Create Render Web Service
1. Go to [render.com](https://render.com) → **New → Web Service**
2. Connect your GitHub repo
3. Render detects `render.yaml` automatically

### 3. Set Environment Variables
In Render dashboard → **Environment**:

| Key | Value |
|---|---|
| `BOT_TOKEN` | Your bot token from [@BotFather](https://t.me/BotFather) |
| `OWNER_IDS` | Your Telegram numeric ID(s), comma-separated |

All other variables have sensible defaults.

### 4. Add ElevenLabs Keys
Start the bot, open it in Telegram, then:
- Send `/owner` or `.owner`
- Click **🔑 API Keys → ➕ Add Key**
- Send your ElevenLabs API key (starts with `sk_`)

---

## 📱 Usage

### Users (private chat only)
| Action | How |
|---|---|
| Text → Voice | Just send any text |
| Voice → Text | Send a voice message |
| Change voice | `/voice` or 🎭 button |
| My stats | 📊 button in menu |

### Owner (anywhere)
| Command | Action |
|---|---|
| `/owner` or `.owner` | Open owner panel |
| Reply to voice + `.t` | Transcribe |
| Reply to text + `.a` | Convert to voice |
| `/userbio USER_ID` | View user profile |

---

## 🎭 Voice Categories

| Category | Voices |
|---|---|
| 🎌 Anime | Akemi · Yuki · Hana · Sakura |
| 👧 Girl | Elli · Lily · Amy · Freya |
| 👩 Women | Rachel · Bella · Dorothy · Domi · Grace · Serena |
| 👨 Men | Josh · Arnold · Adam · Sam · Callum · Liam |
| 👴 Old | Clyde · Dave · Joseph · Fin |
| 🧒 Child | Charlie · Matilda · Elli Jr |

All voices use `eleven_multilingual_v2` — they work in **any language**.

---

## 📁 File Structure
```
.
├── main.py          ← Entry point
├── config.py        ← Config + voice library
├── db.py            ← SQLite async database
├── api.py           ← ElevenLabs API wrapper
├── keyboards.py     ← All inline keyboards
├── handlers/
│   ├── admin.py     ← Owner panel handlers
│   └── user.py      ← User handlers + TTS/STT
├── requirements.txt
├── render.yaml
└── .env.example
```

---

## 🔑 Getting ElevenLabs API Keys
1. Go to [elevenlabs.io](https://elevenlabs.io) → Sign up free
2. Profile → API Keys → Create
3. Free plan gives 10,000 chars/month
4. Add multiple keys to extend quota (key rotation is automatic)
