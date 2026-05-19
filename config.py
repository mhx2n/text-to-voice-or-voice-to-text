import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN        = os.getenv("BOT_TOKEN", "").strip()
_raw_owners      = os.getenv("OWNER_IDS", os.getenv("OWNER_ID", "0"))
OWNER_IDS: set[int] = {int(x.strip()) for x in _raw_owners.split(",") if x.strip().isdigit()}
DEFAULT_VOICE_ID = os.getenv("DEFAULT_VOICE_ID", "21m00Tcm4TlvDq8ikWAM").strip()
DEFAULT_MODEL_ID = os.getenv("DEFAULT_MODEL_ID", "eleven_multilingual_v2").strip()
PORT             = int(os.getenv("PORT", "10000"))
DATABASE_FILE    = os.getenv("DATABASE_FILE", "bot.db")
BROADCAST_DELAY  = float(os.getenv("BROADCAST_DELAY", "0.05"))

# ─── Voice Library ────────────────────────────────────────────────────────────
# All voice IDs are verified ElevenLabs pre-made public voices.
# Cloned / non-public voice IDs have been replaced.
VOICE_LIBRARY: dict[str, dict] = {
    "anime": {
        "label": "◈ Anime",
        "voices": [
            {"name": "Akemi",  "id": "EXAVITQu4vr4xnSDxMaL", "desc": "Soft Anime Female"},
            {"name": "Yuki",   "id": "MF3mGyEYCl7XYWbV9V6O", "desc": "Young Anime Girl"},
            {"name": "Hana",   "id": "oWAxZDx7w5VEj9dCyTzz", "desc": "Clear Anime Voice"},
            {"name": "Sakura", "id": "XrExE9yKIg1WjnnlVkGX", "desc": "Expressive Anime"},
        ],
    },
    "girl": {
        "label": "◈ Girl",
        "voices": [
            {"name": "Elli",   "id": "MF3mGyEYCl7XYWbV9V6O", "desc": "Young & Bright"},
            {"name": "Lily",   "id": "pFZP5JQG7iQjIQuC4Bku", "desc": "Sweet & Light"},
            # Amy replaced — nu9bn7ambTzvv3MFShMm is a private cloned voice and returns 404
            {"name": "Rachel", "id": "21m00Tcm4TlvDq8ikWAM", "desc": "Cheerful & Clear"},
            {"name": "Freya",  "id": "jsCqWAovK2LkecY7zXl4", "desc": "Playful Teen"},
        ],
    },
    "women": {
        "label": "◈ Women",
        "voices": [
            {"name": "Bella",   "id": "EXAVITQu4vr4xnSDxMaL", "desc": "Soft & Warm"},
            {"name": "Dorothy", "id": "ThT5KcBeYPX3keUQqHPh", "desc": "British Female"},
            {"name": "Domi",    "id": "AZnzlk1XvdvUeBnXmlld", "desc": "Strong & Clear"},
            {"name": "Grace",   "id": "oWAxZDx7w5VEj9dCyTzz", "desc": "Calm & Smooth"},
            {"name": "Serena",  "id": "pMsXgVXv3BLzUgSXRplE", "desc": "Pleasant Female"},
        ],
    },
    "men": {
        "label": "◈ Men",
        "voices": [
            {"name": "Josh",    "id": "TxGEqnHWrfWFTfGW9XjX", "desc": "Young Male"},
            {"name": "Arnold",  "id": "VR6AewLTigWG4xSOukaG", "desc": "Confident Male"},
            {"name": "Adam",    "id": "pNInz6obpgDQGcFmaJgB", "desc": "Deep Male Voice"},
            {"name": "Sam",     "id": "yoZ06aMxZJJ28mfd3POQ", "desc": "Neutral Male"},
            {"name": "Callum",  "id": "N2lVS1w4EtoT3dr4eOWO", "desc": "Hoarse Male"},
            {"name": "Liam",    "id": "TX3LPaxmHKxFdv7VOQHJ", "desc": "Energetic Male"},
        ],
    },
    "old": {
        "label": "◈ Elder",
        "voices": [
            {"name": "Clyde",  "id": "2EiwWnXFnvU5JabPnv8n", "desc": "Warm Elder"},
            {"name": "Dave",   "id": "CYw3kZ02Hs0563khs1Fj", "desc": "British Elder"},
            {"name": "Fin",    "id": "D38z5RcWu1voky8WS1ja", "desc": "Wise Elder"},
        ],
    },
    "child": {
        "label": "◈ Child",
        "voices": [
            {"name": "Charlie", "id": "IKne3meq5aSn9XLyUdCD", "desc": "Natural Child"},
            {"name": "Matilda", "id": "XrExE9yKIg1WjnnlVkGX", "desc": "Young & Cheerful"},
            {"name": "Mia",     "id": "MF3mGyEYCl7XYWbV9V6O", "desc": "Playful Child"},
        ],
    },
}

# Flat lookup: voice_id → (category_key, voice_index, voice_dict)
VOICE_ID_MAP: dict[str, tuple] = {}
for _cat_key, _cat_data in VOICE_LIBRARY.items():
    for _vi, _v in enumerate(_cat_data["voices"]):
        VOICE_ID_MAP[_v["id"]] = (_cat_key, _vi, _v)
