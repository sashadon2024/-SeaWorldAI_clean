import os
import logging
import feedparser
import requests
from typing import Dict
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
)
from openai import OpenAI

# 🔸 Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# 🔸 API Keys
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_KEY")
OWM_KEY = os.getenv("OWM_KEY")  # optional for /weather
NEWS_RSS = os.getenv("NEWS_RSS")  # optional fallback RSS feeds

if not BOT_TOKEN or not OPENAI_KEY:
    raise RuntimeError("❌ BOT_TOKEN or OPENAI_KEY not set in environment variables")

client = OpenAI(api_key=OPENAI_KEY)

# 🌍 Languages
LANGUAGES = {
    "ua": "🇺🇦 Українська",
    "en": "🇬🇧 English",
    "ru": "🇷🇺 Русский"
}
user_lang: Dict[int, str] = {}

def tr(user_id: int, ua: str, en: str, ru: str) -> str:
    lang = user_lang.get(user_id, "ua")
    return {"ua": ua, "en": en, "ru": ru}[lang]

# 🔹 Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_lang[update.effective_user.id] = "ua"
    await update.message.reply_text(
        "👋 Вітаю! Я — SeaWorld AI Assistant 🌊\n"
        "Питай про яхти, море, роботу на флоті або технічні поради.\n"
        "🌐 /lang — змінити мову"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(tr(uid,
        "🛟 Доступні команди:\n"
        "/start — почати\n"
        "/help — допомога\n"
        "/lang — змінити мову\n"
        "/news — останні новини яхтингу\n"
        "/jobs — вакансії для моряків\n"
        "/cv — створити професійне резюме\n"
        "/weather <місто> — погода (потрібен OWM_KEY)",
        "🛟 Available commands:\n"
        "/start — start\n"
        "/help — help\n"
        "/lang — change language\n"
        "/news — latest yachting news\n"
        "/jobs — seafarer jobs\n"
        "/cv — create professional CV\n"
        "/weather <city> — weather (needs OWM_KEY)",
        "🛟 Доступные команды:\n"
        "/start — начать\n"
        "/help — помощь\n"
        "/lang — сменить язык\n"
        "/news — последние новости яхтинга\n"
        "/jobs — вакансии моряков\n"
        "/cv — создать профессиональное резюме\n"
        "/weather <город> — погода (требуется OWM_KEY)"
    ))

async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "🌍 Оберіть мову / Choose language / Выберите язык:\n🇺🇦 UA | 🇬🇧 EN | 🇷🇺 RU"
    await update.message.reply_text(text)

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang_map = {"ua": "ua", "uk": "ua", "en": "en", "ru": "ru"}
    msg = update.message.text.lower().strip()
    if msg in lang_map:
        user_lang[uid] = lang_map[msg]
        await update.message.reply_text(tr(uid, "✅ Мову змінено!", "✅ Language changed!", "✅ Язык изменен!"))

# 🔹 /news
async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    feeds = [
        "https://www.yachtingworld.com/feed",
        "https://www.maritime-executive.com/rss",
    ]
    if NEWS_RSS:
        feeds += [f.strip() for f in NEWS_RSS.split(",")]

    news_items = []
    for f in feeds:
        feed = feedparser.parse(f)
        for e in feed.entries[:2]:
            news_items.append(f"📰 {e.title}\n{e.link}\n")

    await update.message.reply_text(
        tr(uid, "🌍 Останні новини:\n", "🌍 Latest news:\n", "🌍 Последние новости:\n") + "\n".join(news_items[:5])
    )

# 🔹 /jobs
async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    links = [
        "https://www.yacrew.com/",
        "https://www.marineresource.com/",
        "https://www.allcruisejobs.com/",
        "https://crew-center.com/jobs",
    ]
    await update.message.reply_text(tr(uid,
        "⚓ Вакансії для моряків:\n" + "\n".join(links),
        "⚓ Seafarer jobs:\n" + "\n".join(links),
        "⚓ Вакансии моряков:\n" + "\n".join(links)
    ))

# 🔹 /cv — AI створює резюме
async def cv_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text(tr(uid,
            "📄 Використання: /cv <коротко про себе>",
            "📄 Usage: /cv <short info about you>",
            "📄 Использование: /cv <коротко о себе>"
        ))
        return

    prompt = tr(uid,
        f"Створи коротке професійне CV моряка на основі: {' '.join(context.args)}",
        f"Create a short professional seafarer CV based on: {' '.join(context.args)}",
        f"Создай короткое профессиональное резюме моряка на основе: {' '.join(context.args)}"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.3,
        )
        answer = response.choices[0].message.content.strip()
    except Exception as e:
        logging.exception("OpenAI error")
        answer = tr(uid, "⛔ Помилка. Спробуйте пізніше.", "⛔ Error. Try later.", "⛔ Ошибка. Попробуйте позже.")

    await update.message.reply_text(answer)

# 🔹 /weather
async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not OWM_KEY:
        await update.message.reply_text(tr(uid,
            "⛔ Потрібен OWM_KEY для погоди.",
            "⛔ OWM_KEY required for weather.",
            "⛔ Требуется OWM_KEY для погоды."
        ))
        return
    if not context.args:
        await update.message.reply_text(tr(uid,
            "🌤 Використання: /weather <місто>",
            "🌤 Usage: /weather <city>",
            "🌤 Использование: /weather <город>"
        ))
        return
    city = " ".join(context.args)
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_KEY}&units=metric&lang=ua"
    try:
        res = requests.get(url).json()
        temp = res["main"]["temp"]
        desc = res["weather"][0]["description"]
        await update.message.reply_text(f"🌤 {city}: {temp}°C, {desc}")
    except Exception:
        await update.message.reply_text(tr(uid, "⛔ Місто не знайдено.", "⛔ City not found.", "⛔ Город не найден."))

# 🔹 Basic message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_text = update.message.text
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": user_text}],
            max_tokens=500,
            temperature=0.3,
        )
        answer = response.choices[0].message.content.strip()
    except Exception as e:
        logging.exception("OpenAI error")
        answer = tr(uid, "⛔ Вибач, зараз я недоступний. Спробуй пізніше.",
                    "⛔ Sorry, currently unavailable. Try later.",
                    "⛔ Извини, сейчас недоступен. Попробуй позже.")
    await update.message.reply_text(answer)

# 🔹 Main
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("lang", lang_command))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CommandHandler("jobs", jobs_command))
    app.add_handler(CommandHandler("cv", cv_command))
    app.add_handler(CommandHandler("weather", weather_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Regex("^(UA|EN|RU|ua|en|ru)$"), set_language))

    app.run_polling()

if __name__ == "__main__":
    main()
