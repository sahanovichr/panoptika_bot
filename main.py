import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# -------------------------
# НАСТРОЙКИ
# -------------------------
CLINIC_NAME = "ПанОптика"

BOOKING_URL = "https://online-zapis.com/online/00691"
INSTAGRAM_URL = "https://www.instagram.com/panoptika_brest?igsh=MTlmYndrbXlwZ3hmbA=="
YANDEX_REVIEW_URL = "https://yandex.ru/maps/org/229002285621?si=r8mrjp7wcrya9x5p9a20t6qgc8"
YANDEX_MAPS_URL = "https://yandex.ru/maps/org/229002285621?si=r8mrjp7wcrya9x5p9a20t6qgc8"

# ВАЖНО: только цифры и плюс (без пробелов, дефисов, текста) — максимально кликабельно
PHONE_CLICK = "+375336518747"

# Callback data
CB_CALL = "call"
CB_WRITE_ADMIN = "write_admin"
CB_STOP_REPLY = "stop_reply"
CB_REPLY_PREFIX = "reply:"  # reply:<chat_id>

# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("panoptika_bot")


def admin_id() -> int:
    v = os.getenv("ADMIN_CHAT_ID", "").strip()
    return int(v) if v.isdigit() else 0


def is_admin(chat_id: int) -> bool:
    return chat_id == admin_id()


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📅 Запись к врачу", url=BOOKING_URL)],
            [InlineKeyboardButton("🗺️ Как добраться", url=YANDEX_MAPS_URL)],
            [InlineKeyboardButton("📞 Позвонить", callback_data=CB_CALL)],
            [InlineKeyboardButton("📸 Instagram", url=INSTAGRAM_URL)],
            [InlineKeyboardButton("⭐ Оставьте честный отзыв и получите 10% скидки", url=YANDEX_REVIEW_URL)],
            [InlineKeyboardButton("✍️ Написать админу", callback_data=CB_WRITE_ADMIN)],
        ]
    )


def start_text() -> str:
    return (
        f"👓 *{CLINIC_NAME}*\n"
        f"Онлайн-запись к врачу и контакты.\n\n"
        f"Выберите действие ниже 👇"
    )


def admin_reply_keyboard(client_chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💬 Ответить клиенту", callback_data=f"{CB_REPLY_PREFIX}{client_chat_id}")],
            [InlineKeyboardButton("⛔️ Завершить ответ", callback_data=CB_STOP_REPLY)],
        ]
    )


def reply_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⛔️ Завершить ответ", callback_data=CB_STOP_REPLY)]])


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_admin_message"] = False
    await update.effective_message.reply_text(
        start_text(),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_chat.id):
        return
    context.application.bot_data["active_client_chat_id"] = None
    await update.message.reply_text("⛔️ Режим ответа выключен.")


async def on_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()  # чтобы не было вечной "загрузки"

    data = query.data

    # Клиент: позвонить
    if data == CB_CALL:
        # Telegram не даёт tel: в URL кнопки. Поэтому отправляем номер одним сообщением.
        # Без текста/эмодзи, чтобы точно был кликабельный для набора.
        await query.message.reply_text(PHONE_CLICK)
        return

    # Клиент: написать админу
    if data == CB_WRITE_ADMIN:
        context.user_data["awaiting_admin_message"] = True
        await query.message.reply_text(
            "✍️ Напишите, пожалуйста, сообщение — администратор ответит вам как можно скорее."
        )
        return

    # Админ: выбрать клиента для ответа
    if data.startswith(CB_REPLY_PREFIX):
        if not is_admin(query.message.chat_id):
            return
        client_chat_id = int(data.split(":", 1)[1])
        context.application.bot_data["active_client_chat_id"] = client_chat_id

        await query.message.reply_text(
            f"💬 Режим ответа включён.\n"
            f"Клиент chat_id: {client_chat_id}\n\n"
            f"Теперь просто пишите сообщения — я отправлю их клиенту.",
            reply_markup=reply_mode_keyboard(),
        )
        return

    # Админ: выключить режим ответа
    if data == CB_STOP_REPLY:
        if is_admin(query.message.chat_id):
            context.application.bot_data["active_client_chat_id"] = None
            await query.message.reply_text("⛔️ Режим ответа выключен.")
        return


# -------------------------
# КЛИЕНТ -> АДМИН
# -------------------------
async def client_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text = update.message.text

    # админа не трогаем тут
    if is_admin(chat_id):
        return

    # если клиент нажал "Написать админу" — следующее сообщение улетает админу
    if context.user_data.get("awaiting_admin_message"):
        context.user_data["awaiting_admin_message"] = False

        a_id = admin_id()
        if not a_id:
            await update.message.reply_text("⚠️ Администратор не настроен. Попробуйте позже.")
            return

        user = update.effective_user
        uname = f"@{user.username}" if user.username else "(без username)"

        admin_text = (
            f"📩 Сообщение от клиента\n"
            f"• Имя: {user.full_name}\n"
            f"• Username: {uname}\n"
            f"• chat_id: {chat_id}\n\n"
            f"{text}"
        )

        await context.bot.send_message(
            chat_id=a_id,
            text=admin_text,
            reply_markup=admin_reply_keyboard(chat_id),
        )

        await update.message.reply_text(
            "✅ Спасибо! Сообщение отправлено администратору.\n\nВыберите действие ниже 👇",
            reply_markup=main_keyboard(),
        )
        return

    # любое другое сообщение — показываем меню
    await update.message.reply_text("Выберите действие ниже 👇", reply_markup=main_keyboard())


# -------------------------
# АДМИН -> КЛИЕНТ (без Reply)
# -------------------------
async def admin_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_chat.id):
        return

    active = context.application.bot_data.get("active_client_chat_id")
    if not active:
        await update.message.reply_text(
            "ℹ️ Сначала выберите клиента: нажмите “💬 Ответить клиенту” под сообщением клиента."
        )
        return

    text = update.message.text
    await context.bot.send_message(chat_id=active, text=f"✅ Ответ администратора:\n\n{text}")
    await update.message.reply_text("Отправлено ✅", reply_markup=reply_mode_keyboard())


def build_app() -> Application:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN не найден. Добавь BOT_TOKEN в Railway Variables.")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CallbackQueryHandler(on_buttons))

    # Сначала админские сообщения, потом клиентские
    a_id = admin_id()
    if a_id:
        app.add_handler(
            MessageHandler(filters.TEXT & filters.Chat(chat_id=a_id) & ~filters.COMMAND, admin_text_router)
        )

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, client_text_router))

    return app


def main() -> None:
    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()


