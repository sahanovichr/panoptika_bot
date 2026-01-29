import os
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
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
# НАСТРОЙКИ (твои данные)
# -------------------------
CLINIC_NAME = "ПанОптика"
BOOKING_URL = "https://online-zapis.com/online/00691"
INSTAGRAM_URL = "https://www.instagram.com/panoptika_brest?igsh=MTlmYndrbXlwZ3hmbA=="
YANDEX_REVIEW_URL = "https://yandex.ru/maps/org/229002285621?si=r8mrjp7wcrya9x5p9a20t6qgc8"

PHONE_E164 = "+3753365188747"          # для contact-карточки (без пробелов/дефисов)
PHONE_DISPLAY = "+375 33 651-87-47"    # как показывать человеку
ADDRESS = "Брест, ул. Пушкинская 6/1"

# Callback data
CB_CALL = "call"
CB_WRITE_ADMIN = "write_admin"

# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("panoptika_bot")


def admin_id() -> int:
    """ADMIN_CHAT_ID хранится в Railway Variables"""
    v = os.getenv("ADMIN_CHAT_ID", "").strip()
    return int(v) if v.isdigit() else 0


def is_admin_chat(chat_id: int) -> bool:
    return chat_id == admin_id()


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📅 Запись к врачу", url=BOOKING_URL)],
            [InlineKeyboardButton("📞 Позвонить", callback_data=CB_CALL)],
            [InlineKeyboardButton("📸 Instagram", url=INSTAGRAM_URL)],
            [InlineKeyboardButton("⭐ Отзыв на Яндекс.Картах (−10%)", url=YANDEX_REVIEW_URL)],
            [InlineKeyboardButton("✍️ Написать администратору", callback_data=CB_WRITE_ADMIN)],
        ]
    )


def start_text() -> str:
    return (
        f"👓 *{CLINIC_NAME}*\n"
        f"Онлайн-запись к врачу и контакты.\n\n"
        f"Выберите действие ниже 👇"
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_admin_message"] = False

    await update.effective_message.reply_text(
        start_text(),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


async def on_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()  # убираем "крутилку" у кнопки

    if query.data == CB_CALL:
        # ВАЖНО: tel: url в inline-кнопке Telegram не принимает.
        # Поэтому отправляем контакт-карточку (там есть кнопка звонка).
        await query.message.reply_text(
            f"📞 Телефон: *{PHONE_DISPLAY}*\n"
            f"📍 Адрес: {ADDRESS}",
            parse_mode=ParseMode.MARKDOWN,
        )
        await context.bot.send_contact(
            chat_id=query.message.chat_id,
            phone_number=PHONE_E164,
            first_name=CLINIC_NAME,
        )
        return

    if query.data == CB_WRITE_ADMIN:
        context.user_data["awaiting_admin_message"] = True
        await query.message.reply_text(
            "✍️ Напишите, пожалуйста, сообщение — администратор ответит вам как можно скорее."
        )
        return


# ----------- Админ-чат режим (без Reply) -----------
async def cmd_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin_chat(update.effective_chat.id):
        return

    # /chat <chat_id | off | status>
    if not context.args:
        await update.message.reply_text("Формат: /chat <chat_id | off | status>")
        return

    arg = context.args[0].strip().lower()

    if arg == "status":
        active = context.application.bot_data.get("active_chat_id")
        if active:
            await update.message.reply_text(f"✅ Активный чат: {active}")
        else:
            await update.message.reply_text("💤 Режим чата выключен. Включить: /chat <chat_id>")
        return

    if arg == "off":
        context.application.bot_data["active_chat_id"] = None
        await update.message.reply_text("💤 Режим чата выключен.")
        return

    if arg.isdigit():
        context.application.bot_data["active_chat_id"] = int(arg)
        await update.message.reply_text(f"✅ Режим чата включен. Активный chat_id: {arg}\n"
                                        f"Теперь просто пишите сообщения — я буду отправлять их клиенту.")
        return

    await update.message.reply_text("Формат: /chat <chat_id | off | status>")


async def cmd_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin_chat(update.effective_chat.id):
        return

    # /to <chat_id> <text...>
    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Формат: /to <chat_id> <текст>")
        return

    target = int(context.args[0])
    text = " ".join(context.args[1:])

    await context.bot.send_message(chat_id=target, text=f"✅ Ответ администратора:\n\n{text}")
    await update.message.reply_text("Отправлено клиенту ✅")


async def admin_free_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Если админ включил /chat <id>, то любое его сообщение улетает клиенту."""
    if not is_admin_chat(update.effective_chat.id):
        return

    active = context.application.bot_data.get("active_chat_id")
    if not active:
        # не мешаем админу, просто подсказка
        await update.message.reply_text("💤 Режим чата не включен.\nВключить: /chat <chat_id>\nИли разово: /to <chat_id> <текст>")
        return

    await context.bot.send_message(chat_id=active, text=f"✅ Ответ администратора:\n\n{update.message.text}")
    await update.message.reply_text("Отправлено ✅")


# ----------- Сообщения клиентов -> админу -----------
async def client_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text = update.message.text

    # Админские сообщения сюда не должны попадать
    if is_admin_chat(chat_id):
        return

    # Если клиент нажал "Написать администратору" и бот ждёт текст
    if context.user_data.get("awaiting_admin_message"):
        context.user_data["awaiting_admin_message"] = False

        a_id = admin_id()
        if not a_id:
            await update.message.reply_text("⚠️ Администратор не настроен. Попробуйте позже.")
            return

        user = update.effective_user
        uname = f"@{user.username}" if user.username else "(без username)"
        header = (
            f"📩 Сообщение от клиента:\n"
            f"• Имя: {user.full_name}\n"
            f"• Username: {uname}\n"
            f"• chat_id: {chat_id}\n\n"
        )
        await context.bot.send_message(chat_id=a_id, text=header + text)

        await update.message.reply_text(
            "✅ Спасибо! Сообщение отправлено администратору.\n\n"
            "Выберите действие ниже 👇",
            reply_markup=main_keyboard(),
        )
        return

    # Иначе — просто показываем меню
    await update.message.reply_text(
        "Выберите действие ниже 👇",
        reply_markup=main_keyboard(),
    )


def build_app() -> Application:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN не найден. Добавьте переменную окружения BOT_TOKEN в Railway.")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("chat", cmd_chat))
    app.add_handler(CommandHandler("to", cmd_to))

    app.add_handler(CallbackQueryHandler(on_buttons))

    # Важно: порядок MessageHandler'ов
    app.add_handler(MessageHandler(filters.TEXT & filters.Chat(chat_id=admin_id()) & ~filters.COMMAND, admin_free_text_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, client_text_router))

    return app


def main() -> None:
    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

