import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# =========================
# НАСТРОЙКИ (твои ссылки)
# =========================
CLINIC_NAME = "ПанОптика"
BOOKING_URL = "https://online-zapis.com/online/00691"

ADDRESS_TEXT = "Брест, ул. Пушкинская 6/1"
PHONE_TEXT = "+375 33 651-87-47"

INSTAGRAM_URL = "https://www.instagram.com/panoptika_brest?igsh=MTlmYndrbXlwZ3hmbA=="
YANDEX_MAPS_URL = "https://yandex.ru/maps/org/229002285621?si=r8mrjp7wcrya9x5p9a20t6qgc8"

# ВАЖНО: сюда поставь ссылку на страницу “оставить отзыв”
# Если пока нет отдельной ссылки на форму отзыва — оставь просто на карточку.
YANDEX_REVIEW_URL = YANDEX_MAPS_URL

# =========================
# СЛУЖЕБНОЕ
# =========================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

CB_CONTACTS = "contacts"
CB_BACK = "back"


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📅 Запись к врачу", url=BOOKING_URL)],
            [
                InlineKeyboardButton("📍 Яндекс.Карты", url=YANDEX_MAPS_URL),
                InlineKeyboardButton("📸 Instagram", url=INSTAGRAM_URL),
            ],
            [InlineKeyboardButton("⭐ Оставить отзыв и получить скидку 10%", url=YANDEX_REVIEW_URL)],
            [InlineKeyboardButton("☎️ Контакты", callback_data=CB_CONTACTS)],
        ]
    )


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=CB_BACK)]])


def start_text() -> str:
    return (
        f"*{CLINIC_NAME}* — запись к врачу онлайн и контакты.\n\n"
        f"Выберите действие ниже 👇"
    )


def contacts_text() -> str:
    return (
        f"*{CLINIC_NAME} — контакты*\n\n"
        f"📍 *Адрес:* {ADDRESS_TEXT}\n"
        f"📞 *Телефон:* {PHONE_TEXT}\n\n"
        f"📅 *Запись онлайн:* {BOOKING_URL}\n"
        f"📸 *Instagram:* {INSTAGRAM_URL}\n"
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        start_text(),
        reply_markup=main_keyboard(),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def cmd_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        contacts_text(),
        reply_markup=back_keyboard(),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def on_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == CB_CONTACTS:
        await query.edit_message_text(
            contacts_text(),
            reply_markup=back_keyboard(),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        return

    if query.data == CB_BACK:
        await query.edit_message_text(
            start_text(),
            reply_markup=main_keyboard(),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        return


def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("Ошибка: не найден BOT_TOKEN. Добавь переменную окружения BOT_TOKEN.")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("contacts", cmd_contacts))
    app.add_handler(CallbackQueryHandler(on_buttons))

    # Самый простой запуск: long polling
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
