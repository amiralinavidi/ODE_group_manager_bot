import time

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

from .config import CREDENTIALS_FILE, SHEET_ID, SYNC_INTERVAL, SYNC_TIMER_FILE
from .database import get_connection, get_setting


def get_last_sync_time() -> float:
    if not SYNC_TIMER_FILE.exists():
        return 0.0
    try:
        return float(SYNC_TIMER_FILE.read_text(encoding="utf-8").strip())
    except (TypeError, ValueError):
        return 0.0


def set_last_sync_time(timestamp: float) -> None:
    SYNC_TIMER_FILE.write_text(str(timestamp), encoding="utf-8")


def _safe_int(value: str | None, fallback: int) -> int:
    try:
        return int(value) if value is not None else fallback
    except (TypeError, ValueError):
        return fallback


def sync_to_google_sheets(force: bool = False) -> bool:
    current_time = time.time()
    last_sync = get_last_sync_time()
    sync_interval = _safe_int(get_setting("sync_interval", str(SYNC_INTERVAL)), SYNC_INTERVAL)

    if not force and (current_time - last_sync < sync_interval):
        return False

    if not SHEET_ID or not CREDENTIALS_FILE.exists():
        return False

    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID).sheet1

        conn = get_connection()
        query = """
            SELECT name as Name, total_score as Total_Score, bonus_score as Bonus_Score
            FROM users
            ORDER BY Total_Score DESC
        """
        dataframe = pd.read_sql_query(query, conn)
        conn.close()

        if dataframe.empty:
            data_to_upload = [["Name", "Total_Score", "Bonus_Score"]]
        else:
            dataframe["Name"] = dataframe["Name"].fillna("Unknown Student")
            data_to_upload = [dataframe.columns.values.tolist()] + dataframe.values.tolist()

        sheet.clear()
        sheet.update("A1", data_to_upload)
        set_last_sync_time(current_time)
        return True
    except Exception:
        return False
