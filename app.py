import os

from flask import Flask, abort, request
import telebot

from ode_bot.bot_handlers import bot
from ode_bot.config import (
    BOT_TOKEN,
    WEBHOOK_PATH_SECRET,
    WEBHOOK_SETUP_SECRET,
    WEBHOOK_URL,
    validate_required_config,
)
from ode_bot.database import init_db

app = Flask(__name__)
init_db()


@app.get("/")
def index() -> tuple[str, int]:
    return "ODE Bot is active and running.", 200


@app.post(f"/{WEBHOOK_PATH_SECRET}")
def webhook() -> tuple[str, int]:
    if request.headers.get("content-type") != "application/json":
        abort(403)
    json_string = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "", 200


@app.get("/set_webhook")
def set_webhook() -> tuple[str, int]:
    if request.args.get("key") != WEBHOOK_SETUP_SECRET:
        return "Unauthorized", 401

    try:
        validate_required_config()
    except ValueError as exc:
        return str(exc), 400

    bot.remove_webhook()
    target = f"{WEBHOOK_URL.rstrip('/')}/{WEBHOOK_PATH_SECRET}"
    success = bot.set_webhook(url=target)
    if success:
        return f"Webhook successfully set to {target}", 200
    return "Webhook setup failed.", 400


if __name__ == "__main__":
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is required.")
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    port = int(os.getenv("PORT", "5000"))
    app.run(debug=debug, port=port)
