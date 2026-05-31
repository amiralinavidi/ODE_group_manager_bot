import argparse
from pathlib import Path

from ode_bot.config import ROSTER_FILE
from ode_bot.database import init_db
from ode_bot.roster_import import import_roster


def main() -> None:
    parser = argparse.ArgumentParser(description="ODE bot management commands")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Create tables and default settings.")

    import_parser = sub.add_parser("import-roster", help="Import class roster from CSV/XLSX.")
    import_parser.add_argument(
        "--file",
        default=str(ROSTER_FILE),
        help=f"Path to roster file (default: {ROSTER_FILE})",
    )

    args = parser.parse_args()

    if args.command == "init-db":
        init_db()
        print("Database initialized.")
        return

    if args.command == "import-roster":
        init_db()
        imported_count, errors = import_roster(Path(args.file))
        print(f"Imported/updated rows: {imported_count}")
        if errors:
            print("Warnings:")
            for error in errors:
                print(f"- {error}")


if __name__ == "__main__":
    main()
