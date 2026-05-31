# ODE Group Manager Bot (GitHub-Ready)

Telegram bot for managing ODE class group activity, scoring students, handling bonus-question workflows, and syncing leaderboard data to Google Sheets.

## What this version improves

- Keeps all new work isolated in `new/` so your original project remains untouched.
- Adds a cleaner project layout with package-based modules.
- Adds safer config practices (`.env.example`, `.gitignore`, no secrets in code).
- Tightens admin flow checks for settings and bonus approvals.
- Fixes bonus scheduling rollover (`+1 day` logic without month-end crash).
- Adds management commands for DB setup and roster import.

## Project structure

```text
new/
├── app.py
├── wsgi.py
├── manage.py
├── import_roster.py
├── requirements.txt
├── pyproject.toml
├── .env.example
├── .gitignore
├── data/
│   └── .gitkeep
└── ode_bot/
    ├── __init__.py
    ├── config.py
    ├── database.py
    ├── bot_handlers.py
    ├── sheets_sync.py
    └── roster_import.py
```

## Quick start

1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create `.env` from `.env.example` and fill in real values.
4. Initialize database:
   ```bash
   python manage.py init-db
   ```
5. Import roster (optional but recommended):
   ```bash
   python manage.py import-roster --file data/roster.xlsx
   ```
6. Run locally:
   ```bash
   python app.py
   ```

## Required environment variables

- `BOT_TOKEN`
- `WEBHOOK_URL`
- `WEBHOOK_PATH_SECRET`
- `WEBHOOK_SETUP_SECRET`
- `ADMIN_ID`
- `ODE_GROUP_ID`

Optional:

- `SHEET_ID`
- `SYNC_INTERVAL`
- `TA_GROUP_ID`

## PythonAnywhere deployment notes

- Point your WSGI file to `new/wsgi.py`.
- Install dependencies from `new/requirements.txt`.
- Add `.env` in `new/` with production values.
- Open this URL once to register webhook:
  - `https://<your-domain>/set_webhook?key=<WEBHOOK_SETUP_SECRET>`

## GitHub publish checklist

1. Confirm no secrets are inside tracked files.
2. Keep `credentials.json`, `.env`, `.db`, and exports out of Git (already covered by `.gitignore`).
3. Initialize repo in `new/`:
   ```bash
   git init
   git add .
   git commit -m "Initial GitHub-ready ODE bot"
   ```
4. Create remote and push:
   ```bash
   git remote add origin <your-repo-url>
   git branch -M main
   git push -u origin main
   ```
