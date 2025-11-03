import os
import logging
import feedparser
import requests
from openai import OpenAI
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
)

# ---------- Logging ----------
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# ---------- Keys ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_KEY")
OWM_KEY = os.getenv("OWM_KEY")

if not BOT_TOKEN or not OPENAI_KEY:
    raise RuntimeError("❌ Missing BOT_TOKEN or OPENAI_KEY")

client = OpenAI(api_key=OPENAI_KEY)

# ---------- Global storage ----------
user_lang: dict = {}

# ---------- Texts ----------
TEXTS = {
    "ua": {
        "start": "👋 Вітаю! Я — SeaWorld AI Assistant 🌊\nТвій помічник у світі яхтингу та флоту!\n\nДоступні команди:\n/help — допомога\n/lang <ua|en|ru> — зміна мови\n/news — новини\n/jobs — вакансії\n/cv — створити CV\n/weather — погода\n/tip, /idea, /fact — поради, ідеї, факти 🌎",
        "help": "💡 Доступні команди:\n/start — початок\n/lang <ua|en|ru> — обрати мову\n/news — морські новини\n/jobs — сайти для пошуку роботи\n/cv <інфо> — створити професійне CV\n/weather <місто> — погода + Windy карта\n/tip — корисна порада\n/idea — ідея дня\n/fact — факт про море 🌊",
        "cv_usage": "📄 Використання: /cv <коротка інформація>.\nНапр.: /cv Матрос, 3 роки на яхтах 30м, швартування, огляд двигуна.",
        "cv_wait": "⛵ Генерую професійне CV...",
        "weather_usage": "🌤 Використання: /weather <місто>",
        "weather_error": "⚠️ Не вдалося отримати дані про погоду.",
        "jobs": "⚓ Найкращі сайти для пошуку роботи:\n• https://www.yotspot.com\n• https://www.crewseekers.net\n• https://www.superyachtcrewagency.com\n• https://www.allcruisejobs.com\n• https://www.vikingcrew.com",
    },
    "en": {
        "start": "👋 Welcome! I'm SeaWorld AI Assistant 🌊\nYour personal guide in yachting & fleet life.\n\nAvailable commands:\n/help — help\n/lang <ua|en|ru> — change language\n/news — news\n/jobs — jobs\n/cv — create CV\n/weather — weather\n/tip, /idea, /fact — advice & ideas 🌎",
        "help": "💡 Commands:\n/start — start\n/lang <ua|en|ru> — choose language\n/news — yachting news\n/jobs — job search links\n/cv <info> — create a CV\n/weather <city> — weather + Windy link\n/tip — useful tip\n/idea — daily idea\n/fact — sea fact 🌊",
        "cv_usage": "📄 Usage: /cv <short info>.\nExample: /cv Deckhand, 3 years on 30m yachts, mooring, engine checks.",
        "cv_wait": "⛵ Generating professional CV...",
        "weather_usage": "🌤 Usage: /weather <city>",
        "weather_error": "⚠️ Failed to fetch weather data.",
        "jobs": "⚓ Best sites for maritime jobs:\n• https://www.yotspot.com\n• https://www.crewseekers.net\n• https://www.superyachtcrewagency.com\n• https://www.allcruisejobs.com\n• https://www.vikingcrew.com",
    },
    "ru": {
        "start": "👋 Привет! Я — SeaWorld AI Assistant 🌊\nТвой помощник в мире яхтинга и флота!\n\nДоступные команды:\n/help — помощь\n/lang <ua|en|ru> — сменить язык\n/news — новости\n/jobs — вакансии\n/cv — создать резюме\n/weather — погода\n/tip, /idea, /fact — советы и факты 🌎",
        "help": "💡 Команды:\n/start — начало\n/lang <ua|en|ru> — выбрать язык\n/news — морские новости\n/jobs — сайты для поиска работы\n/cv <инфо> — создать CV\n/weather <город> — погода + Windy карта\n/tip — совет\n/idea — идея дня\n/fact — факт о море 🌊",
        "cv_usage": "📄 Использование: /cv <короткая информация>.\nПример: /cv Матрос, 3 года на яхтах 30м, швартовка, проверка двигателя.",
        "cv_wait": "⛵ Генерирую профессиональное резюме...",
        "weather_usage": "🌤 Использование: /weather <город>",
        "weather_error": "⚠️ Не удалось получить данные о погоде.",
        "jobs": "⚓ Лучшие сайты для поиска работы:\n• https://www.yotspot.com\n• https://www.crewseekers.net\n• https://www.superyachtcrewagency.com\n• https://www.allcruisejobs.com\n• https://www.vikingcrew.com",
    }
}

# ---------- Helpers ----------
def get_text(lang: str, key: str) -> str:
    return TEXTS.get(lang, TEXTS["en"]).get(key, "⚠️ Missing text")

# ---------- Commands ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_lang[update.effective_user.id] = "ua"
    lang = "ua"
    keyboard = [[KeyboardButton("/news"), KeyboardButton("/jobs")],
                [KeyboardButton("/lang ua"), KeyboardButton("/lang en"), KeyboardButton("/lang ru")]]
    await update.message.reply_text(get_text(lang, "start"), reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = user_lang.get(update.effective_user.id, "en")
    await update.message.reply_text(get_text(lang, "help"))

async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🌍 /lang ua | en | ru")
        return
    lang = context.args[0].lower()
    if lang not in ["ua", "en", "ru"]:
        await update.message.reply_text("❌ Unsupported language.")
        return
    user_lang[update.effective_user.id] = lang
    await update.message.reply_text(f"✅ Language set to {lang.upper()}")

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    feed = feedparser.parse("https://www.yachtingmonthly.com/feed")
    news = "\n\n".join([f"📰 {entry.title}\n{entry.link}" for entry in feed.entries[:5]])
    await update.message.reply_text(news or "⚠️ No news found.")

async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = user_lang.get(update.effective_user.id, "en")
    await update.message.reply_text(get_text(lang, "jobs"))

async def cv_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = user_lang.get(update.effective_user.id, "en")
    if not context.args:
        await update.message.reply_text(get_text(lang, "cv_usage"))
        return
    query = " ".join(context.args)
    await update.message.reply_text(get_text(lang, "cv_wait"))
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "Create a short, professional CV for a maritime or yachting professional."},
                      {"role": "user", "content": query}],
            max_tokens=400,
            temperature=0.6,
            timeout=30,
        )
        await update.message.reply_text(response.choices[0].message.content.strip())
    except Exception as e:
        await update.message.reply_text("⚠️ Error generating CV.")
        print(e)

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = user_lang.get(update.effective_user.id, "en")
    if not context.args:
        await update.message.reply_text(get_text(lang, "weather_usage"))
        return
    city = " ".join(context.args)
    windy_url = f"https://www.windy.com/?{city.replace(' ', '-')}"
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_KEY}&units=metric&lang={lang}"
        data = requests.get(url).json()
        if data.get("cod") != 200:
            raise ValueError()
        desc = data["weather"][0]["description"].capitalize()
        temp = data["main"]["temp"]
        msg = f"🌦 {city}: {temp}°C, {desc}\n🔗 [Windy map]({windy_url})"
        await update.message.reply_markdown(msg)
    except:
        await update.message.reply_text(get_text(lang, "weather_error"))

async def tip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ai_response(update, "Give a short useful tip for yacht maintenance or life onboard.")

async def idea_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ai_response(update, "Give an inspiring idea for sailors or travelers today.")

async def fact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ai_response(update, "Tell an interesting fact about the ocean or ships.")

async def ai_response(update, prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "SeaWorld AI Assistant, expert in yachts, fleet, and marine life."},
                      {"role": "user", "content": prompt}],
            max_tokens=300,
        )
        await update.message.reply_text(response.choices[0].message.content.strip())
    except Exception as e:
        await update.message.reply_text("⛔ Sorry, currently unavailable.")
        print(e)

# ---------- Main ----------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("lang", lang_command))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CommandHandler("jobs", jobs_command))
    app.add_handler(CommandHandler("cv", cv_command))
    app.add_handler(CommandHandler("weather", weather_command))
    app.add_handler(CommandHandler("tip", tip_command))
    app.add_handler(CommandHandler("idea", idea_command))
    app.add_handler(CommandHandler("fact", fact_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_response))
    app.run_polling()

if __name__ == "__main__":
    main()
