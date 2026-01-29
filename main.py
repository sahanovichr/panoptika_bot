import os
import logging
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.helpers import escape


# =========================
# НАСТРОЙКИ (можно менять)
# =========================
CLINIC_NAME = "👓 ПанОптика"

BOOKING_URL = "https://online-zapis.com/online/00691"
INSTAGRAM_URL = "https://www.instagram.com/panoptika_brest?igsh=MTlmYndrbXlwZ3hmbA=="
YANDEX_REVIEW_URL = "https://yandex.ru/maps/org/229002285621?si=r8mrjp7wcrya9x5p9a20t6qgc8"

PHONE_DISPLAY = "+375 33 651-87-47"
PHONE_TEL = "+3753365188747"  # для tel: лучше без пробелов/скобок

# =========================
# CALLBACK DATA
# =========================
CB_WRITE_ADMIN = "WRITE_ADMIN"
CB_ADMIN_REPLY_PREFIX = "ADMIN_REPLY:"  # + chat_id


# =========================
# ТЕКСТЫ
# =========================
def start_text() -> str:
    return (
        f"{CLINIC_NAME}\n"
        f"Онлайн-запись к врачу и контакты.\n\n"
        f"Выберите действие ниже 👇"
    )


def after_action_text() -> str:
    return "Выберите действие ниже 👇"


def ask_user_message_text() -> str:
    return "✍️ Напишите, пожалуйста, сообщение — администратор ответит вам как можно скорее."


def call_info_text() -> str:
    return (
        f"📞 Телефон: {PHONE_DISPLAY}\n"
        f"Если кнопка «Позвонить» не сработала (на ПК бывает), просто нажмите на номер и позвоните."
    )


def admin_help_text() -> str:
    return (
        "🛠 *Админ-панель*\n\n"
        "Как отвечать клиенту *без Reply*:\n"
        "1) Нажми кнопку *«Ответить этому клиенту»* под его сообщением — и просто напиши ответ.\n"
        "2) Или команда разово: `/to <chat_id> <текст>`\n"
        "3) Или включи режим: `/chat <chat_id>` — дальше всё, что пишешь, улетает клиенту.\n"
        "Выключить режим: `/chat off`\n"
        "Проверить статус: `/chat status`\n"
    )


# =========================
# КНОПКИ
# =========================
def main_menu_keyboard() -> InlineKeyboardMarkup:
    # ВАЖНО: чтобы не было "загрузки" — URL-кнопки не требуют callback
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📅 Запись к врачу", url=BOOKING_URL)],
            [InlineKeyboardButton("📞 Позвонить", url=f"tel:{PHONE_TEL}")],
            [InlineKeyboardButton("📸 Instagram", url=INSTAGRAM_URL)],
            [InlineKeyboardButton("⭐ Отзыв на Яндекс.Картах (−10%)", url=YANDEX_REVIEW_URL)],
            [InlineKeyboardButton("✍️ Написать администратору", callback_data=CB_WRITE_ADMIN)],
        ]
    )


def admin_reply_keyboard(user_chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Ответить этому клиенту", callback_data=f"{CB_ADMIN_REPLY_PREFIX}{user_chat_id}")]]
    )


# =========================
# УТИЛИТЫ
# =========================
def is_admin(chat_id: int, admin_id: int) -> bool:
    return chat_id == admin_id


def get_admin_id() -> int:
    raw = os.getenv("ADMIN_CHAT_ID", "").strip()
    if not raw:
        raise SystemExit("Ошибка: не найден ADMIN_CHAT_ID. Добавь переменную окружения ADMIN_CHAT_ID.")
    return int(raw)


def normalize_chat_id(s: str) -> Optional[int]:
    try:
        return int(s.strip())
    except Exception:
        return None


# =========================
# ХЕНДЛЕРЫ
# =========================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # /start должен всегда отвечать
    await update.message.reply_text(
        start_text(),
        reply_markup=main_menu_keyboard(),
        disable_web_page_preview=True,
    )


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin_id = get_admin_id()
    if not is_admin(update.effective_chat.id, admin_id):
        return
    await update.message.reply_text(
        admin_help_text(),
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def on_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()  # <- критично, иначе в Telegram будет вечная "загрузка"

    admin_id = get_admin_id()
    user_chat_id = query.message.chat.id

    # Пользователь нажал "Написать администратору"
    if query.data == CB_WRITE_ADMIN:
        # включаем режим ожидания сообщения от пользователя
        context.user_data["awaiting_user_message"] = True
        await query.message.reply_text(ask_user_message_text())
        return

    # Админ нажал "Ответить этому клиенту"
    if query.data.startswith(CB_ADMIN_REPLY_PREFIX) and is_admin(user_chat_id, admin_id):
        target = query.data.replace(CB_ADMIN_REPLY_PREFIX, "").strip()
        target_id = normalize_chat_id(target)
        if not target_id:
            await query.message.reply_text("Не смог распознать chat_id.")
            return

        # ставим "ожидание ответа админа" именно на админский чат
        context.user_data["pending_admin_reply_to"] = target_id
        await query.message.reply_text(
            f"✍️ Напиши текст ответа — я отправлю клиенту (chat_id: {target_id}).\n"
            f"Отмена: /chat off"
        )
        return


async def cmd_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # /to <chat_id> <text>
    admin_id = get_admin_id()
    if not is_admin(update.effective_chat.id, admin_id):
        return

    if len(context.args) < 2:
        await update.message.reply_text("Формат: /to <chat_id> <текст>")
        return

    target_id = normalize_chat_id(context.args[0])
    if not target_id:
        await update.message.reply_text("Не понял chat_id. Пример: /to 6805556593 Здравствуйте!")
        return

    text = " ".join(context.args[1:]).strip()
    await context.bot.send_message(chat_id=target_id, text=f"✅ Ответ администратора:\n\n{text}")
    await update.message.reply_text("Отправлено ✅")


async def cmd_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # /chat <chat_id | off | status>
    admin_id = get_admin_id()
    if not is_admin(update.effective_chat.id, admin_id):
        return

    if not context.args:
        await update.message.reply_text("Формат: /chat <chat_id | off | status>")
        return

    arg = context.args[0].strip().lower()

    if arg == "off":
        context.user_data.pop("chat_mode_target", None)
        context.user_data.pop("pending_admin_reply_to", None)
        await update.message.reply_text("Режим чата выключен ✅")
        return

    if arg == "status":
        tgt = context.user_data.get("chat_mode_target")
        if tgt:
            await update.message.reply_text(f"Режим чата включен ✅ chat_id: {tgt}")
        else:
            await update.message.reply_text("Режим чата выключен.")
        return

    target_id = normalize_chat_id(arg)
    if not target_id:
        await update.message.reply_text("Не понял chat_id. Формат: /chat 6805556593")
        return

    context.user_data["chat_mode_target"] = target_id
    await update.message.reply_text(f"Режим чата включен ✅ Теперь всё, что ты пишешь, уходит клиенту {target_id}.\n"
                                   f"Выключить: /chat off")


async def on_any_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    1) Если пишет клиент после "Написать администратору" -> пересылаем админу
    2) Если пишет админ и включен чат-режим или pending reply -> отправляем клиенту
    3) Иначе для клиента: показываем меню (мягко)
    """
    if not update.message:
        return

    admin_id = get_admin_id()
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    # ======= Админ пишет =======
    if is_admin(chat_id, admin_id):
        # 1) если админ нажал кнопку "Ответить этому клиенту" и ждём текст
        pending = context.user_data.get("pending_admin_reply_to")
        if pending:
            await context.bot.send_message(chat_id=pending, text=f"✅ Ответ администратора:\n\n{text}")
            await update.message.reply_text("Отправлено клиенту ✅")
            context.user_data.pop("pending_admin_reply_to", None)
            return

        # 2) режим чата
        tgt = context.user_data.get("chat_mode_target")
        if tgt:
            await context.bot.send_message(chat_id=tgt, text=f"✅ Ответ администратора:\n\n{text}")
            await update.message.reply_text("Отправлено ✅")
            return

        # 3) админ без режима — подсказка
        await update.message.reply_text(
            "Режим чата не включен.\n"
            "Включить: /chat <chat_id>\n"
            "Разово: /to <chat_id> <текст>\n"
            "Справка: /admin"
        )
        return

    # ======= Клиент пишет =======
    awaiting = context.user_data.get("awaiting_user_message") is True

    # Если клиент нажал "Написать администратору" и теперь отправил текст
    if awaiting and text:
        # выключаем ожидание
        context.user_data["awaiting_user_message"] = False

        user = update.effective_user
        username = f"@{user.username}" if user.username else "(без username)"
        safe_name = escape(user.full_name)

        # Сообщение админу
        admin_msg = (
            f"✉️ Сообщение от клиента\n"
            f"👤 {safe_name} {username}\n"
            f"🆔 chat_id: `{chat_id}`\n\n"
            f"{escape(text)}"
        )

        await context.bot.send_message(
            chat_id=admin_id,
            text=admin_msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin_reply_keyboard(chat_id),
            disable_web_page_preview=True,
        )

        await update.message.reply_text("✅ Сообщение отправлено администратору. Он ответит вам как можно скорее.")
        # после отправки — снова показываем меню
        await update.message.reply_text(after_action_text(), reply_markup=main_menu_keyboard())
        return

    # Если клиент написал что-то “не по сценарию” — просто покажем меню
    await update.message.reply_text(after_action_text(), reply_markup=main_menu_keyboard())


async def cmd_call(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Доп. команда на случай: /call
    await update.message.reply_text(call_info_text(), reply_markup=main_menu_keyboard())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(after_action_text(), reply_markup=main_menu_keyboard())


# =========================
# MAIN
# =========================
def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Ошибка: не найден BOT_TOKEN. Добавь переменную окружения BOT_TOKEN.")

    # Проверим ADMIN_CHAT_ID сразу
    _ = get_admin_id()

    app = Application.builder().token(token).build()

    # команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("call", cmd_call))

    # админ-команды
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("to", cmd_to))
    app.add_handler(CommandHandler("chat", cmd_chat))

    # кнопки
    app.add_handler(CallbackQueryHandler(on_buttons))

    # любые тексты
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_any_text))

    # Запуск (polling)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
