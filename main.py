import asyncio
import os
import re
import secrets
from datetime import datetime
from typing import Optional, Dict

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


# =========================
# CONFIG (заполни под себя)
# =========================

# ✅ 1) Токен бота
# Вариант A (рекомендуется для Railway): переменная окружения BOT_TOKEN
# Вариант B: впиши токен строкой
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip() or "PASTE_YOUR_BOT_TOKEN_HERE"

# ✅ 2) ID админа (твой id)
# Вариант A: переменная окружения ADMIN_CHAT_ID
# Вариант B: впиши числом
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "6805556593"))

# Ссылки
DOCTOR_APPOINTMENT_URL = "https://online-zapis.com/online/00691"
YANDEX_MAP_URL = "https://yandex.ru/maps/org/229002285621?si=r8mrjp7wcrya9x5p9a20t6qgc8"
INSTAGRAM_URL = "https://www.instagram.com/panoptika_brest?igsh=MTlmYndrbXlwZ3hmbA=="
YANDEX_REVIEW_URL = "https://yandex.ru/maps/org/229002285621?si=r8mrjp7wcrya9x5p9a20t6qgc8"

# Контакты
PHONE_PRETTY = "+375 33 651-87-47"
PHONE_CLICK = "+3753365188747"  # кликабельный вариант (без пробелов)

WORK_HOURS_TEXT = (
    "⏰ <b>Время работы</b>:\n"
    "Пн–Пт 10:00–20:00 · Сб–Вс 10:00–18:00"
)

# SQLite
DB_PATH = "panoptika.db"

# Телефон для статуса заказа
PHONE_RE = re.compile(r"^\+375\d{9}$")  # +375XXXXXXXXX

STATUSES = {"Принят", "В работе", "Готов", "Выдан"}

# Если True — клиенту приходит короткое "✅ Отправлено админу"
# Если False — бот молчит (как мессенджер)
CONFIRM_EACH_MESSAGE = True


# =========================
# FSM
# =========================
class Flow(StatesGroup):
    awaiting_phone = State()


# =========================
# CALLBACKS
# =========================
CB_BACK_MAIN = "back_main"
CB_CONTACTS_CALL = "contacts_call"
CB_CONTACTS_HOURS = "contacts_hours"

CB_PROMO_10 = "promo_10"
CB_PROMO_2ND30 = "promo_2nd30"
CB_PROMO_FAMILY = "promo_family"
CB_PROMO_REF = "promo_ref"


# =========================
# "ЧАТ С АДМИНОМ"
# =========================
# user_id -> bool (включен режим чата)
user_in_admin_chat: Dict[int, bool] = {}

# admin_message_id -> user_id (чтобы reply от админа слать клиенту)
forward_map: Dict[int, int] = {}


def is_admin(message: Message) -> bool:
    return message.chat and message.chat.id == ADMIN_CHAT_ID


# =========================
# DB
# =========================
async def db_init() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                order_no TEXT,
                status TEXT NOT NULL,
                comment TEXT,
                eta TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_phone ON orders(phone)")
        await db.commit()


async def db_get_latest_order(phone: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT phone, order_no, status, comment, eta, updated_at
            FROM orders
            WHERE phone = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (phone,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


# =========================
# KEYBOARDS
# =========================
def kb_main():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🗓 Записаться к врачу")
    kb.button(text="🎁 Акции и скидки")
    kb.button(text="📦 Статус заказа")
    kb.button(text="📍 Адрес и контакты")
    kb.button(text="💬 Написать администратору")
    kb.adjust(1, 2, 2)
    return kb.as_markup(resize_keyboard=True)


def kb_promos():
    b = InlineKeyboardBuilder()
    b.button(text="🏷 -10% на комплект (оправа + линзы)", callback_data=CB_PROMO_10)
    b.button(text="👓 Вторая пара -30%", callback_data=CB_PROMO_2ND30)
    b.button(text="👨‍👩‍👧 Семейная скидка", callback_data=CB_PROMO_FAMILY)
    b.button(text="🤝 Приведи друга", callback_data=CB_PROMO_REF)
    b.button(text="↩️ Назад", callback_data=CB_BACK_MAIN)
    b.adjust(1, 1, 1, 1, 1)
    return b.as_markup()


def kb_contacts():
    b = InlineKeyboardBuilder()
    b.button(text="🗺 Как добраться (Яндекс.Карты)", url=YANDEX_MAP_URL)
    # Позвонить делаем callback'ом, потому что Telegram часто ругается на tel: в inline URL
    b.button(text="📞 Позвонить", callback_data=CB_CONTACTS_CALL)
    b.button(text="🕒 Время работы", callback_data=CB_CONTACTS_HOURS)
    b.button(text="↩️ Назад", callback_data=CB_BACK_MAIN)
    b.adjust(1, 1, 1, 1)
    return b.as_markup()


def kb_back_inline():
    b = InlineKeyboardBuilder()
    b.button(text="↩️ Назад", callback_data=CB_BACK_MAIN)
    return b.as_markup()


def kb_doctor_link():
    b = InlineKeyboardBuilder()
    b.button(text="🗓 Открыть онлайн-запись", url=DOCTOR_APPOINTMENT_URL)
    return b.as_markup()


def kb_review_link():
    b = InlineKeyboardBuilder()
    b.button(text="⭐ Оставить отзыв на Яндекс.Картах (−10%)", url=YANDEX_REVIEW_URL)
    b.button(text="↩️ Назад", callback_data=CB_BACK_MAIN)
    b.adjust(1, 1)
    return b.as_markup()


def kb_instagram_link():
    b = InlineKeyboardBuilder()
    b.button(text="📸 Открыть Instagram", url=INSTAGRAM_URL)
    b.button(text="↩️ Назад", callback_data=CB_BACK_MAIN)
    b.adjust(1, 1)
    return b.as_markup()


# =========================
# BOT INIT (aiogram v3.7+)
# =========================
if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
    # Чтобы не падало молча в Railway — явная ошибка в логах
    raise SystemExit("❌ BOT_TOKEN не задан. Задай переменную окружения BOT_TOKEN или впиши токен в код.")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()


# =========================
# START / MENU
# =========================
@dp.message(Command("start"))
@dp.message(Command("menu"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_in_admin_chat[message.from_user.id] = False

    text = (
        "Добро пожаловать в салон оптики!\n"
        "Онлайн-запись к врачу и контакты.\n\n"
        f"{WORK_HOURS_TEXT}\n\n"
        "Выберите действие ниже 👇"
    )
    await message.answer(text, reply_markup=kb_main())


# =========================
# MAIN MENU BUTTONS
# =========================
@dp.message(F.text == "🗓 Записаться к врачу")
async def btn_doctor(message: Message):
    user_in_admin_chat[message.from_user.id] = False
    # Сразу ссылка — без подменю
    await message.answer(
        "Нажмите кнопку ниже, чтобы выбрать дату и время.\n"
        "Если нужна помощь — напишите администратору.",
        reply_markup=kb_doctor_link(),
    )


@dp.message(F.text == "🎁 Акции и скидки")
async def btn_promos(message: Message):
    user_in_admin_chat[message.from_user.id] = False
    await message.answer("🎁 <b>Акции и скидки</b>\nВыберите акцию:", reply_markup=kb_promos())


@dp.message(F.text == "📦 Статус заказа")
async def btn_status(message: Message, state: FSMContext):
    user_in_admin_chat[message.from_user.id] = False
    await state.set_state(Flow.awaiting_phone)
    await message.answer(
        "📦 <b>Статус заказа</b>\n"
        "Введите номер телефона, который оставляли при заказе, в формате <b>+375XXXXXXXXX</b>.\n"
        "Пример: <code>+375291234567</code>\n\n"
        "Чтобы вернуться в меню: /menu"
    )


@dp.message(F.text == "📍 Адрес и контакты")
async def btn_contacts(message: Message):
    user_in_admin_chat[message.from_user.id] = False
    await message.answer(
        "📍 <b>Адрес и контакты</b>\nВыберите действие:",
        reply_markup=kb_contacts(),
    )


@dp.message(F.text == "💬 Написать администратору")
async def btn_admin_chat(message: Message, state: FSMContext):
    await state.clear()
    user_in_admin_chat[message.from_user.id] = True
    await message.answer(
        "✍️ Напишите, пожалуйста, сообщение — администратор ответит вам как можно скорее.\n\n"
        "Чтобы выйти в меню: /menu",
        reply_markup=None,
    )


# =========================
# STATUS FLOW (phone input)
# =========================
@dp.message(Flow.awaiting_phone)
async def status_phone_input(message: Message, state: FSMContext):
    phone = (message.text or "").strip().replace(" ", "")
    if not PHONE_RE.match(phone):
        await message.answer("❌ Неверный формат. Введите так: <b>+375XXXXXXXXX</b>")
        return

    order = await db_get_latest_order(phone)
    await state.clear()

    if not order:
        await message.answer(
            "🔎 Заказ по этому номеру не найден.\n"
            "Проверьте номер или напишите администратору.",
            reply_markup=kb_main(),
        )
        return

    status = order.get("status", "—")
    order_no = (order.get("order_no") or "").strip()
    comment = (order.get("comment") or "").strip()
    eta = (order.get("eta") or "").strip()
    updated_at = (order.get("updated_at") or "").strip()

    text = f"📦 <b>Статус заказа</b>: <b>{status}</b>\n"
    if order_no:
        text += f"🧾 Номер заказа: <b>{order_no}</b>\n"
    if comment:
        text += f"💬 Комментарий: {comment}\n"
    if eta:
        text += f"📅 Ориентировочная готовность: {eta}\n"
    if updated_at:
        text += f"🕒 Обновлено: {updated_at}\n"

    await message.answer(text, reply_markup=kb_main())


# =========================
# INLINE CALLBACKS
# =========================
@dp.callback_query(F.data == CB_BACK_MAIN)
async def cb_back_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_in_admin_chat[callback.from_user.id] = False
    await callback.message.answer("Выберите действие ниже 👇", reply_markup=kb_main())
    await callback.answer()


@dp.callback_query(F.data == CB_CONTACTS_CALL)
async def cb_contacts_call(callback: CallbackQuery):
    # Показываем красиво + кликабельный номер
    await callback.message.answer(
        f"📞 Телефон: {PHONE_PRETTY}\n{PHONE_CLICK}"
    )
    await callback.answer()


@dp.callback_query(F.data == CB_CONTACTS_HOURS)
async def cb_contacts_hours(callback: CallbackQuery):
    await callback.message.answer(WORK_HOURS_TEXT)
    await callback.answer()


@dp.callback_query(F.data == CB_PROMO_10)
async def cb_promo_10(callback: CallbackQuery):
    code = "PAN10-" + secrets.token_hex(2).upper()
    await callback.message.answer(
        "🏷 <b>-10% на комплект (оправа + линзы)</b>\n"
        f"Ваш купон: <code>{code}</code>\n"
        "Срок действия: 7 дней.\n"
        "Покажите купон на кассе."
    )
    await callback.answer()


@dp.callback_query(F.data == CB_PROMO_2ND30)
async def cb_promo_2nd30(callback: CallbackQuery):
    await callback.message.answer(
        "👓 <b>Вторая пара -30%</b>\n"
        "Скидка 30% на вторую пару.\n"
        "Уточните условия у администратора, если нужно."
    )
    await callback.answer()


@dp.callback_query(F.data == CB_PROMO_FAMILY)
async def cb_promo_family(callback: CallbackQuery):
    await callback.message.answer(
        "👨‍👩‍👧 <b>Семейная скидка</b>\n"
        "Скидка второму члену семьи в течение 14 дней.\n"
        "Подробности уточняйте у администратора."
    )
    await callback.answer()


@dp.callback_query(F.data == CB_PROMO_REF)
async def cb_promo_ref(callback: CallbackQuery):
    code = "FRIEND-" + secrets.token_hex(3).upper()
    await callback.message.answer(
        "🤝 <b>Приведи друга</b>\n"
        f"Ваш код: <code>{code}</code>\n"
        "Другу — скидка, вам — бонус.\n"
        "Сообщите код администратору при визите."
    )
    await callback.answer()


# =========================
# ADMIN SEND COMMAND: /to <user_id> <text>
# =========================
@dp.message(Command("to"))
async def cmd_to(message: Message):
    if not is_admin(message):
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Формат: /to <user_id> <текст>")
        return

    try:
        uid = int(parts[1])
    except ValueError:
        await message.answer("user_id должен быть числом.")
        return

    text = parts[2].strip()
    if not text:
        await message.answer("Текст пуст.")
        return

    await bot.send_message(uid, f"✅ Ответ администратора:\n\n{text}")
    await message.answer("✅ Отправлено клиенту.")


# =========================
# CATCH-ALL (чат с админом + ответы админа reply)
# =========================
@dp.message()
async def catch_all(message: Message, state: FSMContext):
    uid = message.from_user.id if message.from_user else 0

    # 1) Если пишет клиент и включен режим чата — пересылаем админу
    if not is_admin(message) and user_in_admin_chat.get(uid, False):
        header = (
            f"💬 <b>Сообщение от клиента</b>\n"
            f"👤 {message.from_user.full_name} "
            f"(id: <code>{uid}</code>)\n"
            f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            "— — —"
        )
        await bot.send_message(ADMIN_CHAT_ID, header)

        sent = await message.copy_to(ADMIN_CHAT_ID)
        forward_map[sent.message_id] = uid

        if CONFIRM_EACH_MESSAGE:
            await message.answer("✅ Спасибо! Сообщение отправлено администратору.")
        return

    # 2) Если админ отвечает reply на пересланное — отправляем клиенту
    if is_admin(message) and message.reply_to_message:
        replied_id = message.reply_to_message.message_id
        target_uid = forward_map.get(replied_id)
        if target_uid:
            await message.copy_to(target_uid)
            return

    # 3) Любой другой текст от клиента — мягко вернуть в меню
    if not is_admin(message):
        await state.clear()
        user_in_admin_chat[uid] = False
        await message.answer("Откройте меню: /menu", reply_markup=kb_main())


async def main():
    await db_init()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

