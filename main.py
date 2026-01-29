# main.py
import os
import logging
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("panoptika_bot")

# ====== НАСТРОЙКИ ======
CLINIC_NAME = "ПанОптика"

BOOKING_URL = "https://online-zapis.com/online/00691"
INSTAGRAM_URL = "https://www.instagram.com/panoptika_brest?igsh=MTlmYndrbXlwZ3hmbA=="
SITE_URL = "https://panoptika.by/"

YANDEX_MAPS_URL = "https://yandex.ru/maps/org/229002285621?si=r8mrjp7wcrya9x5p9a20t6qgc8"
YANDEX_REVIEW_URL = "https://yandex.ru/maps/org/229002285621?si=r8mrjp7wcrya9x5p9a20t6qgc8"

ADDRESS_TEXT = "Брест, ул. Пушкинская 6/1"
PHONE_RAW = "+375336518747"          # для tel:
PHONE_PRETTY = "+375 33 651-87-47"   # для отображения

# callback data
CB_BOOK = "book"
CB_CONTACTS = "contacts"
CB_INSTAGRAM = "instagram"
CB_REVIEW = "review"
CB_WRITE_ADMIN = "write_admin"
CB_BACK = "back"

# user_id -> ждём сообщение админу
WAITING_FOR_ADMIN = set()

# ====== ТЕКСТЫ ======
def start_text() -> str:
    return (
        f"👓 *{CLINIC_NAME}*\n"
        "Онлайн-запись к врачу и контакты.\n\n"
        "Выберите действие ниже:"
    )

def contacts_text() -> str:
    return (
        f"*Контакты {CLINIC_NAME}*\n\n"
        f"📍 Адрес: {ADDRESS_TEXT}\n"
        f"📞 Телефон: <a href='tel:{PHONE_RAW}'>{PHONE_PRETTY}</a>\n\n"
        f"🌐 Сайт: {SITE_URL}\n"
        f"📸 Instagram: {INSTAGRAM_URL}\n"
    )

def booking_text() -> str:
    return (
        "*Запись к врачу*\n\n"
        "Нажмите кнопку ниже — откроется онлайн-запись.\n"
        "Или напишите администратору прямо здесь."
    )

def instagram_text() -> str:
    return "*Instagram*\n\nНажмите кнопку ниже, чтобы открыть профиль."

def review_text() -> str:
    return (
        "*Отзывы*\n\n"
        "Оставьте отзыв на Яндекс.Картах и получите скидку 10% на заказ.\n"
        "После отзыва можете написать админу — подтвердим скидку."
    )

# ====== КЛАВИАТУРЫ ======
def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Запись к врачу", callback_data=CB_BOOK)],
        [InlineKeyboardButton("☎️ Контакты", callback_data=CB_CONTACTS)],
        [InlineKeyboardButton("📸 Instagram", callback_data=CB_INSTAGRAM)],
        [InlineKeyboardButton("⭐ Отзыв на Яндекс.Картах (-10%)", callback_data=CB_REVIEW)],
        [InlineKeyboardButton("✍️ Написать администратору", callback_data=CB_WRITE_ADMIN)],
    ])

def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=CB_BACK)]])

def contacts_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📞 Позвонить {PHONE_PRETTY}", url=f"tel:{PHONE_RAW}")],
        [InlineKeyboardButton("🗺 Открыть Яндекс.Карты", url=YANDEX_MAPS_URL)],
        [InlineKeyboardButton("✍️ Написать администратору", callback_data=CB_WRITE_ADMIN)],
        [InlineKeyboardButton("⬅️ Назад", callback_data=CB_BACK)],
    ])

def booking_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Открыть онлайн-запись", url=BOOKING_URL)],
        [InlineKeyboardButton("✍️ Написать администратору", callback_data=CB_WRITE_ADMIN)],
        [InlineKeyboardButton("⬅️ Назад", callback_data=CB_BACK)],
    ])

def instagram_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 Открыть Instagram", url=INSTAGRAM_URL)],
        [InlineKeyboardButton("⬅️ Назад", callback_data=CB_BACK)],
    ])

def review_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Оставить отзыв на Яндекс.Картах", url=YANDEX_REVIEW_URL)],
        [InlineKeyboardButton("✍️ Написать администратору", callback_data=CB_WRITE_ADMIN)],
        [InlineKeyboardButton("⬅️ Назад", callback_data=CB_BACK)],
    ])

# ====== ХЕЛПЕРЫ ======
def get_admin_chat_id() -> int:
    val = os.getenv("ADMIN_CHAT_ID", "").strip()
    if not val:
        return 0
    try:
        return int(val)
    except ValueError:
        return 0

def is_admin_chat(update: Update) -> bool:
    admin_id = get_admin_chat_id()
    return admin_id != 0 and update.effective_chat and update.effective_chat.id == admin_id

def extract_user_id_from_text(text: str) -> int:
    """
    Ищем user_id в тексте админского сообщения, которое бот отправляет админу.
    Формат: "🆔 123456789"
    """
    if not text:
        return 0
    m = re.search(r"🆔\s*(\d+)", text)
    return int(m.group(1)) if m else 0

# ====== КОМАНДЫ ======
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    WAITING_FOR_ADMIN.discard(update.effective_user.id)
    await update.message.reply_text(
        start_text(),
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )

async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Ваш chat_id: {update.effective_chat.id}")

# (оставим как запасной вариант)
async def cmd_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_chat(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Используй: /reply <user_id> текст")
        return
    user_id = int(context.args[0])
    reply_text = " ".join(context.args[1:])
    await context.bot.send_message(chat_id=user_id, text=f"✅ Ответ администратора:\n\n{reply_text}")
    await update.message.reply_text("Отправлено клиенту ✅")

# ====== КНОПКИ ======
async def on_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == CB_CONTACTS:
        WAITING_FOR_ADMIN.discard(query.from_user.id)
        await query.edit_message_text(
            contacts_text(),
            reply_markup=contacts_keyboard(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    if data == CB_BOOK:
        WAITING_FOR_ADMIN.discard(query.from_user.id)
        await query.edit_message_text(
            booking_text(),
            reply_markup=booking_keyboard(),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
        return

    if data == CB_INSTAGRAM:
        WAITING_FOR_ADMIN.discard(query.from_user.id)
        await query.edit_message_text(
            instagram_text(),
            reply_markup=instagram_keyboard(),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
        return

    if data == CB_REVIEW:
        WAITING_FOR_ADMIN.discard(query.from_user.id)
        await query.edit_message_text(
            review_text(),
            reply_markup=review_keyboard(),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
        return

    if data == CB_WRITE_ADMIN:
        WAITING_FOR_ADMIN.add(query.from_user.id)
        await query.edit_message_text(
            "✍️ Напишите одним сообщением, что нужно (время/услуга/вопрос). "
            "Я передам администратору.\n\n"
            "Чтобы отменить — нажмите «Назад».",
            reply_markup=back_keyboard(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data == CB_BACK:
        WAITING_FOR_ADMIN.discard(query.from_user.id)
        await query.edit_message_text(
            start_text(),
            reply_markup=main_keyboard(),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
        return

# ====== СООБЩЕНИЯ ОТ КЛИЕНТОВ (в админ) ======
async def on_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or not update.message:
        return

    # клиент не в режиме "написать админу" → просто меню
    if user.id not in WAITING_FOR_ADMIN:
        await update.message.reply_text(
            "Выберите действие кнопками ниже 🙂",
            reply_markup=main_keyboard(),
        )
        return

    WAITING_FOR_ADMIN.discard(user.id)

    admin_id = get_admin_chat_id()
    if admin_id == 0:
        await update.message.reply_text(
            "⚠️ Администратор пока не подключен. Попробуйте позже.",
            reply_markup=main_keyboard(),
        )
        return

    text = update.message.text.strip()

    msg = (
        "✉️ Сообщение от клиента\n"
        f"👤 {user.full_name} (@{user.username})\n"
        f"🆔 {user.id}\n\n"
        f"{text}\n\n"
        "⬇️ *Чтобы ответить клиенту — просто нажми Reply на это сообщение и напиши текст.*"
    )

    await context.bot.send_message(
        chat_id=admin_id,
        text=msg,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )

    await update.message.reply_text(
        "✅ Передал администратору. Он ответит вам здесь в чате.",
        reply_markup=main_keyboard(),
    )

# ====== СООБЩЕНИЯ ОТ АДМИНА (Reply → клиенту) ======
async def on_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_chat(update):
        return
    if not update.message or not update.message.text:
        return

    # Если админ НЕ ответом (Reply) — ничего не делаем (чтобы не было случайных отправок)
    if not update.message.reply_to_message:
        return

    original = update.message.reply_to_message.text or ""
    user_id = extract_user_id_from_text(original)
    if user_id == 0:
        await update.message.reply_text("Не вижу 🆔 user_id в сообщении, на которое ты отвечаешь.")
        return

    admin_reply = update.message.text.strip()

    await context.bot.send_message(
        chat_id=user_id,
        text=f"✅ Ответ администратора:\n\n{admin_reply}",
        disable_web_page_preview=True,
    )

    await update.message.reply_text("Отправлено клиенту ✅")

# ====== ЗАПУСК ======
def main() -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Ошибка: не найден BOT_TOKEN. Добавь переменную BOT_TOKEN в Railway.")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("reply", cmd_reply))  # запасной способ

    app.add_handler(CallbackQueryHandler(on_buttons))

    # ВАЖНО: сначала ловим сообщения админа, потом клиентов
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_admin_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_user_text))

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
