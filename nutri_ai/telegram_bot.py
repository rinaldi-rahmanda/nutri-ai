"""Telegram front end. Uses long polling, so it runs anywhere with internet
access: no public URL, webhook or server needed.
"""

import logging
from datetime import datetime

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from . import reports
from .analyzer import AnalysisError
from .config import Settings
from .service import MealService

log = logging.getLogger(__name__)

HELP = """\
Send me a photo of your food and I'll estimate its nutrition and log it.

Add a caption to say more, for example:
  "dinner for Sarah"
  "half of this, the rest is for later"
You can also just describe a meal in text: "2 fried eggs and a slice of toast".

Commands:
/today [person] - today's intake
/week [person] - last 7 days, with daily and per-mealtime averages
/undo - remove the last meal logged from this chat
"""


def build_application(settings: Settings, service: MealService) -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()
    last_meal_id: dict[int, str] = {}  # chat id -> last logged meal, for /undo

    # With ALLOWED_CHAT_IDS set, everyone else is ignored. Each photo costs
    # an AI call, so don't leave the bot open to strangers.
    allowed = filters.Chat(chat_id=list(settings.allowed_chat_ids)) if settings.allowed_chat_ids else filters.ALL

    def now() -> datetime:
        return datetime.now(settings.timezone)

    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(HELP + f"\nYour chat id: {update.effective_chat.id}")

    async def log_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message
        image, media_type = None, "image/jpeg"
        if message.photo:
            file = await message.photo[-1].get_file()  # last = highest resolution
            image = bytes(await file.download_as_bytearray())
        elif message.document:  # image sent "as file"
            file = await message.document.get_file()
            image = bytes(await file.download_as_bytearray())
            media_type = message.document.mime_type
        caption = message.caption or message.text or ""

        await message.chat.send_action(ChatAction.TYPING)
        try:
            eaten_at = message.date.astimezone(settings.timezone)
            meal = await service.log_meal(eaten_at, image, media_type, caption)
        except AnalysisError as e:
            await message.reply_text(str(e))
            return
        except Exception:
            log.exception("Failed to log meal")
            await message.reply_text("Something went wrong while logging that meal. Nothing was saved.")
            return

        if not meal.entries:
            await message.reply_text(meal.comment or "I couldn't find any food in that message.")
            return
        last_meal_id[message.chat_id] = meal.entries[0].meal_id
        await message.reply_text(reports.logged_meal(meal.entries, meal.comment))

    async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE, days: int) -> None:
        person = " ".join(context.args) or settings.default_user
        try:
            entries = await service.entries_for_days(now(), days, person)
        except Exception:
            log.exception("Failed to read meals")
            await update.message.reply_text("Couldn't read the meal log. Check the bot's logs.")
            return
        text = reports.day_summary(entries, person) if days == 1 else reports.period_summary(entries, person, days)
        await update.message.reply_text(text)

    async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await summary(update, context, days=1)

    async def week_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await summary(update, context, days=7)

    async def undo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        meal_id = last_meal_id.pop(update.effective_chat.id, None)
        if not meal_id:
            await update.message.reply_text("Nothing to undo. (I only remember the last meal since I was started.)")
            return
        try:
            deleted = await service.delete_meal(meal_id)
        except Exception:
            log.exception("Failed to delete meal")
            last_meal_id[update.effective_chat.id] = meal_id
            await update.message.reply_text("Couldn't remove that meal. Check the bot's logs.")
            return
        await update.message.reply_text(f"Removed the last meal ({deleted} items).")

    app.add_handler(CommandHandler(["start", "help"], help_command))  # open to all: shows the chat id
    app.add_handler(CommandHandler("today", today_command, filters=allowed))
    app.add_handler(CommandHandler("week", week_command, filters=allowed))
    app.add_handler(CommandHandler("undo", undo_command, filters=allowed))
    food_message = filters.PHOTO | filters.Document.IMAGE | (filters.TEXT & ~filters.COMMAND)
    app.add_handler(MessageHandler(allowed & food_message, log_message))
    return app
