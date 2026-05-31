import sqlite3
from typing import Any

from .config import DB_PATH, DEFAULT_SETTINGS


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db() -> None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            student_id TEXT PRIMARY KEY,
            name TEXT,
            telegram_username TEXT UNIQUE,
            numeric_id INTEGER UNIQUE,
            text_score INTEGER DEFAULT 0,
            photo_score INTEGER DEFAULT 0,
            file_score INTEGER DEFAULT 0,
            bonus_score INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS unknown_users (
            numeric_id INTEGER PRIMARY KEY,
            telegram_username TEXT,
            first_name TEXT,
            bonus_score INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bonus_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ta_chat_id INTEGER,
            ta_message_id INTEGER,
            scheduled_time TEXT,
            status TEXT DEFAULT 'pending',
            main_group_message_id INTEGER
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bonus_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bonus_id INTEGER,
            student_id INTEGER,
            student_name TEXT,
            message_id INTEGER,
            original_message_id INTEGER,
            status TEXT DEFAULT 'pending',
            order_num INTEGER
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tracked_groups (
            chat_id INTEGER PRIMARY KEY,
            title TEXT
        )
        """
    )

    for key, value in DEFAULT_SETTINGS.items():
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )

    conn.commit()
    conn.close()


def get_setting(key: str, default: str | None = None) -> str | None:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0]
        return default
    except sqlite3.Error:
        return default


def set_setting(key: str, value: Any) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def track_group(chat_id: int, title: str | None) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO tracked_groups (chat_id, title) VALUES (?, ?)",
        (chat_id, title or ""),
    )
    conn.commit()
    conn.close()


def get_user_score(numeric_id: int) -> tuple[tuple[Any, ...] | None, str | None]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, total_score, bonus_score FROM users WHERE numeric_id = ?",
        (numeric_id,),
    )
    user = cursor.fetchone()
    if user:
        conn.close()
        return user, "known"

    cursor.execute(
        "SELECT first_name, total_score, bonus_score FROM unknown_users WHERE numeric_id = ?",
        (numeric_id,),
    )
    unknown = cursor.fetchone()
    conn.close()
    if unknown:
        return unknown, "unknown"
    return None, None


def _as_int(value: str | None, fallback: int) -> int:
    try:
        return int(value) if value is not None else fallback
    except (TypeError, ValueError):
        return fallback


def add_points(
    username: str | None,
    numeric_id: int,
    first_name: str | None,
    msg_type: str,
    custom_points: int | None = None,
) -> None:
    conn = get_connection()
    cursor = conn.cursor()

    clean_username = username.replace("@", "").strip().lower() if username else None
    first_name = first_name or "Unknown"

    cursor.execute(
        """
        SELECT student_id FROM users
        WHERE telegram_username = ? OR numeric_id = ?
        """,
        (clean_username, numeric_id),
    )
    row = cursor.fetchone()

    if row:
        student_id = row[0]
        cursor.execute(
            "UPDATE users SET numeric_id = ? WHERE student_id = ?",
            (numeric_id, student_id),
        )
        if custom_points is not None:
            if msg_type == "bonus":
                cursor.execute(
                    """
                    UPDATE users
                    SET total_score = total_score + ?,
                        bonus_score = bonus_score + ?
                    WHERE student_id = ?
                    """,
                    (custom_points, custom_points, student_id),
                )
            else:
                cursor.execute(
                    "UPDATE users SET total_score = total_score + ? WHERE student_id = ?",
                    (custom_points, student_id),
                )
        else:
            points_file = _as_int(get_setting("points_file", "3"), 3)
            points_photo = _as_int(get_setting("points_photo", "2"), 2)
            points_text = _as_int(get_setting("points_text", "1"), 1)
            if msg_type == "file":
                cursor.execute(
                    """
                    UPDATE users
                    SET file_score = file_score + 1,
                        total_score = total_score + ?
                    WHERE student_id = ?
                    """,
                    (points_file, student_id),
                )
            elif msg_type == "photo":
                cursor.execute(
                    """
                    UPDATE users
                    SET photo_score = photo_score + 1,
                        total_score = total_score + ?
                    WHERE student_id = ?
                    """,
                    (points_photo, student_id),
                )
            elif msg_type == "text":
                cursor.execute(
                    """
                    UPDATE users
                    SET text_score = text_score + 1,
                        total_score = total_score + ?
                    WHERE student_id = ?
                    """,
                    (points_text, student_id),
                )
    else:
        cursor.execute(
            """
            INSERT OR IGNORE INTO unknown_users (numeric_id, telegram_username, first_name)
            VALUES (?, ?, ?)
            """,
            (numeric_id, clean_username, first_name),
        )
        if custom_points is not None:
            if msg_type == "bonus":
                cursor.execute(
                    """
                    UPDATE unknown_users
                    SET total_score = total_score + ?,
                        bonus_score = bonus_score + ?
                    WHERE numeric_id = ?
                    """,
                    (custom_points, custom_points, numeric_id),
                )
            else:
                cursor.execute(
                    "UPDATE unknown_users SET total_score = total_score + ? WHERE numeric_id = ?",
                    (custom_points, numeric_id),
                )
        else:
            points_file = _as_int(get_setting("points_file", "3"), 3)
            points_photo = _as_int(get_setting("points_photo", "2"), 2)
            points_text = _as_int(get_setting("points_text", "1"), 1)
            points = {
                "file": points_file,
                "photo": points_photo,
                "text": points_text,
            }.get(msg_type, points_text)
            cursor.execute(
                "UPDATE unknown_users SET total_score = total_score + ? WHERE numeric_id = ?",
                (points, numeric_id),
            )

    conn.commit()
    conn.close()
