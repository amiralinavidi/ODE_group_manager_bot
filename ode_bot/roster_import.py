from pathlib import Path

import pandas as pd

from .database import get_connection

REQUIRED_COLUMNS = ("Student_ID", "Name", "Telegram_Username")


def import_roster(file_path: Path) -> tuple[int, list[str]]:
    if not file_path.exists():
        return 0, [f"Could not find roster file: {file_path}"]

    if file_path.suffix.lower() == ".csv":
        dataframe = pd.read_csv(file_path)
    else:
        dataframe = pd.read_excel(file_path)

    errors: list[str] = []
    for column in REQUIRED_COLUMNS:
        if column not in dataframe.columns:
            errors.append(f"Missing required column: {column}")

    if errors:
        return 0, errors

    conn = get_connection()
    cursor = conn.cursor()
    inserted_or_updated = 0

    for _, row in dataframe.iterrows():
        student_id = str(row["Student_ID"]).split(".")[0].strip()
        name = str(row["Name"]).strip()
        username = str(row["Telegram_Username"]).strip()
        if not username or username.lower() == "nan":
            clean_username = None
        else:
            clean_username = username.replace("@", "").lower()

        try:
            cursor.execute("SELECT student_id FROM users WHERE student_id = ?", (student_id,))
            if cursor.fetchone():
                cursor.execute(
                    """
                    UPDATE users
                    SET name = ?, telegram_username = ?
                    WHERE student_id = ?
                    """,
                    (name, clean_username, student_id),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO users (student_id, name, telegram_username)
                    VALUES (?, ?, ?)
                    """,
                    (student_id, name, clean_username),
                )
            inserted_or_updated += 1
        except Exception as exc:
            errors.append(f"Failed to import {name} ({student_id}): {exc}")

    conn.commit()
    conn.close()
    return inserted_or_updated, errors
