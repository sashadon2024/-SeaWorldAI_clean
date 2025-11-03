#!/usr/bin/env python3
"""
SeaWorld AI Assistant - main.py
Single-file Telegram bot with:
- Multilanguage support (uk/en/ru)
- Commands: /start /help /about /news /jobs /weather /routes /tips /contact /language /ask /cv /subscribe
- /cv: interactive form -> generates PDF CV and sends to user
- /news, /jobs: fetch from RSS feeds (feedparser)
- AI answers via OpenAI API (ChatCompletion)
"""

import os
import logging
import asyncio
import tempfile
import feedparser
import requests
from fpdf import FPDF
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)
import openai

# ---------------------------
# Logging
# ---------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("SeaWorldAI")

# ---------------------------
# Environment / keys
# ---------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_KEY")
OWM_KEY = os.getenv("OWM_KEY")  # OpenWeatherMap (optional)
NEWS_RSS = os.getenv("NEWS_RSS", "")  # comma separated RSS list, optional
JOBS_RSS = os.getenv("JOBS_RSS", "")  # comma separated job feeds, optional

if not BOT_TOKEN or not OPENAI_KEY:
    raise RuntimeError("Required environment variables BOT_TOKEN and OPENAI_KEY are not set")

openai.api_key = OPENAI_KEY

# ---------------------------
# Simple in-memory storage
# ---------------------------
user_languages = {}           # user_id -> 'uk'/'en'/'ru'
subscribers = set()           # user ids for digest (simple in-memory; use DB for persistence)

# ---------------------------
# Multilanguage texts
# ---------------------------
texts = {
    "start": {
        "uk": "👋 Вітаю! Я — SeaWorld AI Assistant 🌊\nПитай про яхти, море, вакансії та технічні поради.",
        "en": "👋 Welcome! I'm SeaWorld AI Assistant 🌊\nAsk me about yachts, maritime jobs, maintenance and tips.",
        "ru": "👋 Привет! Я — SeaWorld AI Assistant 🌊\nСпроси про яхты, вакансии, обслуживание и советы."
    },
    "help": {
        "uk": "Команди:\n/start /help /about /news /jobs /weather [порт] /routes /tips /contact /language /ask (пиши питання) /cv",
        "en": "Commands:\n/start /help /about /news /jobs /weather [port] /routes /tips /contact /language /ask (just send a question) /cv",
        "ru": "Команды:\n/start /help /about /news /jobs /weather [порт] /routes /tips /contact /language /ask (пиши вопрос) /cv"
    },
    "about": {
        "uk": "🌊 SeaWorld Life — екосистема для моряків і яхтсменів. AI-помічник відповідає і допомагає генерувати CV та шукати вакансії.",
        "en": "🌊 SeaWorld Life — ecosystem for sailors and yachting pros. AI assistant answers questions, helps create CVs and find jobs.",
        "ru": "🌊 SeaWorld Life — экосистема для моряков и яхтсменов. ИИ-помощник отвечает, помогает создать резюме и искать вакансии."
    },
    "choose_lang": {
        "uk": "🌐 Обери мову:",
        "en": "🌐 Choose a language:",
        "ru": "🌐 Выберите язык:"
    },
    "weather_missing": {
        "uk": "Щоб користуватися погодою, налаштуй змінну OWM_KEY або вкажи місто: /weather [порт]",
        "en": "To use weather, set OWM_KEY env var or enter: /weather [port]",
        "ru": "Чтобы использовать погоду, установите OWM_KEY или введите: /weather [порт]"
    }
}

# ---------------------------
# Helpers
# ---------------------------
def get_lang_for_user(user_id, fallback="en"):
    return user_languages.get(user_id, fallback)

def detect_lang_from_update(update: Update):
    # prefer stored language, fallback to user's telegram language_code
    uid = update.effective_user.id
    if uid in user_languages:
        return user_languages[uid]
    lc = update.effective_user.language_code or "en"
    # normalize
    lc = lc.lower()
    if lc.startswith("uk"):
        return "uk"
    if lc.startswith("ru"):
        return "ru"
    return "en"

def safe_send_text(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str):
    return context.bot.send_message(chat_id=chat_id, text=text)

# ---------------------------
# Commands - simple
# ---------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = detect_lang_from_update(update)
    await update.message.reply_text(texts["start"][lang])

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = detect_lang_from_update(update)
    await update.message.reply_text(texts["help"][lang])

async def about_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = detect_lang_from_update(update)
    await update.message.reply_text(texts["about"][lang])

# ---------------------------
# /language
# ---------------------------
async def language_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    keyboard = [['🇺🇦 Українська', '🇬🇧 English', '🇷🇺 Русский']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    lang = detect_lang_from_update(update)
    await update.message.reply_text(texts["choose_lang"][lang], reply_markup=reply_markup)

async def set_language_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    uid = update.effective_user.id
    if "Україн" in text:
        user_languages[uid] = "uk"
        await update.message.reply_text("✅ Мову встановлено: Українська 🇺🇦")
    elif "Рус" in text:
        user_languages[uid] = "ru"
        await update.message.reply_text("✅ Язык установлен: Русский 🇷🇺")
    else:
        user_languages[uid] = "en"
        await update.message.reply_text("✅ Language set: English 🇬🇧")

# ---------------------------
# /news - fetch top N from RSS feeds
# ---------------------------
DEFAULT_NEWS_FEEDS = [
    "https://www.yachtingworld.com/feed/",            # Yachting World
    "https://www.maritime-executive.com/rss/all",     # Maritime Executive
    "https://www.imo.org/en/MediaCentre/Pages/News.aspx?rss=1"  # IMO (may vary)
]

async def news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = detect_lang_from_update(update)
    feeds = [u for u in (NEWS_RSS.split(",") if NEWS_RSS else DEFAULT_NEWS_FEEDS) if u]
    send_lines = []
    count = 0
    max_items = 5
    for feed_url in feeds:
        try:
            d = feedparser.parse(feed_url)
            for e in d.entries[:max_items]:
                title = e.get("title", "No title")
                link = e.get("link", "")
                summary = e.get("summary", "") or e.get("description", "")
                send_lines.append(f"• {title}\n{link}")
                count += 1
                if count >= 6:
                    break
        except Exception as ex:
            logger.exception("Error parsing feed %s: %s", feed_url, ex)
        if count >= 6:
            break
    if not send_lines:
        await update.message.reply_text({
            "uk": "Немає новин. Перевір налаштування RSS або додай NEWS_RSS.",
            "en": "No news found. Check RSS settings or add NEWS_RSS env var.",
            "ru": "Новостей не найдено. Проверьте RSS или добавьте NEWS_RSS."
        }[lang])
        return
    await update.message.reply_text("\n\n".join(send_lines[:6]))

# ---------------------------
# /jobs - similar RSS / JSON job sources
# ---------------------------
DEFAULT_JOB_FEEDS = [
    "https://www.yotspot.com/jobs/rss",      # (example) may or may not exist
    # add more job RSS endpoints or API endpoints here
]

async def jobs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = detect_lang_from_update(update)
    feeds = [u for u in (JOBS_RSS.split(",") if JOBS_RSS else DEFAULT_JOB_FEEDS) if u]
    items = []
    for feed_url in feeds:
        try:
            d = feedparser.parse(feed_url)
            for e in d.entries[:5]:
                items.append(f"• {e.get('title','No title')}\n{e.get('link','')}")
        except Exception:
            logger.exception("Job feed error for %s", feed_url)
    if not items:
        await update.message.reply_text({
            "uk": "Немає вакансій. Додай JOBS_RSS або перевір джерела.",
            "en": "No jobs found. Add JOBS_RSS or check sources.",
            "ru": "Вакансий не найдено. Добавьте JOBS_RSS или проверьте источники."
        }[lang])
        return
    await update.message.reply_text("\n\n".join(items[:8]))

# ---------------------------
# /weather [location] (uses OpenWeatherMap)
# ---------------------------
async def weather_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = detect_lang_from_update(update)
    if not OWM_KEY:
        return await update.message.reply_text(texts["weather_missing"][lang])
    args = context.args
    if not args:
        return await update.message.reply_text({
            "uk": "Вкажи порт або місто: /weather Split",
            "en": "Specify port or city: /weather Split",
            "ru": "Укажите порт или город: /weather Split"
        }[lang])
    city = " ".join(args)
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={requests.utils.quote(city)}&appid={OWM_KEY}&units=metric"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        j = r.json()
        desc = j["weather"][0]["description"]
        temp = j["main"]["temp"]
        wind = j.get("wind", {}).get("speed", 0)
        reply = {
            "uk": f"Погода в {city}: {desc}, {temp}°C, вітер {wind} m/s",
            "en": f"Weather in {city}: {desc}, {temp}°C, wind {wind} m/s",
            "ru": f"Погода в {city}: {desc}, {temp}°C, ветер {wind} m/s"
        }[lang]
    except Exception as e:
        logger.exception("Weather error")
        reply = {
            "uk": "Не вдалося отримати погоду.",
            "en": "Could not fetch weather.",
            "ru": "Не удалось получить погоду."
        }[lang]
    await update.message.reply_text(reply)

# ---------------------------
# /routes /tips /contact - simple canned responses
# ---------------------------
async def routes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = detect_lang_from_update(update)
    await update.message.reply_text({
        "uk": "🗺️ Популярні маршрути: Хорватія, Італія, Греція.",
        "en": "🗺️ Popular routes: Croatia, Italy, Greece.",
        "ru": "🗺️ Популярные маршруты: Хорватия, Италия, Греция."
    }[lang])

async def tips_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = detect_lang_from_update(update)
    await update.message.reply_text({
        "uk": "⚓ Порада: перед виходом перевір запасні системи та причеплення.",
        "en": "⚓ Tip: check backup systems and mooring before departure.",
        "ru": "⚓ Совет: проверьте запасные системы и швартовку перед выходом."
    }[lang])

async def contact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = detect_lang_from_update(update)
    await update.message.reply_text({
        "uk": "📩 Контакт: seaworldlive.wordpress.com",
        "en": "📩 Contact: seaworldlive.wordpress.com",
        "ru": "📩 Контакт: seaworldlive.wordpress.com"
    }[lang])

# ---------------------------
# /ask or plain messages => OpenAI
# ---------------------------
async def ai_answer(user_text: str):
    # simple wrapper
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": user_text}],
            temperature=0.25,
            max_tokens=700
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.exception("OpenAI error")
        return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    # If it starts with '/', ignore (other handlers)
    if text.startswith("/"):
        return
    # treat as AI question
    await update.message.chat.send_action(action="typing")
    answer = await ai_answer(text)
    if not answer:
        lang = detect_lang_from_update(update)
        await update.message.reply_text({
            "uk": "⛔ Вибач, зараз я недоступний. Спробуй пізніше.",
            "en": "⛔ Sorry, I'm unavailable right now. Try later.",
            "ru": "⛔ Извини, сейчас я недоступен. Попробуйте позже."
        }[lang])
    else:
        await update.message.reply_text(answer)

# ---------------------------
# /cv - Conversation handler: collect fields then generate PDF
# ---------------------------
CV_NAME, CV_POS, CV_EXP, CV_CERTS, CV_CONTACT, CV_CONFIRM = range(6)

def generate_cv_pdf(data: dict, output_path: str):
    # simple CV generator using FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=14)
    pdf.cell(0, 8, "SeaWorld Life - Crew CV", ln=1)
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 7, f"Name: {data.get('name','')}", ln=1)
    pdf.cell(0, 7, f"Position: {data.get('position','')}", ln=1)
    pdf.cell(0, 7, f"Experience: {data.get('experience','')}", ln=1)
    pdf.cell(0, 7, "Certifications:", ln=1)
    pdf.multi_cell(0, 6, data.get("certs",""))
    pdf.cell(0, 7, f"Contacts: {data.get('contact','')}", ln=1)
    pdf.ln(4)
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 6, f"Generated: {datetime.utcnow().isoformat()} UTC", ln=1)
    pdf.output(output_path)

async def cv_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = detect_lang_from_update(update)
    await update.message.reply_text({
        "uk": "Давай створимо CV. Введи своє повне ім'я:",
        "en": "Let's create your CV. Enter your full name:",
        "ru": "Давайте создадим резюме. Введите ваше полное имя:"
    }[lang])
    return CV_NAME

async def cv_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['cv_name'] = update.message.text.strip()
    lang = detect_lang_from_update(update)
    await update.message.reply_text({
        "uk": "Посада, на яку претендуєш (наприклад: Deckhand, Engineer, Stewardess):",
        "en": "Position you apply for (e.g. Deckhand, Engineer, Stewardess):",
        "ru": "Должность, на которую претендуете (например: Deckhand, Engineer, Stewardess):"
    }[lang])
    return CV_POS

async def cv_pos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['cv_pos'] = update.message.text.strip()
    lang = detect_lang_from_update(update)
    await update.message.reply_text({
        "uk": "Коротко опиши досвід (роки, типи суден):",
        "en": "Briefly describe experience (years, vessel types):",
        "ru": "Кратко опишите опыт (годы, типы судов):"
    }[lang])
    return CV_EXP

async def cv_exp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['cv_exp'] = update.message.text.strip()
    lang = detect_lang_from_update(update)
    await update.message.reply_text({
        "uk": "Перерахуйте сертифікати / STCW / курси (через коми):",
        "en": "List certificates / STCW / courses (comma separated):",
        "ru": "Перечислите сертификаты / STCW / курсы (через запятую):"
    }[lang])
    return CV_CERTS

async def cv_certs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['cv_certs'] = update.message.text.strip()
    lang = detect_lang_from_update(update)
    await update.message.reply_text({
        "uk": "Контакти (email / Telegram / phone):",
        "en": "Contacts (email / Telegram / phone):",
        "ru": "Контакты (email / Telegram / телефон):"
    }[lang])
    return CV_CONTACT

async def cv_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['cv_contact'] = update.message.text.strip()
    data = {
        "name": context.user_data.get('cv_name',''),
        "position": context.user_data.get('cv_pos',''),
        "experience": context.user_data.get('cv_exp',''),
        "certs": context.user_data.get('cv_certs',''),
        "contact": context.user_data.get('cv_contact',''),
    }
    # create pdf
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
        pdf_path = tf.name
    try:
        generate_cv_pdf(data, pdf_path)
        # send
        await update.message.reply_document(open(pdf_path, "rb"), filename=f"{data['name']}_CV.pdf")
    except Exception:
        logger.exception("CV PDF generation failed")
        await update.message.reply_text("❗ Error generating CV.")
    finally:
        try:
            os.remove(pdf_path)
        except Exception:
            pass
    return ConversationHandler.END

async def cv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("CV creation cancelled.")
    return ConversationHandler.END

# ---------------------------
# /subscribe - placeholder
# ---------------------------
async def subscribe_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    subscribers.add(uid)
    await update.message.reply_text("✅ Subscribed to daily digest (placeholder).")

# ---------------------------
# Main: create application and handlers
# ---------------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Basic commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("about", about_cmd))
    app.add_handler(CommandHandler("news", news_cmd))
    app.add_handler(CommandHandler("jobs", jobs_cmd))
    app.add_handler(CommandHandler("weather", weather_cmd))
    app.add_handler(CommandHandler("routes", routes_cmd))
    app.add_handler(CommandHandler("tips", tips_cmd))
    app.add_handler(CommandHandler("contact", contact_cmd))
    app.add_handler(CommandHandler("language", language_cmd))
    app.add_handler(CommandHandler("subscribe", subscribe_cmd))

    # Language selection by keyboard
    app.add_handler(MessageHandler(filters.Regex("^(🇺🇦 Українська|🇬🇧 English|🇷🇺 Русский)$"), set_language_msg))

    # CV conversation
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('cv', cv_start)],
        states={
            CV_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cv_name)],
            CV_POS: [MessageHandler(filters.TEXT & ~filters.COMMAND, cv_pos)],
            CV_EXP: [MessageHandler(filters.TEXT & ~filters.COMMAND, cv_exp)],
            CV_CERTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, cv_certs)],
            CV_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cv_contact)],
        },
        fallbacks=[CommandHandler('cancel', cv_cancel)],
        allow_reentry=True
    )
    app.add_handler(conv_handler)

    # AI handler for plain text (fallback)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start polling
    logger.info("Starting SeaWorld AI Bot...")
    app.run_polling()

if __name__ == "__main__":
    main()
