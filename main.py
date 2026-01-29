import os
from typing import Dict, Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================
# НАСТРОЙКИ (можно менять)
# =========================

BOT_TITLE = "👓 ПанОптика"
GREETING_SUBTITLE = "Онлайн-запись к врачу и контакты."
WORK_HOURS = "Пн–Пт 10:00–20:00 · Сб–Вс 10:00–18:00"

BOOKING_URL = "https://online-zapis.com/online/00691"
YANDEX_MAPS_URL = "https://yandex.ru/maps/org/229002285621?si=r8mrjp7wcrya9x5p9a20t6qgc8"
INSTAGRAM_URL = "https://www.instagram.com/panoptika_brest?igsh=MTlmYndrbXlwZ3hmbA=="
# Можно оставить ту же ссылку, или заменить на ссылку именно на отзывы (если найдёшь отдельную страницу reviews)
REVIEW_URL = "https://yandex.ru/maps/org/229002285621?si=r8mrjp7wcrya9x5p9a20t6qgc8"

PHONE_PRETTY = "+375 33 651-87-47"
PHONE_DIGITS = "+375336518747"

# Твой admin chat_id (можно также задать переменной окружения ADMIN_CHAT_ID в Railway)
DEFAULT_ADMIN_CHAT_ID = 6805556593

# Callback data
CB_CALL = "CALL"
CB_WRITE_ADMIN = "WRITE_ADMIN"
CB_SETCHAT_PREFIX = "SETCHAT:"       # SETCHAT:<chat_id>
CB_MENU = "MENU"

# Ключи хранения состояния в памяти (Railway может перезапускать — это нормально)
BOTDATA_ACTIVE_CHAT = "admin_active_chat_id"
BOTDATA_ADMIN_MSG_MAP = "admin_msgid_to_userchat"  # {admin_msg_id: user_chat_id}


# =========================
# ТЕКСТЫ / КНОПКИ
# =========================

def start_text() -> str:
    # Время работы — только здесь, как ты и просил
    return (
        f"{BOT_TITLE}\n"
        f"{GREETING_SUBTITLE}\n\n"
        f"⏰ Время работы: {WORK_HOURS}\n\n"
        "Выберите действие ниже 👇"
    )

def menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📅 Запись к врачу", url=BOOKING_URL)],
            [InlineKeyboardButton("🗺️ Как добраться", url=YANDEX_MAPS_URL)],
            [InlineKeyboardButton("Позвонить", callback_data=CB_CALL)],
            [InlineKeyboardButton("📸 Instagram", url=INSTAGRAM_URL)],
            [InlineKeyboardButton("⭐ Оставьте честный отзыв и получите 10% скидки", url=REVIEW_URL)],
            [InlineKeyboardButton("✍️ Написать администратору", callback_data=CB_WRITE_ADMIN)],
        ]
    )

def admin_reply_keyboard(user_chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✍️ Ответить клиенту", callback_data=f"{CB_SETCHAT_PREFIX}{user_chat_id}")],
            [InlineKeyboardButton("📋 Показать меню клиенту", callback_data=f"{CB_SETCHAT_PREFIX}{user_chat_id}:MENU")],
        ]
    )

def who(update: Update) -> str:
    u = update.effective_user
    if not u:
        return ""
    parts = []
    if u.full_name:
        parts.append(u.full_name)
    if u.username:
        parts.append(f"@{u.username}")
    return " · ".join(parts).strip()

def is_admin(chat_id: int) -> bool:
    admin_id = int(os.getenv("ADMIN_CHAT_ID", str(DEFAULT_ADMIN_CHAT_ID)))
    return chat_id == admin_id


# =========================
# ХЭНДЛЕРЫ
# =========================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(start_text(), reply_markup=menu_keyboard())

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Для админа: выключить "режим ответа клиенту"
    if not update.effective_chat:
        return
    if not is_admin(update.effective_chat.id):
        return

    context.application.bot_data[BOTDATA_ACTIVE_CHAT] = None
    await update.message.reply_text("✅ Режим ответа клиенту выключен. Теперь сообщения не пересылаются клиенту автоматически.")

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    chat_id = query.message.chat_id if query.message else None
    await query.answer()

    # Нажал клиент: "Позвонить"
    if data == CB_CALL:
        # Никаких контакт-карточек. Только сообщение (номер кликабельный).
        await query.message.reply_text(f"📞 Телефон: {PHONE_PRETTY}")
        return

    # Нажал клиент: "Написать администратору"
    if data == CB_WRITE_ADMIN:
        await query.message.reply_text("✍️ Напишите, пожалуйста, сообщение — администратор ответит вам как можно скорее.")
        return

    # Админ выбрал клиента (без reply)
    if data.startswith(CB_SETCHAT_PREFIX):
        if not query.message:
            return
        if not chat_id or not is_admin(chat_id):
            await query.message.reply_text("⛔ Эта кнопка доступна только администратору.")
            return

        payload = data[len(CB_SETCHAT_PREFIX):]

        # Вариант: "SETCHAT:<id>:MENU" — просто показать меню клиенту
        if payload.endswith(":MENU"):
            user_chat_id = int(payload.replace(":MENU", ""))
            await context.bot.send_message(chat_id=user_chat_id, text=start_text(), reply_markup=menu_keyboard())
            await query.message.reply_text("✅ Меню отправлено клиенту.")
            return

        user_chat_id = int(payload)
        context.application.bot_data[BOTDATA_ACTIVE_CHAT] = user_chat_id

        await query.message.reply_text(
            "✅ Вы выбрали клиента.\n"
            "Теперь просто напишите сообщение — я отправлю его клиенту.\n\n"
            "Чтобы выключить режим — /stop"
        )
        return

    if data == CB_MENU:
        await query.message.reply_text(start_text(), reply_markup=menu_keyboard())
        return


async def user_text_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Любое обычное сообщение от клиента автоматически уходит админу."""
    if not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id

    # Если это админ — не сюда
    if is_admin(chat_id):
        return

    admin_id = int(os.getenv("ADMIN_CHAT_ID", str(DEFAULT_ADMIN_CHAT_ID)))

    text = update.message.text or ""
    user_name = who(update)
    user_line = f"{user_name}\n" if user_name else ""
    user_chat_line = f"Chat ID: {chat_id}"

    admin_text = (
        "📩 Сообщение от клиента\n\n"
        f"{user_line}{user_chat_line}\n\n"
        f"Текст:\n{text}\n\n"
        "⬇️ Нажмите кнопку ниже, чтобы ответить клиенту без Reply."
    )

    sent = await context.bot.send_message(
        chat_id=admin_id,
        text=admin_text,
        reply_markup=admin_reply_keyboard(chat_id),
    )

    # Сохраняем связь admin_msg_id -> user_chat_id (если захочешь отвечать Reply-способом в будущем)
    bot_data = context.application.bot_data
    msg_map: Dict[int, int] = bot_data.get(BOTDATA_ADMIN_MSG_MAP, {})
    msg_map[sent.message_id] = chat_id
    bot_data[BOTDATA_ADMIN_MSG_MAP] = msg_map

    # Клиенту: подтверждение + меню
    await update.message.reply_text(
        "✅ Спасибо! Сообщение отправлено администратору.\n\nВыберите действие ниже 👇",
        reply_markup=menu_keyboard(),
    )


async def admin_send_to_selected_client(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Если админ выбрал клиента кнопкой — любые сообщения админа идут клиенту (пока не /stop)."""
    if not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        return

    active_user_chat: Optional[int] = context.application.bot_data.get(BOTDATA_ACTIVE_CHAT)
    if not active_user_chat:
        return  # админ не в режиме ответа

    text = update.message.text or ""
    if not text.strip():
        return

    # Отправляем клиенту
    await context.bot.send_message(
        chat_id=active_user_chat,
        text=f"✅ Ответ администратора:\n\n{text}",
        reply_markup=menu_keyboard(),
    )

    await update.message.reply_text("✅ Отправлено клиенту. (Чтобы выйти из режима — /stop)")


def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("Ошибка: не найден BOT_TOKEN. Добавь переменную окружения BOT_TOKEN в Railway.")

    app = Application.builder().token(token).build()

    # Команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))

    # Кнопки
    app.add_handler(CallbackQueryHandler(on_button))

    # Админ: если выбрал клиента — любые сообщения идут клиенту
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_send_to_selected_client), group=0)

    # Клиент: любое сообщение уходит админу
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user_text_to_admin), group=1)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
