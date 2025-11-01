import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import openai

# Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Keys
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_KEY")

if not BOT_TOKEN or not OPENAI_KEY:
    raise RuntimeError("Required environment variables BOT_TOKEN and OPENAI_KEY are not set")

openai.api_key = OPENAI_KEY

# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Вітаю! Я — SeaWorld AI Assistant 🌊\n"
        "Питай про яхти, море, роботу на флоті або технічні поради."
    )

# Messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": user_text}],
            max_tokens=700,
            temperature=0.2,
        )
        answer = response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.exception("OpenAI error")
        answer = "⛔ Вибач, зараз я недоступний. Спробуй пізніше."

    await update.message.reply_text(answer)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
