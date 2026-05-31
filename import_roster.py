from pathlib import Path

from ode_bot.config import ROSTER_FILE
from ode_bot.database import init_db
from ode_bot.roster_import import import_roster


if __name__ == "__main__":
    init_db()
    count, errors = import_roster(Path(ROSTER_FILE))
    print(f"Imported/updated rows: {count}")
    if errors:
        print("Warnings:")
        for error in errors:
            print(f"- {error}")
