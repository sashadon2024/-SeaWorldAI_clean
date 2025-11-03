import os
import logging
import asyncio
from typing import Optional, Dict

import openai
import requests
import feedparser

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------- LOGS ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------- CONFIG (env vars) ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_KEY")
OWM_KEY = os.getenv("OWM_KEY")  # optional (OpenWeatherMap)
NEWS_RSS = os.getenv("NEWS_RSS")  # optional: comma-separated RSS feeds

if not BOT_TOKEN or not OPENAI_KEY:
    raise RuntimeError("Required environment variables BOT_TOKEN and OPENAI_KEY are not set")

openai.api_key = OPENAI_KEY

# ---------- In-memory user prefs (simple) ----------
# For production consider persistent DB. For now - lightweight dict.
user_lang: Dict[int, str] = {}  # maps user_id -> 'ua'|'en'|'ru'

# ---------- Helpers ----------
def get_lang(uid: int) -> str:
    return user_lang.get(uid, "en")  # default EN

def tr(uid: int, ua: str, en: str, ru: str) -> str:
    lang = get_lang(uid)
    if lang == "ua":
        return ua
    if lang == "ru":
        return ru
    return en

async def safe_openai_chat(prompt: str, model="gpt-3.5-turbo", max_tokens=500, temperature=0.5) -> str:
    try:
        # Using ChatCompletion.create (v1.x openai)
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            n=1,
            timeout=30,
        )
        text = resp["choices"][0]["message"]["content"].strip()
        return text
    except Exception as e:
        logger.exception("OpenAI error")
        return None

# ---------- Commands ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("/news"), KeyboardButton("/jobs")], [KeyboardButton("/lang en"), KeyboardButton("/lang ua"), KeyboardButton("/lang ru")]],
        resize_keyboard=True,
    )
    await update.message.reply_text(
        tr(uid,
           "👋 Ласкаво! Я — SeaWorld AI Assistant 🌊\nНапиши питання або використовуй команди (/help).",
           "👋 Welcome! I’m SeaWorld AI Assistant 🌊\nType a question or use commands (/help).",
           "👋 Привет! Я — SeaWorld AI Assistant 🌊\nЗадай вопрос или используй команды (/help)."
        ),
        reply_markup=kb,
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = tr(
        uid,
        "Доступні команди:\n/start /help /lang <en|ua|ru>\n/news /jobs /cv <коротко>\n/weather <місто> (опц.)\nАбо просто напиши питання.",
        "Available commands:\n/start /help /lang <en|ua|ru>\n/news /jobs /cv <short info>\n/weather <city> (opt.)\nOr just send a question.",
        "Доступные команды:\n/start /help /lang <en|ua|ru>\n/news /jobs /cv <коротко>\n/weather <город> (опц.)\nИли просто напиши вопрос."
    )
    await update.message.reply_text(text)

async def lang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /lang <en|ua|ru>")
        return
    code = context.args[0].lower()
    if code not in ("en", "ua", "ru"):
        await update.message.reply_text("Allowed: en, ua, ru")
        return
    user_lang[uid] = code
    await update.message.reply_text(tr(uid, "Мова встановлена: Українська" if code=="ua" else "", 
                                          "Language set: English" if code=="en" else "",
                                          "Язык установлен: Русский" if code=="ru" else ""))

# NEWS: read RSS / NEWS_RSS env or reply that it's not configured
async def news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not NEWS_RSS:
        await update.message.reply_text(tr(uid,
                                          "RSS для новин не налаштовано.",
                                          "News RSS not configured.",
                                          "RSS для новостей не настроено."))
        return
    feeds = [f.strip() for f in NEWS_RSS.split(",") if f.strip()]
    items = []
    for feed in feeds:
        try:
            d = feedparser.parse(feed)
            for e in d.entries[:3]:
                items.append(f"• {e.get('title','No title')} — {e.get('link','')}")
        except Exception:
            logger.exception("RSS parse error for %s", feed)
    if not items:
        await update.message.reply_text(tr(uid, "Не знайдено новин.", "No news found.", "Новостей не найдено."))
        return
    await update.message.reply_text("\n".join(items[:10]))

# JOBS: show curated resources
async def jobs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = tr(uid,
             "Вакансії та ресурси:\n• t.me/SeaWorldJobs\n• www.findacrew.net\n• www.marinejobs.com\n• LinkedIn — морські ролі",
             "Jobs & resources:\n• t.me/SeaWorldJobs\n• www.findacrew.net\n• www.marinejobs.com\n• LinkedIn - maritime jobs",
             "Вакансии и ресурсы:\n• t.me/SeaWorldJobs\n• www.findacrew.net\n• www.marinejobs.com\n• LinkedIn - морские вакансии")
    await update.message.reply_text(txt)

# CV generator
async def cv_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text(tr(uid,
                                          "📄 Використання: /cv <коротко про тебе>. Наприклад: /cv Deckhand, 3 years on 24m yachts, skills: docking, engine checks",
                                          "📄 Usage: /cv <short info about you>. Eg: /cv Deckhand, 3 years on 24m yachts, skills: docking, engine checks",
                                          "📄 Использование: /cv <коротко о себе>. Пример: /cv Deckhand, 3 года на 24м яхтах, навыки: швартовка, проверка двигателей"))
        return
    user_text = " ".join(context.args)
    prompt = tr(uid,
                f"Створи коротке професійне CV моряка на основі: {user_text}. Формат: Ім'я, посада, досвід, навички, сертифікати, контакти. Текст українською.",
                f"Create a short professional seafarer CV based on: {user_text}. Format: Name, position, experience, skills, certificates, contacts. English.",
                f"Создай короткое профессиональное резюме моряка на основе: {user_text}. Формат: Имя, должность, опыт, навыки, сертификаты, контакты. Русский."
               )
    await update.message.reply_text(tr(uid, "Генерую CV... ⛳", "Generating CV... ⛳", "Генерирую CV... ⛳"))
    result = await asyncio.get_event_loop().run_in_executor(None, lambda: safe_openai_chat(prompt, model="gpt-3.5-turbo", max_tokens=600))
    if not result:
        await update.message.reply_text(tr(uid, "⛔ Помилка. Спробуйте пізніше.", "⛔ Error. Try later.", "⛔ Ошибка. Попробуйте позже."))
        return
    await update.message.reply_text(result)

# Weather
async def weather_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not OWM_KEY:
        await update.message.reply_text(tr(uid, "Погода не налаштована (OWM_KEY).", "Weather not configured (OWM_KEY).", "Погода не настроена (OWM_KEY)."))
        return
    if not context.args:
        await update.message.reply_text(tr(uid, "Використання: /weather <місто>", "Usage: /weather <city>", "Использование: /weather <город>"))
        return
    city = " ".join(context.args)
    try:
        r = requests.get("http://api.openweathermap.org/data/2.5/weather", params={"q": city, "appid": OWM_KEY, "units": "metric", "lang": get_lang(uid)})
        data = r.json()
        if r.status_code != 200:
            await update.message.reply_text(tr(uid, "Місто не знайдено.", "City not found.", "Город не найден."))
            return
        desc = data["weather"][0]["description"].capitalize()
        temp = data["main"]["temp"]
        feels = data["main"].get("feels_like")
        text = tr(uid,
                  f"Погода в {city}: {desc}. Темп.: {temp}°C. Відчувається як {feels}°C.",
                  f"Weather in {city}: {desc}. Temp: {temp}°C. Feels like {feels}°C.",
                  f"Погода в {city}: {desc}. Темп.: {temp}°C. Ощущается как {feels}°C.")
        await update.message.reply_text(text)
    except Exception:
        logger.exception("Weather error")
        await update.message.reply_text(tr(uid, "⛔ Помилка погоди.", "⛔ Weather error.", "⛔ Ошибка погоды."))

# Free chat handler — makes bot "live"
async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_text = update.message.text.strip()
    if not user_text:
        return
    # Short circuit: if user asks simple help-like things, avoid calling OpenAI
    low = user_text.lower()
    if len(low) < 4 and low in ("hi","hello","привіт","hello!"):
        await update.message.reply_text(tr(uid, "Привіт! Як можу допомогти?", "Hello! How can I help?", "Привет! Чем помочь?"))
        return

    # Compose prompt with persona
    persona = tr(uid,
                 "Ти — дружній та професійний морський асистент. Відповідай коротко і практично, додавай приклади і посилання, якщо потрібно.",
                 "You are a friendly professional maritime assistant. Answer concisely and practically, give examples and useful tips.",
                 "Ты — дружелюбный профессиональный морской помощник. Отвечай кратко и по делу, добавляй примеры и советы.")
    prompt = f"{persona}\n\nUser: {user_text}\n\nAnswer:"
    await update.message.chat.send_action(action="typing")
    result = await asyncio.get_event_loop().run_in_executor(None, lambda: safe_openai_chat(prompt, model="gpt-3.5-turbo", max_tokens=400, temperature=0.6))
    if not result:
        await update.message.reply_text(tr(uid, "⛔ Помилка. Спробуйте пізніше.", "⛔ Error. Try later.", "⛔ Ошибка. Попробуйте позже."))
        return
    await update.message.reply_text(result)

# Small utility commands: /idea, /tip, /fact
async def idea_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    prompt = tr(uid,
                "Запропонуй цікаву і безпечну 5-денну яхт-мандрівку для початківця у Середземному морі (маршрут, зупинки, поради).",
                "Suggest a fun and safe 5-day yacht trip for a beginner in the Mediterranean (route, stops, tips).",
                "Предложи интересное и безопасное 5-дневное яхт-путешествие для новичка в Средиземном море (маршрут, остановки, советы)."
               )
    await update.message.reply_text(tr(uid, "Генерую ідею...", "Generating idea...", "Генерирую идею..."))
    res = await asyncio.get_event_loop().run_in_executor(None, lambda: safe_openai_chat(prompt, max_tokens=400))
    if not res:
        await update.message.reply_text(tr(uid, "⛔ Помилка. Спробуйте пізніше.", "⛔ Error. Try later.", "⛔ Ошибка. Попробуйте позже."))
        return
    await update.message.reply_text(res)

async def tip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    prompt = tr(uid,
                "Дай 5 практичних порад з обслуговування яхти перед сезоном (коротко).",
                "Give 5 practical tips for yacht maintenance before the season (short).",
                "Дай 5 практических советов по обслуживанию яхты перед сезоном (кратко)."
               )
    res = await asyncio.get_event_loop().run_in_executor(None, lambda: safe_openai_chat(prompt, max_tokens=300))
    if not res:
        await update.message.reply_text(tr(uid, "⛔ Помилка. Спробуйте пізніше.", "⛔ Error. Try later.", "⛔ Ошибка. Попробуйте позже."))
        return
    await update.message.reply_text(res)

async def fact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    prompt = tr(uid,
                "Поділися цікавим фактом про історію яхтингу (1 абзац).",
                "Share an interesting fact about yachting history (1 paragraph).",
                "Поделись интересным фактом об истории яхтинга (1 абзац)."
               )
    res = await asyncio.get_event_loop().run_in_executor(None, lambda: safe_openai_chat(prompt, max_tokens=180))
    if not res:
        await update.message.reply_text(tr(uid, "⛔ Помилка. Спробуйте пізніше.", "⛔ Error. Try later.", "⛔ Ошибка. Попробуйте позже."))
        return
    await update.message.reply_text(res)

# ---------- Main ----------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("lang", lang_cmd))
    app.add_handler(CommandHandler("news", news_cmd))
    app.add_handler(CommandHandler("jobs", jobs_cmd))
    app.add_handler(CommandHandler("cv", cv_cmd))
    app.add_handler(CommandHandler("weather", weather_cmd))
    app.add_handler(CommandHandler("idea", idea_cmd))
    app.add_handler(CommandHandler("tip", tip_cmd))
    app.add_handler(CommandHandler("fact", fact_cmd))

    # free chat (must be last, handles plain text)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))

    logger.info("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
