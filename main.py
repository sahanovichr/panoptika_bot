import os
import logging
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# =========================
# НАСТРОЙКИ ПАНОПТИКИ
# =========================
CLINIC_NAME = "ПанОптика"

BOOKING_URL = "https://online-zapis.com/online/00691"
INSTAGRAM_URL = "https://www.instagram.com/panoptika_brest?igsh=MTlmYndrbXlwZ3hmbA=="
YANDEX_REVIEW_URL = "https://yandex.ru/maps/org/229002285621?si=r8mrjp7wcrya9x5p9a20t6qgc8"

# Телефон: обязательно в формате +375...
PHONE_DISPLAY = "+375 33 651-87-47"
PHONE_TEL = "+375336518747"  # без пробелов/дефисов

# (Опционально) Яндекс-карты на адрес — если захочешь кнопку "Как добраться"
YANDEX_MAPS_URL = "https://yandex.ru/maps/?text=%D0%91%D1%80%D0%B5%D1%81%D1%82%2C%20%D1%83%D0%BB.%20%D0%9F%D1%83%D1%88%D0%BA%D0%B8%D0%BD%D1%81%D0%BA%D0%B0%D1%8F%206%2F1"

# =========================
# CALLBACK DATA
# =========================
CB_WRITE_ADMIN = "WRITE_ADMIN"
CB_ADMIN_SETCHAT_PREFIX = "ADMIN_SETCHAT:"  # + <chat_id>
CB_ADMIN_CHATOFF = "ADMIN_CHATOFF"

# =========================
# ВСПОМОГАТЕЛЬНОЕ
# =========================
def get_admin_chat_id() -> int:
    v = os.getenv("ADMIN_CHAT_ID", "").strip()
    if not v:
        raise SystemExit("Ошибка: не найден ADMIN_CHAT_ID. Добавь переменную окружения ADMIN_CHAT_ID в Railway.")
    return int(v)

def is_admin_chat(update: Update) -> bool:
    try:
        return update.effective_chat and update.effective_chat.id == get_admin_chat_id()
    except Exception:
        return False

def start_text() -> str:
    return (
        f"👓 {CLINIC_NAME}\n"
        "Онлайн-запись к врачу и контакты.\n\n"
        "Выберите действие ниже 👇"
    )

def main_keyboard() -> InlineKeyboardMarkup:
    # Важно: "Позвонить" делаем URL-кнопкой tel: чтобы НЕ было бесконечной загрузки
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📅 Запись к врачу", url=BOOKING_URL)],
            [InlineKeyboardButton(f"📞 Позвонить ({PHONE_DISPLAY})", url=f"tel:{PHONE_TEL}")],
            [InlineKeyboardButton("📸 Instagram", url=INSTAGRAM_URL)],
            [InlineKeyboardButton("⭐ Отзыв на Яндекс.Картах (−10%)", url=YANDEX_REVIEW_URL)],
            [InlineKeyboardButton("✍️ Написать администратору", callback_data=CB_WRITE_ADMIN)],
            # Если хочешь — раскомментируй:
            # [InlineKeyboardButton("📍 Как добраться (Яндекс.Карты)", url=YANDEX_MAPS_URL)],
        ]
    )

def admin_incoming_keyboard(user_chat_id: int) -> InlineKeyboardMarkup:
    # Кнопка для админа: включить режим /chat с этим клиентом
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💬 Чат с клиентом", callback_data=f"{CB_ADMIN_SETCHAT_PREFIX}{user_chat_id}")],
            [InlineKeyboardButton("⛔️ Выключить чат", callback_data=CB_ADMIN_CHATOFF)],
        ]
    )

def admin_chat_target(context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    # Храним текущую цель чата в bot_data (общая на бота) — удобно, если админ один
    return context.application.bot_data.get("ADMIN_CHAT_TARGET")

def set_admin_chat_target(context: ContextTypes.DEFAULT_TYPE, chat_id: Optional[int]) -> None:
    if chat_id is None:
        context.application.bot_data.pop("ADMIN_CHAT_TARGET", None)
    else:
        context.application.bot_data["ADMIN_CHAT_TARGET"] = int(chat_id)

# =========================
# КОМАНДЫ
# =========================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        start_text(),
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin_chat(update):
        await update.message.reply_text("Команды доступны только администратору.")
        return

    await update.message.reply_text(
        "🛠 Команды админа:\n\n"
        "1) /chat <chat_id>  — включить режим чата с клиентом\n"
        "2) /chat off        — выключить режим чата\n"
        "3) /chat status     — показать текущего клиента\n"
        "4) /to <chat_id> <текст> — разово отправить сообщение клиенту\n\n"
        "Подсказка: можно нажать кнопку «💬 Чат с клиентом» под сообщением клиента.",
        disable_web_page_preview=True,
    )

async def cmd_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin_chat(update):
        return

    if not context.args:
        await update.message.reply_text("Формат: /chat <chat_id | off | status>")
        return

    arg = context.args[0].strip().lower()

    if arg == "off":
        set_admin_chat_target(context, None)
        await update.message.reply_text("✅ Режим чата выключен.")
        return

    if arg == "status":
        target = admin_chat_target(context)
        if target:
            await update.message.reply_text(f"💬 Сейчас чат с клиентом: {target}")
        else:
            await update.message.reply_text("💤 Режим чата не включен.")
        return

    # иначе ждём chat_id
    try:
        user_id = int(arg)
    except ValueError:
        await update.message.reply_text("chat_id должен быть числом. Пример: /chat 6805556593")
        return

    set_admin_chat_target(context, user_id)
    await update.message.reply_text(
        f"💬 Режим чата включен.\n"
        f"Теперь всё, что ты напишешь (без /команд), уйдёт клиенту {user_id}.\n\n"
        f"Отключить: /chat off"
    )

async def cmd_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin_chat(update):
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Формат: /to <chat_id> <сообщение>")
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("chat_id должен быть числом. Пример: /to 6805556593 Привет!")
        return

    text = " ".join(context.args[1:]).strip()
    if not text:
        await update.message.reply_text("Сообщение пустое.")
        return

    await context.bot.send_message(
        chat_id=user_id,
        text=f"✅ Ответ администратора:\n\n{text}",
        disable_web_page_preview=True,
    )
    await update.message.reply_text("Отправлено клиенту ✅")

# =========================
# INLINE CALLBACKS
# =========================
async def on_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    await query.answer()  # важно, чтобы не висела “загрузка”

    # Клиент нажал "Написать администратору"
    if data == CB_WRITE_ADMIN:
        context.user_data["WAITING_ADMIN_MESSAGE"] = True
        await query.message.reply_text(
            "✍️ Напишите, пожалуйста, сообщение — администратор ответит вам как можно скорее.",
            disable_web_page_preview=True,
        )
        return

    # Админ нажал "Чат с клиентом"
    if data.startswith(CB_ADMIN_SETCHAT_PREFIX):
        if not is_admin_chat(update):
            return
        try:
            user_id = int(data.split(":", 1)[1])
        except Exception:
            return

        set_admin_chat_target(context, user_id)
        await query.message.reply_text(
            f"💬 Чат с клиентом {user_id} включен.\n"
            f"Теперь просто пиши текст — он уйдёт клиенту.\n"
            f"Отключить: /chat off"
        )
        return

    if data == CB_ADMIN_CHATOFF:
        if not is_admin_chat(update):
            return
        set_admin_chat_target(context, None)
        await query.message.reply_text("✅ Режим чата выключен.")
        return

# =========================
# ТЕКСТОВЫЕ СООБЩЕНИЯ
# =========================
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    # 1) Если пишет админ и включен режим /chat — отправляем клиенту
    if is_admin_chat(update):
        target = admin_chat_target(context)

        # не трогаем команды
        if text.startswith("/"):
            return

        if not target:
            await update.message.reply_text(
                "💤 Режим чата не включен.\n"
                "Включить: /chat <chat_id>\n"
                "Или разово: /to <chat_id> <текст>"
            )
            return

        await context.bot.send_message(
            chat_id=target,
            text=f"✅ Ответ администратора:\n\n{text}",
            disable_web_page_preview=True,
        )
        await update.message.reply_text("Отправлено клиенту ✅")
        return

    # 2) Если клиент ждал ввода сообщения админу
    if context.user_data.get("WAITING_ADMIN_MESSAGE"):
        context.user_data["WAITING_ADMIN_MESSAGE"] = False

        user = update.effective_user
        user_chat_id = update.effective_chat.id

        username = f"@{user.username}" if user and user.username else "(без username)"
        fullname = user.full_name if user else "(неизвестно)"

        admin_id = get_admin_chat_id()

        admin_text = (
            "📩 Сообщение от клиента\n\n"
            f"👤 {fullname} {username}\n"
            f"🆔 chat_id: {user_chat_id}\n\n"
            f"💬 Текст:\n{text}"
        )

        await context.bot.send_message(
            chat_id=admin_id,
            text=admin_text,
            reply_markup=admin_incoming_keyboard(user_chat_id),
            disable_web_page_preview=True,
        )

        await update.message.reply_text(
            "✅ Сообщение отправлено администратору.\n\n"
            "Выберите действие ниже 👇",
            reply_markup=main_keyboard(),
        )
        return

    # 3) Любой другой текст от клиента — просто показываем меню
    await update.message.reply_text(
        "Выберите действие ниже 👇",
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )

# =========================
# MAIN
# =========================
def main() -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Ошибка: не найден BOT_TOKEN. Добавь переменную окружения BOT_TOKEN в Railway.")

    # Проверяем ADMIN_CHAT_ID заранее
    _ = get_admin_chat_id()

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("chat", cmd_chat))
    app.add_handler(CommandHandler("to", cmd_to))

    app.add_handler(CallbackQueryHandler(on_callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # Railway ок: long polling
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

