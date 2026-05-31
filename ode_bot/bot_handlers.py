import re
import threading
import time
from datetime import datetime, timedelta

import pandas as pd
import pytz
import telebot
from telebot.apihelper import ApiTelegramException
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from .config import ADMIN_ID, BOT_TOKEN, EXCEL_REPORT_PATH, ODE_GROUP_ID, STOP_WORDS
from .database import add_points, get_connection, get_setting, get_user_score, set_setting, track_group
from .sheets_sync import sync_to_google_sheets

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required.")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

LAST_HEARTBEAT = 0.0
HEARTBEAT_LOCK = threading.Lock()

INT_SETTING_KEYS = {
    "bonus_points",
    "approval_limit",
    "forward_limit",
    "sync_interval",
    "points_text",
    "points_photo",
    "points_file",
}


def to_persian_num(value: object) -> str:
    if value is None:
        return ""
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    english_digits = "0123456789"
    translation = str.maketrans(english_digits, persian_digits)
    return str(value).translate(translation)


def get_student_menu() -> ReplyKeyboardMarkup:
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("📊 مشاهده امتیاز من"))
    return markup


def get_now() -> datetime:
    timezone_name = get_setting("timezone", "Asia/Tehran") or "Asia/Tehran"
    try:
        timezone = pytz.timezone(timezone_name)
    except pytz.UnknownTimeZoneError:
        timezone = pytz.timezone("Asia/Tehran")
    return datetime.now(timezone)


def safe_answer_callback(call_id: str) -> None:
    try:
        bot.answer_callback_query(call_id)
    except ApiTelegramException:
        pass


def _is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def _get_int_setting(key: str, fallback: int) -> int:
    value = get_setting(key, str(fallback))
    try:
        return int(value) if value is not None else fallback
    except (TypeError, ValueError):
        return fallback


def _validate_setting_value(key: str, value: str) -> str | None:
    if key in INT_SETTING_KEYS:
        try:
            parsed = int(value)
        except ValueError:
            return "Value must be a number."
        if parsed < 0:
            return "Value cannot be negative."
        if key in {"approval_limit", "forward_limit", "sync_interval"} and parsed == 0:
            return "Value must be greater than zero."
        return None

    if key == "ta_group_id":
        try:
            int(value)
        except ValueError:
            return "TA Group ID must be numeric."
        return None

    if key == "post_time":
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError:
            return "Time format must be HH:MM."
        return None

    if key == "timezone":
        try:
            pytz.timezone(value)
        except pytz.UnknownTimeZoneError:
            return "Timezone is invalid."
        return None

    return None


@bot.message_handler(commands=["admin", "start"], func=lambda message: message.chat.type == "private")
def start_handler(message: telebot.types.Message) -> None:
    if _is_admin(message.from_user.id):
        show_admin_panel(message)
        return

    welcome_text = (
        "سلام! خوش آمدید. 😊\n\n"
        "من ربات مدیریت گروه درس معادلات دیفرانسیل هستم.\n"
        "فعالیت‌های شما در گروه را بررسی می‌کنم و امتیازدهی انجام می‌دهم.\n\n"
        "برای دیدن امتیاز خود از دکمه زیر استفاده کنید:"
    )
    bot.reply_to(message, welcome_text, reply_markup=get_student_menu())


def show_admin_panel(message: telebot.types.Message) -> None:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📊 Export Excel", callback_data="admin_export"),
        InlineKeyboardButton("🔄 Force Sync", callback_data="admin_sync"),
        InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings"),
        InlineKeyboardButton("❓ Check Bonus", callback_data="admin_check_bonus"),
    )
    bot.send_message(
        message.chat.id,
        "⚙️ **ODE Admin Control Panel**",
        reply_markup=markup,
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["getid"], func=lambda message: _is_admin(message.from_user.id))
def handle_getid(message: telebot.types.Message) -> None:
    if message.chat.type != "private":
        bot.reply_to(
            message,
            f"Chat ID: `{message.chat.id}`\nTitle: {message.chat.title}",
            parse_mode="Markdown",
        )
        track_group(message.chat.id, message.chat.title or "")
        return

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, title FROM tracked_groups")
    groups = cursor.fetchall()
    conn.close()

    if not groups:
        bot.reply_to(message, "No groups tracked yet. Use /getid in a group first.")
        return

    markup = InlineKeyboardMarkup()
    for group_id, title in groups:
        markup.add(InlineKeyboardButton(f"{title} ({group_id})", callback_data=f"gid_{group_id}"))
    bot.reply_to(message, "Select a group to see its ID:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("gid_"))
def gid_callback(call: telebot.types.CallbackQuery) -> None:
    group_id = call.data.split("_", maxsplit=1)[1]
    safe_answer_callback(call.id)
    bot.send_message(call.message.chat.id, f"ID for selected group: `{group_id}`", parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data == "admin_settings")
def settings_menu(call: telebot.types.CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        safe_answer_callback(call.id)
        return

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("⚙️ General Settings", callback_data="menu_general"),
        InlineKeyboardButton("🏆 Scoring Rules", callback_data="menu_scoring"),
        InlineKeyboardButton("❓ Bonus Questions", callback_data="menu_bonus"),
        InlineKeyboardButton("⬅️ Back", callback_data="admin_back"),
    )

    try:
        bot.edit_message_text(
            "⚙️ **Settings Categories**",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown",
        )
    except ApiTelegramException as exc:
        if "message is not modified" not in str(exc):
            raise
    safe_answer_callback(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("menu_"))
def handle_midway_menu(call: telebot.types.CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        safe_answer_callback(call.id)
        return

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    settings_map = dict(cursor.fetchall())
    conn.close()

    markup = InlineKeyboardMarkup(row_width=1)
    title = "⚙️ **Settings**"

    if call.data == "menu_general":
        markup.add(
            InlineKeyboardButton(
                f"TA Group: {settings_map.get('ta_group_id', '0')}",
                callback_data="set_ta_group",
            ),
            InlineKeyboardButton(
                f"Timezone: {settings_map.get('timezone', 'Asia/Tehran')}",
                callback_data="set_timezone",
            ),
            InlineKeyboardButton(
                f"Sync Interval (s): {settings_map.get('sync_interval', '3600')}",
                callback_data="set_sync_interval",
            ),
        )
        title = "⚙️ **General Settings**"
    elif call.data == "menu_scoring":
        markup.add(
            InlineKeyboardButton(
                f"Bonus Points: {settings_map.get('bonus_points', '5')}",
                callback_data="set_bonus_points",
            ),
            InlineKeyboardButton(
                f"Text Points: {settings_map.get('points_text', '1')}",
                callback_data="set_points_text",
            ),
            InlineKeyboardButton(
                f"Photo Points: {settings_map.get('points_photo', '2')}",
                callback_data="set_points_photo",
            ),
            InlineKeyboardButton(
                f"File Points: {settings_map.get('points_file', '3')}",
                callback_data="set_points_file",
            ),
        )
        title = "🏆 **Scoring Rules**"
    elif call.data == "menu_bonus":
        markup.add(
            InlineKeyboardButton(
                f"Approval Limit: {settings_map.get('approval_limit', '5')}",
                callback_data="set_limit",
            ),
            InlineKeyboardButton(
                f"Forward Top (N): {settings_map.get('forward_limit', '3')}",
                callback_data="set_forward_limit",
            ),
            InlineKeyboardButton(
                f"Post Time: {settings_map.get('post_time', '14:00')}",
                callback_data="set_time",
            ),
        )
        title = "❓ **Bonus Questions Settings**"

    markup.add(InlineKeyboardButton("⬅️ Back to Settings", callback_data="admin_settings"))

    try:
        bot.edit_message_text(
            title,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown",
        )
    except ApiTelegramException:
        pass
    safe_answer_callback(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("set_"))
def handle_set_setting(call: telebot.types.CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        safe_answer_callback(call.id)
        return

    key_map = {
        "set_bonus_points": ("bonus_points", "Enter new points for bonus questions:"),
        "set_limit": ("approval_limit", "Enter max number of approvals (e.g. 5):"),
        "set_forward_limit": ("forward_limit", "Enter top forwards count (e.g. 3):"),
        "set_time": ("post_time", "Enter post time in HH:MM format (e.g. 14:00):"),
        "set_ta_group": ("ta_group_id", "Enter the TA group chat ID:"),
        "set_timezone": ("timezone", "Enter timezone (e.g. Asia/Tehran):"),
        "set_sync_interval": ("sync_interval", "Enter sync interval in seconds (e.g. 3600):"),
        "set_points_text": ("points_text", "Enter points for text messages:"),
        "set_points_photo": ("points_photo", "Enter points for photo messages:"),
        "set_points_file": ("points_file", "Enter points for file messages:"),
    }
    payload = key_map.get(call.data)
    if not payload:
        safe_answer_callback(call.id)
        return

    key, prompt = payload
    message = bot.send_message(call.message.chat.id, prompt)
    bot.register_next_step_handler(message, save_setting_step, key)
    safe_answer_callback(call.id)


def save_setting_step(message: telebot.types.Message, key: str) -> None:
    value = message.text.strip()
    validation_error = _validate_setting_value(key, value)
    if validation_error:
        prompt = bot.send_message(message.chat.id, f"❌ {validation_error}\nTry again:")
        bot.register_next_step_handler(prompt, save_setting_step, key)
        return

    set_setting(key, value)
    bot.reply_to(message, f"✅ `{key}` updated to `{value}`", parse_mode="Markdown")
    show_admin_panel(message)


@bot.callback_query_handler(func=lambda call: call.data == "admin_back")
def admin_back(call: telebot.types.CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        safe_answer_callback(call.id)
        return
    safe_answer_callback(call.id)
    show_admin_panel(call.message)


@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_callback(call: telebot.types.CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        safe_answer_callback(call.id)
        return

    if call.data == "admin_export":
        safe_answer_callback(call.id)
        handle_export_logic(call.message)
    elif call.data == "admin_sync":
        safe_answer_callback(call.id)
        handle_sync_logic(call.message)
    elif call.data == "admin_check_bonus":
        safe_answer_callback(call.id)
        check_bonus_posting()


def handle_sync_logic(message: telebot.types.Message) -> None:
    bot.send_message(message.chat.id, "⏳ Forcing Google Sheets sync...")

    def force_sync() -> None:
        if sync_to_google_sheets(force=True):
            bot.send_message(message.chat.id, "✅ Successfully synced to Google Sheets!")
        else:
            bot.send_message(message.chat.id, "❌ Sync failed. Check credentials and sheet settings.")

    threading.Thread(target=force_sync, daemon=True).start()


def handle_export_logic(message: telebot.types.Message) -> None:
    bot.send_message(message.chat.id, "⏳ Generating Excel report...")
    try:
        conn = get_connection()
        users_query = (
            "SELECT student_id, name, telegram_username, numeric_id, text_score, photo_score, "
            "file_score, bonus_score, total_score FROM users ORDER BY total_score DESC"
        )
        unknown_query = (
            "SELECT numeric_id, telegram_username, first_name, bonus_score, total_score "
            "FROM unknown_users ORDER BY total_score DESC"
        )
        users_df = pd.read_sql_query(users_query, conn)
        unknown_df = pd.read_sql_query(unknown_query, conn)
        conn.close()

        with pd.ExcelWriter(EXCEL_REPORT_PATH, engine="openpyxl") as writer:
            users_df.to_excel(writer, sheet_name="Students (SID)", index=False)
            unknown_df.to_excel(writer, sheet_name="Unknown Users", index=False)

        with EXCEL_REPORT_PATH.open("rb") as file_doc:
            bot.send_document(message.chat.id, file_doc, caption="📊 Latest ODE Activity Report")
    except Exception as exc:
        bot.send_message(message.chat.id, f"❌ Export Error: {exc}")


@bot.message_handler(commands=["set_bonus"], func=lambda message: message.reply_to_message is not None)
def set_bonus_handler(message: telebot.types.Message) -> None:
    ta_group_id = _get_int_setting("ta_group_id", 0)
    if message.chat.id != ta_group_id:
        return

    post_time = get_setting("post_time", "14:00") or "14:00"
    try:
        hour, minute = map(int, post_time.split(":"))
    except ValueError:
        bot.reply_to(message, "❌ Invalid time format. Use HH:MM.")
        return

    now = get_now()
    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now >= scheduled:
        scheduled += timedelta(days=1)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO bonus_questions (ta_chat_id, ta_message_id, scheduled_time) VALUES (?, ?, ?)",
        (message.chat.id, message.reply_to_message.message_id, scheduled.isoformat()),
    )
    conn.commit()
    conn.close()

    scheduled_text = to_persian_num(scheduled.strftime("%Y-%m-%d %H:%M"))
    bot.reply_to(
        message,
        f"✅ Bonus question scheduled for `{scheduled_text}`.",
        parse_mode="Markdown",
    )


def check_bonus_posting() -> None:
    now_iso = get_now().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, ta_chat_id, ta_message_id
        FROM bonus_questions
        WHERE status = 'pending' AND scheduled_time <= ?
        """,
        (now_iso,),
    )
    pending_questions = cursor.fetchall()

    for bonus_id, chat_id, message_id in pending_questions:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("ارسال پاسخ", callback_data=f"bonus_submit_{bonus_id}"))
        try:
            sent = bot.copy_message(ODE_GROUP_ID, chat_id, message_id, reply_markup=markup)
            cursor.execute(
                "UPDATE bonus_questions SET status = 'active', main_group_message_id = ? WHERE id = ?",
                (sent.message_id, bonus_id),
            )
        except Exception:
            continue

    conn.commit()
    conn.close()


@bot.callback_query_handler(func=lambda call: call.data.startswith("bonus_submit_"))
def bonus_submit_init(call: telebot.types.CallbackQuery) -> None:
    parts = call.data.split("_")
    if len(parts) != 3:
        safe_answer_callback(call.id)
        return
    bonus_id = parts[2]

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM bonus_questions WHERE id = ?", (bonus_id,))
    row = cursor.fetchone()
    conn.close()

    if not row or row[0] == "closed":
        try:
            bot.send_message(call.from_user.id, "❌ مهلت ارسال پاسخ برای این سوال به پایان رسیده است.")
        except ApiTelegramException:
            pass
        safe_answer_callback(call.id)
        return

    try:
        prompt = bot.send_message(
            call.from_user.id,
            "لطفاً پاسخ خود را به صورت یک پیام (متن، عکس یا فایل) ارسال کنید:",
        )
        bot.register_next_step_handler(prompt, process_bonus_submission, bonus_id)
        bot.answer_callback_query(call.id, "لطفاً پیوی ربات را چک کنید.", show_alert=True)
    except ApiTelegramException as exc:
        message = str(exc).lower()
        if "forbidden" in message or "chat not found" in message:
            bot.answer_callback_query(
                call.id,
                "❌ لطفاً ابتدا ربات را در پیام خصوصی استارت کنید.",
                show_alert=True,
            )
        else:
            bot.answer_callback_query(call.id, "خطایی رخ داد.", show_alert=True)


def process_bonus_submission(message: telebot.types.Message, bonus_id: str) -> None:
    ta_group_id = _get_int_setting("ta_group_id", 0)
    if not ta_group_id:
        bot.reply_to(message, "❌ گروه دستیاران آموزشی تنظیم نشده است. لطفاً به مدیر اطلاع دهید.")
        return

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM bonus_questions WHERE id = ?", (bonus_id,))
    status_row = cursor.fetchone()
    if not status_row or status_row[0] == "closed":
        conn.close()
        bot.reply_to(message, "❌ این سوال بسته شده است و پاسخ جدید پذیرفته نمی‌شود.")
        return

    cursor.execute(
        "SELECT status FROM bonus_submissions WHERE bonus_id = ? AND student_id = ?",
        (bonus_id, message.from_user.id),
    )
    existing = cursor.fetchone()
    if existing:
        conn.close()
        bot.reply_to(message, "⚠️ شما قبلاً پاسخ این سوال را ارسال کرده‌اید.")
        return

    username = f"@{message.from_user.username}" if message.from_user.username else "no-username"
    student_name = f"{message.from_user.first_name} ({username})"

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ تایید", callback_data=f"ta_appr_{bonus_id}_{message.from_user.id}"))

    forwarded = bot.forward_message(ta_group_id, message.chat.id, message.message_id)
    bot.send_message(
        ta_group_id,
        f"📥 Submission from: {student_name}",
        reply_markup=markup,
        reply_to_message_id=forwarded.message_id,
    )

    cursor.execute(
        """
        INSERT INTO bonus_submissions (bonus_id, student_id, student_name, message_id, original_message_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (bonus_id, message.from_user.id, student_name, forwarded.message_id, message.message_id),
    )
    conn.commit()
    conn.close()

    bot.reply_to(message, "✅ پاسخ شما برای اساتید ارسال شد. در صورت تایید امتیاز دریافت خواهید کرد.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("ta_appr_"))
def ta_approve(call: telebot.types.CallbackQuery) -> None:
    parts = call.data.split("_")
    if len(parts) != 4:
        safe_answer_callback(call.id)
        return

    ta_group_id = _get_int_setting("ta_group_id", 0)
    if call.message.chat.id != ta_group_id:
        safe_answer_callback(call.id)
        return

    bonus_id = parts[2]
    student_id = parts[3]

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status FROM bonus_submissions WHERE bonus_id = ? AND student_id = ?",
        (bonus_id, student_id),
    )
    submission_row = cursor.fetchone()

    if not submission_row:
        conn.close()
        safe_answer_callback(call.id)
        return

    if submission_row[0] == "approved":
        conn.close()
        safe_answer_callback(call.id)
        return

    limit = _get_int_setting("approval_limit", 5)
    cursor.execute(
        "SELECT COUNT(*) FROM bonus_submissions WHERE bonus_id = ? AND status = 'approved'",
        (bonus_id,),
    )
    approved_count = cursor.fetchone()[0]

    if approved_count >= limit:
        conn.close()
        safe_answer_callback(call.id)
        return

    order_num = approved_count + 1
    cursor.execute(
        """
        UPDATE bonus_submissions
        SET status = 'approved', order_num = ?
        WHERE bonus_id = ? AND student_id = ?
        """,
        (order_num, bonus_id, student_id),
    )
    conn.commit()

    points = _get_int_setting("bonus_points", 5)
    cursor.execute(
        """
        SELECT username, first_name
        FROM (
            SELECT telegram_username AS username, name AS first_name FROM users WHERE numeric_id = ?
            UNION
            SELECT telegram_username, first_name FROM unknown_users WHERE numeric_id = ?
        )
        """,
        (student_id, student_id),
    )
    user_row = cursor.fetchone()
    username = user_row[0] if user_row else ""
    first_name = user_row[1] if user_row else "Unknown"
    conn.close()

    add_points(username, int(student_id), first_name, "bonus", custom_points=points)
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except ApiTelegramException:
        pass
    bot.send_message(
        call.message.chat.id,
        f"✅ Approved #{to_persian_num(order_num)}: {first_name}",
    )

    if order_num >= limit:
        finish_bonus(bonus_id)
    safe_answer_callback(call.id)


def finish_bonus(bonus_id: str) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE bonus_questions SET status = 'closed' WHERE id = ?", (bonus_id,))

    forward_limit = _get_int_setting("forward_limit", 3)
    cursor.execute(
        """
        SELECT COALESCE(u.name, s.student_name) AS display_name, s.student_id, s.original_message_id
        FROM bonus_submissions s
        LEFT JOIN users u ON s.student_id = u.numeric_id
        WHERE s.bonus_id = ? AND s.status = 'approved'
        ORDER BY s.order_num ASC
        LIMIT ?
        """,
        (bonus_id, forward_limit),
    )
    winners = cursor.fetchall()
    conn.commit()
    conn.close()

    if not winners:
        bot.send_message(ODE_GROUP_ID, "🎯 چالش به پایان رسید اما پاسخی تایید نشد.")
        return

    winners_text = "🎯 چالش به پایان رسید!\n\nنفرات برتر که پاسخ صحیح ارسال کردند:\n"
    for index, (name, _, _) in enumerate(winners, start=1):
        winners_text += f"{to_persian_num(index)}. {name}\n"
    bot.send_message(ODE_GROUP_ID, winners_text)

    bot.send_message(ODE_GROUP_ID, f"👇 {to_persian_num(len(winners))} پاسخ برتر جهت بررسی:")
    for name, student_id, original_message_id in winners:
        try:
            bot.copy_message(
                ODE_GROUP_ID,
                student_id,
                original_message_id,
                caption=f"👤 پاسخ ارسالی توسط: {name}",
            )
        except Exception:
            continue


@bot.message_handler(
    func=lambda message: message.text == "📊 مشاهده امتیاز من" and message.chat.type == "private"
)
def show_score_farsi(message: telebot.types.Message) -> None:
    user_data, status = get_user_score(message.from_user.id)
    if status == "known" and user_data:
        name, score, bonus = user_data
        bot.reply_to(
            message,
            (
                f"👤 **دانشجو:** {name}\n"
                f"🏆 **امتیاز کل:** {to_persian_num(score)} امتیاز\n"
                f"🏅 **امتیاز تمرین:** {to_persian_num(bonus)} امتیاز"
            ),
            parse_mode="Markdown",
        )
    elif status == "unknown" and user_data:
        name, score, bonus = user_data
        bot.reply_to(
            message,
            (
                f"👤 **کاربر (ناشناس):** {name}\n"
                f"🏆 **امتیاز کل:** {to_persian_num(score)} امتیاز\n"
                f"🏅 **امتیاز تمرین:** {to_persian_num(bonus)} امتیاز\n\n"
                "⚠️ حساب شما به لیست دانشجویان کلاس متصل نشده است."
            ),
            parse_mode="Markdown",
        )
    else:
        bot.reply_to(message, "❌ شما هنوز در لیست ثبت نشده‌اید یا امتیازی کسب نکرده‌اید.")


@bot.message_handler(
    content_types=["text", "photo", "document", "video", "voice", "audio"],
    func=lambda message: message.chat.type in ["group", "supergroup"],
)
def track_activity(message: telebot.types.Message) -> None:
    global LAST_HEARTBEAT

    track_group(message.chat.id, message.chat.title or "")

    if message.chat.id == ODE_GROUP_ID:
        now = time.time()
        if now - LAST_HEARTBEAT > 120 and HEARTBEAT_LOCK.acquire(blocking=False):
            LAST_HEARTBEAT = now

            def background_tasks() -> None:
                try:
                    check_bonus_posting()
                    sync_to_google_sheets()
                finally:
                    HEARTBEAT_LOCK.release()

            threading.Thread(target=background_tasks, daemon=True).start()

    if message.from_user.id == ADMIN_ID:
        return

    if message.chat.id != ODE_GROUP_ID:
        return

    content_type = message.content_type
    if content_type in ["document", "video", "voice", "audio"]:
        add_points(message.from_user.username, message.from_user.id, message.from_user.first_name, "file")
    elif content_type == "photo":
        add_points(message.from_user.username, message.from_user.id, message.from_user.first_name, "photo")
    elif content_type == "text":
        clean_text = re.sub(r"[^\w\s]", "", message.text or "").strip().lower()
        if (len(clean_text) > 2 and clean_text not in STOP_WORDS) or clean_text.isdigit():
            add_points(message.from_user.username, message.from_user.id, message.from_user.first_name, "text")
