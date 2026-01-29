import os
import re
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# ========== НАСТРОЙКИ ==========
CLINIC_NAME = "ПанОптика"

def clean_url(u: str) -> str:
    return (u or "").strip().replace("\n", "").replace("\r", "")

BOOKING_URL = clean_url("https://online-zapis.com/online/00691")
INSTAGRAM_URL = clean_url("https://www.instagram.com/panoptika_brest?igsh=MTlmYndrbXlwZ3hmbA==")
SITE_URL = clean_url("https://panoptika.by/")

YANDEX_MAPS_URL = clean_url("https://yandex.ru/maps/org/229002285621?si=r8mrjp7wcrya9x5p9a20t6qgc8")
YANDEX_REVIEW_URL = clean_url("https://yandex.ru/maps/org/229002285621/reviews/")

ADDRESS_TEXT = "Брест, ул. Пушкинская 6/1"

PHONE_RAW = "+375336518747"          # для tel:
PHONE_PRETTY = "+375 33 651-87-47"   # как показывать людям

# callback data
CB_CALL = "CALL"
CB_WRITE_ADMIN = "WRITE_ADMIN"
CB_BACK = "BACK"

# режим ожидания сообщения админу
WAITING_FOR_ADMIN = set()

# ========== КЛАВИАТУРЫ ==========
def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Запись к врачу", url=BOOKING_URL)],  # сразу на сайт
        [InlineKeyboardButton("📞 Позвонить", callback_data=CB_CALL)],
        [InlineKeyboardButton("📸 Instagram", url=INSTAGRAM_URL)],
        [InlineKeyboardButton("⭐ Отзыв на Яндекс.Картах (−10%)", url=YANDEX_REVIEW_URL)],
        [InlineKeyboardButton("✍️ Написать администратору", callback_data=CB_WRITE_ADMIN)],
    ])

def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=CB_BACK)]])

def call_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📞 Набрать {PHONE_PRETTY}", url=f"tel:{PHONE_RAW}")],
        [InlineKeyboardButton("🗺 Яндекс.Карты", url=YANDEX_MAPS_URL)],
        [InlineKeyboardButton("⬅️ Назад", callback_data=CB_BACK)],
    ])

# ========== ХЕЛПЕРЫ ==========
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

def extract_user_id_from_forwarded(text: str) -> int:
    # ищем "🆔 123456"
    if not text:
        return 0
    m = re.search(r"🆔\s*(\d+)", text)
    return int(m.group(1)) if m else 0

# ========== КОМАНДЫ ==========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    WAITING_FOR_ADMIN.discard(update.effective_user.id)
    text = (
        f"👓 {CLINIC_NAME}\n\n"
        f"📍 Адрес: {ADDRESS_TEXT}\n"
        f"📞 Телефон: {PHONE_PRETTY}\n\n"
        "Выберите действие кнопками ниже 👇"
    )
    await update.message.reply_text(text, reply_markup=main_keyboard(), disable_web_page_preview=True)

async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Ваш chat_id: {update.effective_chat.id}")

# ========== КНОПКИ ==========
async def on_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id

    if query.data == CB_CALL:
        WAITING_FOR_ADMIN.discard(uid)
        text = (
            f"📞 Позвонить в {CLINIC_NAME}\n\n"
            f"Номер: {PHONE_PRETTY}\n\n"
            "Нажмите кнопку «Набрать» ниже."
        )
        await query.edit_message_text(
            text=text,
            reply_markup=call_keyboard(),
            disable_web_page_preview=True
        )
        return

    if query.data == CB_WRITE_ADMIN:
        WAITING_FOR_ADMIN.add(uid)
        text = (
            "✍️ Напишите пожалуйста сообщение, администратор ответит вам как можно скорее.\n\n"
            "Например: «Хочу записаться на завтра после 18:00» или «Подскажите стоимость линз».\n\n"
            "Чтобы отменить — нажмите «Назад»."
        )
        await query.edit_message_text(text=text, reply_markup=back_keyboard())
        return

    if query.data == CB_BACK:
        WAITING_FOR_ADMIN.discard(uid)
        text = (
            f"👓 {CLINIC_NAME}\n\n"
            f"📍 Адрес: {ADDRESS_TEXT}\n"
            f"📞 Телефон: {PHONE_PRETTY}\n\n"
            "Выберите действие кнопками ниже 👇"
        )
        await query.edit_message_text(
            text=text,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True
        )
        return

# ========== КЛИЕНТ → АДМИН ==========
async def on_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not update.message or not update.message.text:
        return

    # если не в режиме "написать админу" — просто показываем меню
    if user.id not in WAITING_FOR_ADMIN:
        await update.message.reply_text(
            "Выберите действие кнопками ниже 🙂",
            reply_markup=main_keyboard()
        )
        return

    WAITING_FOR_ADMIN.discard(user.id)

    admin_id = get_admin_chat_id()
    if admin_id == 0:
        await update.message.reply_text(
            "⚠️ Администратор пока не подключён. Попробуйте позже.",
            reply_markup=main_keyboard()
        )
        return

    text = update.message.text.strip()
    msg_to_admin = (
        "✉️ Сообщение от клиента\n"
        f"👤 {user.full_name} (@{user.username})\n"
        f"🆔 {user.id}\n\n"
        f"{text}\n\n"
        "⬇️ Чтобы ответить клиенту — нажмите Reply на это сообщение и напишите ответ."
    )

    await context.bot.send_message(chat_id=admin_id, text=msg_to_admin)
    await update.message.reply_text(
        "✅ Сообщение отправлено администратору. Он ответит вам здесь в чате.",
        reply_markup=main_keyboard()
    )

# ========== АДМИН REPLY → КЛИЕНТ ==========
async def on_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # срабатывает только на Reply-сообщения админа (см. фильтр в main())
    if not is_admin_chat(update):
        return
    if not update.message or not update.message.text or not update.message.reply_to_message:
        return

    original = update.message.reply_to_message.text or ""
    user_id = extract_user_id_from_forwarded(original)
    if user_id == 0:
        await update.message.reply_text("Не нашёл 🆔 пользователя в сообщении, на которое ты отвечаешь.")
        return

    reply_text = update.message.text.strip()
    await context.bot.send_message(
        chat_id=user_id,
        text=f"✅ Ответ администратора:\n\n{reply_text}",
        disable_web_page_preview=True
    )
    await update.message.reply_text("Отправлено клиенту ✅")

# ========== ЗАПУСК ==========
def main() -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN не задан. Добавь BOT_TOKEN в Railway → Variables.")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("myid", cmd_myid))

    app.add_handler(CallbackQueryHandler(on_buttons))

    # 1) Админские ответы Reply — отдельно и первым
    app.add_handler(
        MessageHandler(filters.REPLY & filters.TEXT & ~filters.COMMAND, on_admin_reply),
        group=0
    )
    # 2) Все обычные сообщения пользователей
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_user_text),
        group=1
    )

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
