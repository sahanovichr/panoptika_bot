import asyncio
import re
from datetime import datetime
from typing import Optional, Dict

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

# =========================
# CONFIG — ЗАПОЛНИ ПОД СЕБЯ
# =========================
BOT_TOKEN = "8027908597:AAF-HcFE723DZbb6vPL7znowWanlNBEX3n8"

# ТВОЙ chat_id (или chat_id группы админов)
# Узнать можно через @userinfobot (или @getmyid_bot)
ADMIN_CHAT_ID = 6805556593  # <-- ты писал этот id, проверь

# Ссылка на онлайн-запись
DOCTOR_APPOINTMENT_URL = "https://online-zapis.com/online/00691"

# Яндекс.Карты (точка организации)
YANDEX_MAP_URL = "https://yandex.ru/maps/org/229002285621?si=r8mrjp7wcrya9x5p9a20t6qgc8"

# Instagram / сайт (если нужно — сейчас в контактах покажем инсту отдельной кнопкой)
INSTAGRAM_URL = "https://www.instagram.com/panoptika_brest?igsh=MTlmYndrbXlwZ3hmbA=="
WEBSITE_URL = "https://panoptika.by/"

# Адрес / телефон / график
PHONE_NUMBER_CLICK = "+3753365188747"      # кликабельный вариант (цифры)
PHONE_NUMBER_PRETTY = "+375 33 651-87-47"  # красивый в тексте

WORK_HOURS_TEXT = (
    "Пн–Пт 10:00–20:00\n"
    "Сб–Вс 10:00–18:00"
)

ADDRESS_TEXT = "Брест, ул. Пушкинская 6/1"

CB_CONTACTS_CALL = "contacts_call"
CB_CONTACTS_HOURS = "contacts_hours"
CB_BACK_MAIN = "back_main"


# SQLite база
DB_PATH = "panoptika.db"

# Если True — пользователю будет приходить "✅ Отправлено админу" на каждое сообщение
CONFIRM_EACH_MESSAGE_TO_USER = False

# =========================
# VALIDATION
# =========================
PHONE_RE = re.compile(r"^\+375\d{9}$")  # +375XXXXXXXXX (9 цифр после 375)
STATUSES = {"Принят", "В работе", "Готов", "Выдан"}

# =========================
# FSM
# =========================
class Flow(StatesGroup):
    awaiting_phone = State()

# =========================
# IN-MEMORY ROUTING
# =========================
# пользователь в режиме "чат с админом"
user_in_admin_chat: Dict[int, bool] = {}

# message_id в админ-чате -> user_id (чтобы админ отвечал reply и сообщение ушло клиенту)
forward_map: Dict[int, int] = {}

# =========================
# KEYBOARDS
# =========================
def kb_main() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🗓 Записаться к врачу")],
            [KeyboardButton(text="🎁 Акции и скидки"), KeyboardButton(text="📦 Статус заказа")],
            [KeyboardButton(text="📍 Адрес и контакты"), KeyboardButton(text="💬 Написать администратору")],
        ],
        resize_keyboard=True,
        selective=True,
    )



def kb_back_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="↩️ Назад в меню")]],
        resize_keyboard=True,
        selective=True,
    )

def kb_status_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Проверить по телефону")],
            [KeyboardButton(text="↩️ Назад в меню")],
        ],
        resize_keyboard=True,
        selective=True,
    )

def kb_doctor_link() -> InlineKeyboardMarkup:
    # одна кнопка, никаких подменю
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗓 Открыть онлайн-запись", url=DOCTOR_APPOINTMENT_URL)],
            [InlineKeyboardButton(text="↩️ Назад в меню", callback_data="back_main")],
        ]
    )

def kb_promos() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏷 -10% на комплект (оправа + линзы)", callback_data="promo_10")],
            [InlineKeyboardButton(text="👓 Вторая пара -30%", callback_data="promo_second30")],
            [InlineKeyboardButton(text="👨‍👩‍👧 Семейная скидка", callback_data="promo_family")],
            [InlineKeyboardButton(text="🤝 Приведи друга", callback_data="promo_ref")],
            [InlineKeyboardButton(text="↩️ Назад в меню", callback_data="back_main")],
        ]
    )

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def kb_contacts() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗺 Как добраться (карта)", url=YANDEX_MAP_URL)],
        [InlineKeyboardButton(text="📞 Позвонить", callback_data=CB_CONTACTS_CALL)],
        [InlineKeyboardButton(text="🕒 Время работы", callback_data=CB_CONTACTS_HOURS)],
        [InlineKeyboardButton(text="↩️ Назад", callback_data=CB_BACK_MAIN)],
    ])
        ]
    )

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

# опционально: тестовая вставка заказа (можешь потом удалить)
async def db_add_demo(phone: str, status: str, order_no: str = "", comment: str = "", eta: str = "") -> None:
    if status not in STATUSES:
        raise ValueError("Invalid status")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO orders(phone, order_no, status, comment, eta, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (phone, order_no, status, comment, eta, datetime.now().isoformat(timespec="seconds")),
        )
        await db.commit()

# =========================
# BOT
# =========================
from aiogram.client.default import DefaultBotProperties

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()

def is_admin(message: Message) -> bool:
    return bool(message.chat and message.chat.id == ADMIN_CHAT_ID)

def normalize_phone(s: str) -> str:
    return (s or "").strip().replace(" ", "").replace("-", "")

# ---- START / MENU ----
@dp.message(Command("start"))
@dp.message(Command("menu"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_in_admin_chat[message.from_user.id] = False
    await message.answer(
        "👓 <b>ПанОптика</b>\n"
        "Онлайн-запись к врачу и контакты.\n\n"
        f"⏰ <b>Время работы</b>: {WORK_HOURS_TEXT}\n\n"
        "Выберите действие ниже 👇",
        reply_markup=kb_main(),
    )

# ---- 1) DOCTOR ----
@dp.message(F.text == "🗓 Записаться к врачу")
async def doctor_button(message: Message) -> None:
    user_in_admin_chat[message.from_user.id] = False
    await message.answer(
        "Нажмите кнопку ниже, чтобы выбрать дату и время.\n"
        "Если нужна помощь — напишите администратору.",
        reply_markup=kb_doctor_link(),
    )

# ---- 2) PROMOS ----
@dp.message(F.text == "🎁 Акции и скидки")
async def promos_button(message: Message) -> None:
    user_in_admin_chat[message.from_user.id] = False
    await message.answer(
        "🎁 <b>Акции месяца</b>\nВыберите интересующую акцию:",
        reply_markup=kb_promos(),
    )

@dp.callback_query(F.data == "promo_10")
async def cb_promo_10(callback: CallbackQuery) -> None:
    # пока просто промокод (дальше сделаем ограничения)
    promo = "PAN10"
    await callback.message.answer(
        "🏷 <b>-10% на комплект (оправа + линзы)</b>\n"
        f"Промокод: <code>{promo}</code>\n"
        "Срок действия: 7 дней.",
    )
    await callback.answer()

@dp.callback_query(F.data == "promo_second30")
async def cb_promo_second30(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "👓 <b>Вторая пара -30%</b>\n"
        "Условия: в течение 14 дней после первой покупки (уточним/зафиксируем позже)."
    )
    await callback.answer()

@dp.callback_query(F.data == "promo_family")
async def cb_promo_family(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "👨‍👩‍👧 <b>Семейная скидка</b>\n"
        "Пример: -15% второму члену семьи в течение 14 дней (можно изменить)."
    )
    await callback.answer()

@dp.callback_query(F.data == "promo_ref")
async def cb_promo_ref(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "🤝 <b>Приведи друга</b>\n"
        "Скоро добавим уникальный реферальный код.\n"
        "Другу — скидка, вам — бонус."
    )
    await callback.answer()

# ---- 3) STATUS ----
@dp.message(F.text == "📦 Статус заказа")
async def status_button(message: Message, state: FSMContext) -> None:
    user_in_admin_chat[message.from_user.id] = False
    await state.clear()
    await message.answer(
        "📦 Проверка статуса заказа.\nНажмите «Проверить по телефону».",
        reply_markup=kb_status_menu(),
    )

@dp.message(F.text == "📱 Проверить по телефону")
async def ask_phone(message: Message, state: FSMContext) -> None:
    await state.set_state(Flow.awaiting_phone)
    await message.answer(
        "Введите номер телефона, который оставляли при заказе\n"
        "в формате <b>+375XXXXXXXXX</b> (например, +375291234567):",
        reply_markup=kb_status_menu(),
    )

@dp.message(Flow.awaiting_phone)
async def handle_phone_input(message: Message, state: FSMContext) -> None:
    phone = normalize_phone(message.text)
    if not PHONE_RE.match(phone):
        await message.answer("❌ Неверный формат. Введите телефон так: <b>+375XXXXXXXXX</b>")
        return

    order = await db_get_latest_order(phone)
    await state.clear()

    if not order:
        await message.answer(
            "🔎 Заказ по этому номеру не найден.\n"
            "Проверьте номер или напишите администратору.",
            reply_markup=kb_status_menu(),
        )
        return

    status = order.get("status", "—")
    order_no = (order.get("order_no") or "").strip()
    comment = (order.get("comment") or "").strip()
    eta = (order.get("eta") or "").strip()

    text = f"📦 <b>Статус заказа</b>: <b>{status}</b>\n"
    if order_no:
        text += f"🧾 Номер заказа: <b>{order_no}</b>\n"
    if comment:
        text += f"💬 Комментарий: {comment}\n"
    if eta:
        text += f"📅 Ориентировочная готовность: {eta}\n"

    await message.answer(text, reply_markup=kb_status_menu())

# ---- 4) CONTACTS ----
@dp.message(F.text == "📍 Адрес и контакты")
async def contacts_button(message: Message) -> None:
    text = (
        "📍 Адрес и контакты\n\n"
        f"{ADDRESS_TEXT}\n"
        f"{PHONE_NUMBER_PRETTY}\n\n"
        "Выберите действие ниже 👇"
    )
    await message.answer(text, reply_markup=kb_contacts(), disable_web_page_preview=True)

    )

@dp.callback_query(F.data == "work_hours")
async def cb_work_hours(callback: CallbackQuery) -> None:
    await callback.message.answer(f"🕒 <b>Время работы</b>\n{WORK_HOURS_TEXT}")
    await callback.answer()

@dp.callback_query(F.data == CB_CONTACTS_CALL)
async def cb_contacts_call(callback: CallbackQuery) -> None:
    await callback.message.answer(f"📞 Телефон: {PHONE_NUMBER_PRETTY}\n{PHONE_NUMBER_CLICK}")
    await callback.answer()

@dp.callback_query(F.data == CB_CONTACTS_HOURS)
async def cb_contacts_hours(callback: CallbackQuery) -> None:
    await callback.message.answer(f"⏰ Время работы:\n{WORK_HOURS_TEXT}")
    await callback.answer()

@dp.callback_query(F.data == CB_BACK_MAIN)
async def cb_back_main(callback: CallbackQuery) -> None:
    await callback.message.answer("Главное меню:", reply_markup=kb_main())
    await callback.answer()



# ---- BACK TO MENU ----
@dp.callback_query(F.data == "back_main")
async def cb_back_main(callback: CallbackQuery) -> None:
    user_in_admin_chat[callback.from_user.id] = False
    await callback.message.answer("Главное меню:", reply_markup=kb_main())
    await callback.answer()

@dp.message(F.text == "↩️ Назад в меню")
async def back_to_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_in_admin_chat[message.from_user.id] = False
    await message.answer("Главное меню:", reply_markup=kb_main())

# ---- 5) CHAT WITH ADMIN ----
@dp.message(F.text == "💬 Написать администратору")
async def admin_chat_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_in_admin_chat[message.from_user.id] = True
    await message.answer(
        "💬 Напишите, пожалуйста, сообщение — администратор ответит вам как можно скорее.\n\n"
        "Чтобы вернуться в меню, отправьте: <code>/menu</code>",
        reply_markup=None,
    )

# ---- CATCH ALL: route chat messages ----
@dp.message()
async def catch_all(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id

    # 1) Клиент в режиме чата — пересылаем админу
    if user_in_admin_chat.get(uid, False) and not is_admin(message):
        header = (
            f"💬 <b>Сообщение клиента</b>\n"
            f"👤 {message.from_user.full_name} (id: <code>{uid}</code>)\n"
            f"— — —"
        )
        await bot.send_message(ADMIN_CHAT_ID, header)

        sent = await message.copy_to(ADMIN_CHAT_ID)
        forward_map[sent.message_id] = uid

        if CONFIRM_EACH_MESSAGE_TO_USER:
            await message.answer("✅ Отправлено администратору.")
        return

    # 2) Админ отвечает reply на пересланное — отправляем клиенту
    if is_admin(message) and message.reply_to_message:
        replied_id = message.reply_to_message.message_id
        target_uid = forward_map.get(replied_id)
        if target_uid:
            await message.copy_to(target_uid)
            return

    # 3) Любые “непонятные” сообщения — вернуть меню
    if not is_admin(message):
        await state.clear()
        user_in_admin_chat[uid] = False
        await message.answer("Откройте меню командой /menu", reply_markup=kb_main())

# =========================
# RUN
# =========================
async def main() -> None:
    await db_init()

    # --- ДЕМО ДЛЯ ПРОВЕРКИ "СТАТУС ЗАКАЗА" (можешь убрать) ---
    # await db_add_demo("+375336518747", "В работе", order_no="29/01-001", comment="Ожидаем линзы", eta="03.02.2026")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
