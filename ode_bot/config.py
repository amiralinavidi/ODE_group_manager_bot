import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH_SECRET = os.getenv("WEBHOOK_PATH_SECRET") or BOT_TOKEN or "webhook"
WEBHOOK_SETUP_SECRET = os.getenv("WEBHOOK_SETUP_SECRET", "")

def _to_int(var_name: str, fallback: int = 0) -> int:
    value = os.getenv(var_name, str(fallback))
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


ADMIN_ID = _to_int("ADMIN_ID", 0)
ODE_GROUP_ID = _to_int("ODE_GROUP_ID", 0)

SHEET_ID = os.getenv("SHEET_ID", "")
SYNC_INTERVAL = _to_int("SYNC_INTERVAL", 3600)
TA_GROUP_ID = _to_int("TA_GROUP_ID", 0)

DB_PATH = DATA_DIR / "ode_class.db"
ROSTER_FILE = DATA_DIR / "roster.xlsx"
CREDENTIALS_FILE = DATA_DIR / "credentials.json"
EXCEL_REPORT_PATH = DATA_DIR / "ODE_Class_Grades.xlsx"
SYNC_TIMER_FILE = DATA_DIR / "last_sync.txt"

DEFAULT_SETTINGS = {
    "bonus_points": "5",
    "approval_limit": "5",
    "forward_limit": "3",
    "post_time": "14:00",
    "timezone": "Asia/Tehran",
    "ta_group_id": str(TA_GROUP_ID),
    "sync_interval": str(SYNC_INTERVAL),
    "points_text": "1",
    "points_photo": "2",
    "points_file": "3",
}

STOP_WORDS = {
    "سلام",
    "درود",
    "ممنون",
    "مرسی",
    "تشکر",
    "سپاس",
    "بله",
    "خیر",
    "نه",
    "ok",
    "thanks",
    "hi",
    "hello",
    "استاد",
    "بچه ها",
    "خداحافظ",
    "فعلا",
    "اره",
    "آره",
    "دقیقا",
    "درسته",
    "چشم",
    "merci",
}


def validate_required_config() -> None:
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not WEBHOOK_URL:
        missing.append("WEBHOOK_URL")
    if not WEBHOOK_PATH_SECRET:
        missing.append("WEBHOOK_PATH_SECRET")
    if not WEBHOOK_SETUP_SECRET:
        missing.append("WEBHOOK_SETUP_SECRET")
    if ADMIN_ID == 0:
        missing.append("ADMIN_ID")
    if ODE_GROUP_ID == 0:
        missing.append("ODE_GROUP_ID")
    if missing:
        names = ", ".join(missing)
        raise ValueError(f"Missing required environment variables: {names}")
