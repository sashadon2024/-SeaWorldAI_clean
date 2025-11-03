import os
import logging
import feedparser
import requests
from typing import Dict
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from openai import OpenAI  # ✅ новий правильний імпорт

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Keys
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_KEY")

if not BOT_TOKEN or not OPENAI_KEY:
    raise RuntimeError("❌ Required environment variables BOT_TOKEN and OPENAI_KEY are not set")

# ✅ новий формат для роботи з OpenAI
client = OpenAI(api_key=OPENAI_KEY)

# Per-user language preference (in-memory). Keys are telegram user_id -> 'en'|'ua'|'ru'
user_lang: Dict[int, str] = {}

# Helper: get language for user
def get_lang_for_user(user_id: int) -> str:
    return user_lang.get(user_id, "en")  # default English

# Multi-language texts
START_TEXT = {
    "en": "👋 Welcome! I'm SeaWorld AI Assistant 🌊\nAsk about yachting, merchant fleet work, or technical tips.",
    "ua": "👋 Вітаю! Я — SeaWorld AI Assistant 🌊\nПитай про яхтинг, роботу на флоті чи технічні поради.",
    "ru": "👋 Привет! Я — SeaWorld AI Assistant 🌊\nСпрашивай про яхтинг, работу на флоте или технические советы.",
}

HELP_TEXT = {
    "en": (
        "Commands:\n"
        "/start - welcome\n"
        "/help - this message\n"
        "/lang <en|ua|ru> - set language\n"
        "/news - latest yachting/fleet news (from RSS)\n"
        "/jobs - useful job sites and channels\n"
        "/cv <brief info> - generate professional CV from your short input\n"
        "/weather <City> - current weather (if OWM_KEY configured)\n\n"
        "Example: /cv I'm a deckhand with 3 years experience on 30m yachts."
    ),
    "ua": (
        "Команди:\n"
        "/start - привітання\n"
        "/help - ця підказка\n"
        "/lang <en|ua|ru> - обрати мову\n"
        "/news - останні новини (RSS)\n"
        "/jobs - корисні сайти та канали з вакансіями\n"
        "/cv <коротко> - згенерувати професійне CV\n"
        "/weather <Місто> - погода (якщо налаштовано OWM_KEY)\n\n"
        "Приклад: /cv Я матрос з 3 роками досвіду на 30м яхтах."
    ),
    "ru": (
        "Команды:\n"
        "/start - приветствие\n"
        "/help - это подсказка\n"
        "/lang <en|ua|ru> - выбрать язык\n"
        "/news - последние новости (RSS)\n"
        "/jobs - полезные сайты и каналы с вакансиями\n"
        "/cv <кратко> - сгенерировать профессиональное CV\n"
        "/weather <Город> - погода (если настроен OWM_KEY)\n\n"
        "Пример: /cv Я матрос с 3 годами опыта на 30м яхтах."
    ),
}

# JOBS: hardcoded starter list (you can expand)
JOBS_TEXT = {
    "en": (
        "Job resources (starter):\n"
        "- SeaWorld Jobs group: t.me/SeaWorldJobs\n"
        "- Crewseekers: https://www.crewseekers.net\n"
        "- Find a Crew: https://www.findacrew.net\n"
        "- YPI Crew: https://www.ypi-crew.com\n\n"
        "Tip: check company websites and major crewing agencies."
    ),
    "ua": (
        "Ресурси вакансій (старт):\n"
        "- SeaWorld Jobs: t.me/SeaWorldJobs\n"
        "- Crewseekers: https://www.crewseekers.net\n"
        "- Find a Crew: https://www.findacrew.net\n"
        "- YPI Crew: https://www.ypi-crew.com\n\n"
        "Порада: перевіряйте сайти компаній та великі крюінгові агенції."
    ),
    "ru": (
        "Ресурсы вакансий (старт):\n"
        "- SeaWorld Jobs: t.me/SeaWorldJobs\n"
        "- Crewseekers: https://www.crewseekers.net\n"
        "- Find a Crew: https://www.findacrew.net\n"
        "- YPI Crew: https://www.ypi-crew.com\n\n"
        "Совет: проверяйте сайты компаний и крупные крюинговые агентства."
    ),
}

# --- Command handlers ---


from openai import OpenAI

client = OpenAI(api_key=OPENAI_KEY)

# --- CV generation ---
async def cv_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🧾 Використання:\n"
            "/cv <коротка інформація>\n\n"
            "Приклад:\n"
            "/cv Матрос, 3 роки досвіду на 30м яхтах, навички: швартування, двигуни"
        )
        return

    user_input = " ".join(context.args)
    user_lang = context.user_data.get("lang", "ua")

    system_prompts = {
        "ua": "Ти помічник із морського флоту. Створи коротке професійне CV українською для резюме моряка.",
        "en": "You are a maritime assistant. Create a short professional CV in English for a seafarer resume.",
        "ru": "Ты морской помощник. Составь краткое профессиональное резюме на русском для моряка.",
    }

    try:
        response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": user_text}],
    max_tokens=700,
    temperature=0.3,
)
answer = response.choices[0].message.content.strip()
        await update.message.reply_text(f"📄 Твоє CV:\n\n{answer}")

    except Exception as e:
        logging.error(f"Помилка при створенні CV: {e}")
        await update.message.reply_text("⛔ Вибач, зараз я недоступний. Спробуй пізніше.")


# /news: fetch RSS feeds from NEWS_RSS env
async def news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang_for_user(update.effective_user.id)
    if not NEWS_RSS:
        texts = {
            "en": "No RSS feeds configured. Please ask admin to add NEWS_RSS.",
            "ua": "RSS стрічки не налаштовані. Попросіть адміністратора додати NEWS_RSS.",
            "ru": "RSS ленты не настроены. Попросите администратора добавить NEWS_RSS.",
        }
        await update.message.reply_text(texts.get(lang))
        return

    feeds = [u.strip() for u in NEWS_RSS.split(",") if u.strip()]
    messages = []
    max_items = 3
    try:
        for feed_url in feeds:
            d = feedparser.parse(feed_url)
            if d.bozo:
                continue
            title = d.feed.get("title", feed_url)
            messages.append(f"🔹 {title}")
            count = 0
            for e in d.entries:
                if count >= max_items:
                    break
                link = e.get("link", "")
                entry_title = e.get("title", "No title")
                messages.append(f"• {entry_title}\n{link}")
                count += 1
    except Exception as e:
        logger.exception("Error fetching RSS")
        await update.message.reply_text("Error reading RSS feeds.")
        return

    if not messages:
        await update.message.reply_text("No news found.")
    else:
        # send in chunks if long
        chunk = "\n\n".join(messages[:30])
        await update.message.reply_text(chunk)


# /weather City
async def weather_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang_for_user(update.effective_user.id)
    texts = {
        "en": "Usage: /weather <City> (requires OWM_KEY configured)",
        "ua": "Використання: /weather <Місто> (потрібен OWM_KEY)",
        "ru": "Использование: /weather <Город> (требуется OWM_KEY)",
    }
    if not OWM_KEY:
        await update.message.reply_text(texts.get(lang))
        return
    args = context.args
    if not args:
        await update.message.reply_text(texts.get(lang))
        return
    city = " ".join(args)
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": OWM_KEY, "units": "metric", "lang": "en"}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        weather = data["weather"][0]["description"].capitalize()
        temp = data["main"]["temp"]
        feels = data["main"].get("feels_like")
        wind = data["wind"].get("speed")
        reply = f"Weather in {city}:\n{weather}\nTemp: {temp}°C\nFeels like: {feels}°C\nWind: {wind} m/s"
        await update.message.reply_text(reply)
    except Exception as e:
        logger.exception("Weather error")
        await update.message.reply_text("Could not fetch weather. Check city name or OWM_KEY.")


# /cv <short info> -> generate CV with OpenAI
async def cv_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = get_lang_for_user(uid)
    args = context.args
    if not args:
        texts = {
            "en": "Usage: /cv <brief info>. Example: /cv Deckhand, 3 years on 30m yachts, skills: lines, engine checks",
            "ua": "Використання: /cv <коротка інформація>. Приклад: /cv Матрос, 3 роки на 30м яхтах, навички: швартування, огляд двигуна",
            "ru": "Использование: /cv <краткая информация>. Пример: /cv Матрос, 3 года на 30м яхтах, навыки: швартовка, осмотр двигателя",
        }
        await update.message.reply_text(texts.get(lang))
        return

    short_info = " ".join(args)
    # Build prompt respecting language
    prompt_map = {
        "en": f"Convert the following short resume info into a professional English CV/resume suitable for yacht/crew applications:\n\n{short_info}\n\nInclude: brief profile, skills, experience (bullets), certifications (if any), contact placeholder.",
        "ua": f"Перетвори коротку інформацію у професійне CV українською для вакансії на яхті/флоті:\n\n{short_info}\n\nДодай: профіль, навички, досвід (маркерні список), сертифікати (якщо є), контакти (заповнити).",
        "ru": f"Преобразуй краткую информацию в профессиональное CV на русском языке для яхтинга/флота:\n\n{short_info}\n\nВключи: профиль, навыки, опыт (пункты), сертификаты (если есть), контакты (заполнить).",
    }
    prompt = prompt_map.get(lang, prompt_map["en"])
    await update.message.reply_text("⏳ Generating CV...")

    try:
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.2,
        )
        answer = resp.choices[0].message.content.strip()
        await update.message.reply_text(answer)
    except Exception as e:
        logger.exception("OpenAI CV error")
        await update.message.reply_text("⛔ Sorry, currently unavailable. Try later.")


# Generic message handler: pass user text to OpenAI (short Q&A)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = get_lang_for_user(uid)
    user_text = update.message.text.strip()
    # short help when user writes 'help' words
    lower = user_text.lower()
    if lower in ("help", "поміч", "довідка", "хелп", "помощь"):
        await help_cmd(update, context)
        return

    system_prompt = {
        "en": "You are a helpful assistant for yachting and merchant fleet professionals. Be concise and practical.",
        "ua": "Ти корисний асистент для професіоналів яхтингу та торгового флоту. Відповідай практично й лаконічно.",
        "ru": "Вы — полезный ассистент для профессионалов яхтинга и торгового флота. Отвечайте практично и кратко.",
    }

    try:
        messages = [
            {"role": "system", "content": system_prompt.get(lang, system_prompt["en"])},
            {"role": "user", "content": user_text},
        ]
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=700,
            temperature=0.2,
        )
        answer = resp.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("OpenAI error")
        answer = {
            "en": "⛔ Sorry, I'm currently unavailable. Try again later.",
            "ua": "⛔ Вибач, зараз я недоступний. Спробуй пізніше.",
            "ru": "⛔ Извините, сейчас я недоступен. Попробуйте позже.",
        }.get(lang, "Sorry, unavailable.")
    await update.message.reply_text(answer)


# Setup and run
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("lang", lang_cmd))
    app.add_handler(CommandHandler("jobs", jobs_cmd))
    app.add_handler(CommandHandler("news", news_cmd))
    app.add_handler(CommandHandler("weather", weather_cmd))
    app.add_handler(CommandHandler("cv", cv_cmd))

    # Generic messages (Q&A)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start polling
    logger.info("Starting SeaWorld AI Assistant...")
    app.run_polling()


if __name__ == "__main__":
    main()
