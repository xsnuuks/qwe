from aiogram.dispatcher.event.bases import SkipHandler
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, WebAppInfo
from aiogram.filters import CommandStart, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_ID, PRICE_NORMAL, PRICE_DISCOUNT
from database import (
    get_user, create_user, update_user_language, set_referrer,
    get_all_products, get_product, create_order, use_discount,
    add_to_cart, get_cart, remove_from_cart, update_cart_quantity,
    clear_cart, get_cart_count, set_referrer_if_empty,
)
from keyboards import (
    language_keyboard, main_menu_keyboard, catalog_keyboard,
    product_keyboard, back_keyboard, cart_keyboard, city_keyboard
)
from locales import get_text

router = Router()


class SupportState(StatesGroup):
    waiting_message = State()


class CheckoutState(StatesGroup):
    city = State()
    place = State()


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, bot: Bot, lang: str = "ru"):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name or ""

    referrer_id = None
    if command.args and command.args.startswith("ref_"):
        try:
            referrer_id = int(command.args.split("_")[1])
            if referrer_id == user_id:
                referrer_id = None
        except (ValueError, IndexError):
            referrer_id = None

    existing = await get_user(user_id)
    if not existing:
        await create_user(user_id, username, full_name, "ru", referrer_id)
    elif referrer_id:
        try:
            await set_referrer_if_empty(user_id, referrer_id)
        except Exception:
            try:
                await set_referrer(user_id, referrer_id)
            except Exception:
                pass

        kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть магазин",
                    web_app=WebAppInfo(url="https://mono-miniapp.vercel.app"),
                )
            ]
        ]
    )
    await message.answer(
        "Добро пожаловать в MONO.\n\n"
        "Минимализм. Качество. Только проверенные жидкости.\n\n"
        "Откройте мини-приложение, чтобы посмотреть каталог и оформить заказ.",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("lang_"))
async def set_language(callback: CallbackQuery):
    lang_code = callback.data.split("_")[1]
    user_id = callback.from_user.id
    await update_user_language(user_id, lang_code)
    await callback.message.edit_text(get_text(lang_code, "language_set"))
    await callback.message.answer(
        get_text(lang_code, "welcome"),
        reply_markup=main_menu_keyboard(lang_code, is_admin(user_id)),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(F.text.in_(["🌐 Язык", "🌐 Language", "🌐 Sprache"]))
async def change_language(message: Message):
    await message.answer(
        get_text("ru", "choose_language"),
        reply_markup=ReplyKeyboardRemove()
    )


@router.message(F.text.in_(["🛍 Каталог", "🛍 Catalog", "🛍 Katalog"]))
async def show_catalog(message: Message, lang: str):
    products = await get_all_products(only_available=True)
    if not products:
        await message.answer(get_text(lang, "no_products"))
        return
    await message.answer(
        get_text(lang, "catalog"),
        reply_markup=catalog_keyboard(lang, products)
    )


@router.callback_query(F.data == "back_catalog")
@router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery, lang: str):
    await callback.message.delete()
    await callback.message.answer(
        get_text(lang, "main_menu"),
        reply_markup=main_menu_keyboard(lang, is_admin(callback.from_user.id))
    )
    await callback.answer()


@router.callback_query(F.data.startswith("product_"))
async def show_product(callback: CallbackQuery, lang: str):
    product_id = int(callback.data.split("_")[1])
    product = await get_product(product_id)
    if not product:
        await callback.answer("Not found", show_alert=True)
        return

    user = await get_user(callback.from_user.id)
    has_discount = user and user.get("has_discount")

    if has_discount:
        price_str = get_text(lang, "price_discount", old=int(product["price"]), new=PRICE_DISCOUNT)
    else:
        price_str = get_text(lang, "price_normal", price=int(product["price"]))

    text = get_text(
        lang, "product_card",
        name=product["name"],
        description=product["description"] or "",
        volume=product["volume"] or "—",
        strength=product["strength"] or "—",
        price=price_str
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    if product.get("photo_file_id"):
        await callback.message.answer_photo(
            photo=product["photo_file_id"],
            caption=text,
            reply_markup=product_keyboard(lang, product_id),
            parse_mode="HTML"
        )
    else:
        await callback.message.answer(
            text,
            reply_markup=product_keyboard(lang, product_id),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data.startswith("buy_"))
async def buy_product(callback: CallbackQuery, bot: Bot, lang: str):
    product_id = int(callback.data.split("_")[1])
    product = await get_product(product_id)
    if not product:
        await callback.answer("Not found", show_alert=True)
        return

    user = await get_user(callback.from_user.id)
    has_discount = bool(user and user.get("has_discount"))
    used_discount = False

    if has_discount:
        await use_discount(callback.from_user.id)
        used_discount = True

    await create_order(callback.from_user.id, product_id, used_discount)

    name = callback.from_user.full_name or "—"
    username = callback.from_user.username or "—"
    discount_text = "Да (10€)" if used_discount else "Нет"

    admin_text = get_text(
        "ru", "admin_new_order",
        name=name,
        username=username,
        user_id=callback.from_user.id,
        product=product["name"],
        discount=discount_text
    )
    try:
        await bot.send_message(
            ADMIN_ID,
            admin_text + "\n\n" + get_text("ru", "reply_hint"),
            parse_mode="HTML"
        )
    except Exception:
        pass

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        get_text(lang, "buy_request_sent"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(F.text.in_(["👤 Профиль", "👤 Profile", "👤 Profil"]))
async def show_profile(message: Message, lang: str):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Error")
        return

    progress = user.get("successful_referrals", 0)
    discount_status = get_text(lang, "discount_yes") if user.get("has_discount") else get_text(lang, "discount_no")

    text = get_text(
        lang, "profile_text",
        purchases=user.get("purchases_count", 0),
        referrals=progress,
        progress=progress,
        discount_status=discount_status
    )
    await message.answer(text, parse_mode="HTML")


@router.message(F.text.in_(["🔗 Реферальная программа", "🔗 Referral program", "🔗 Empfehlungsprogramm"]))
async def show_referral(message: Message, bot: Bot, lang: str):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{message.from_user.id}"
    text = get_text(lang, "referral_text", link=link)
    await message.answer(text, parse_mode="HTML")


@router.message(F.text.in_(["📜 Правила", "📜 Rules", "📜 Regeln"]))
async def show_rules(message: Message, lang: str):
    await message.answer(get_text(lang, "rules_text"), parse_mode="HTML")


@router.message(F.text.in_(["💬 Поддержка", "💬 Support"]))
async def support_start(message: Message, state: FSMContext, lang: str):
    await message.answer(get_text(lang, "support_text"))
    await state.set_state(SupportState.waiting_message)


@router.message(SupportState.waiting_message)
async def support_message(message: Message, state: FSMContext, bot: Bot, lang: str):
    if message.text and message.text.startswith("/"):
        await state.clear()
        return

    name = message.from_user.full_name or "—"
    username = message.from_user.username or "—"
    text = message.text or "(media)"

    admin_text = get_text(
        "ru", "admin_new_message",
        name=name,
        username=username,
        user_id=message.from_user.id,
        text=text
    )
    try:
        await bot.send_message(
            ADMIN_ID,
            admin_text + "\n\n" + get_text("ru", "reply_hint"),
            parse_mode="HTML"
        )
    except Exception:
        pass

    await message.answer(get_text(lang, "support_sent"))
    await state.clear()


# ========== КОРЗИНА ==========

@router.callback_query(F.data.startswith("cart_add_"))
async def cart_add(callback: CallbackQuery, lang: str):
    product_id = int(callback.data.split("_")[2])
    await add_to_cart(callback.from_user.id, product_id)
    await callback.answer("✅ Добавлено в корзину", show_alert=False)


@router.message(F.text == "🛒 \u041a\u043e\u0440\u0437\u0438\u043d\u0430")
async def show_cart(message: Message, lang: str):
    cart = await get_cart(message.from_user.id)
    if not cart:
        await message.answer("🛒 Корзина пуста")
        return
    total = sum(item["price"] * item["quantity"] for item in cart)
    text = "🛒 Ваша корзина:\n\n"
    for item in cart:
        text += f"• {item['name']} × {item['quantity']} = {item['price'] * item['quantity']}€\n"
    text += f"\nИтого: {total}€"
    await message.answer(text, reply_markup=cart_keyboard(lang, cart))


@router.callback_query(F.data.startswith("cart_plus_"))
async def cart_plus(callback: CallbackQuery, lang: str):
    product_id = int(callback.data.split("_")[2])
    cart = await get_cart(callback.from_user.id)
    current = next((i["quantity"] for i in cart if i["product_id"] == product_id), 0)
    await update_cart_quantity(callback.from_user.id, product_id, current + 1)
    await show_cart_callback(callback, lang)


@router.callback_query(F.data.startswith("cart_minus_"))
async def cart_minus(callback: CallbackQuery, lang: str):
    product_id = int(callback.data.split("_")[2])
    cart = await get_cart(callback.from_user.id)
    current = next((i["quantity"] for i in cart if i["product_id"] == product_id), 0)
    await update_cart_quantity(callback.from_user.id, product_id, current - 1)
    await show_cart_callback(callback, lang)


@router.callback_query(F.data.startswith("cart_remove_"))
async def cart_remove(callback: CallbackQuery, lang: str):
    product_id = int(callback.data.split("_")[2])
    await remove_from_cart(callback.from_user.id, product_id)
    await show_cart_callback(callback, lang)


@router.callback_query(F.data == "cart_clear")
async def cart_clear_handler(callback: CallbackQuery, lang: str):
    await clear_cart(callback.from_user.id)
    await callback.message.edit_text("🛒 Корзина очищена")
    await callback.answer()


async def show_cart_callback(callback: CallbackQuery, lang: str):
    cart = await get_cart(callback.from_user.id)
    if not cart:
        await callback.message.edit_text("🛒 Корзина пуста")
        await callback.answer()
        return
    total = sum(item["price"] * item["quantity"] for item in cart)
    text = "🛒 Ваша корзина:\n\n"
    for item in cart:
        text += f"• {item['name']} × {item['quantity']} = {item['price'] * item['quantity']}€\n"
    text += f"\nИтого: {total}€"
    await callback.message.edit_text(text, reply_markup=cart_keyboard(lang, cart))
    await callback.answer()


# ========== ОФОРМЛЕНИЕ ==========

@router.callback_query(F.data == "cart_checkout")
async def cart_checkout_start(callback: CallbackQuery, state: FSMContext, lang: str):
    cart = await get_cart(callback.from_user.id)
    if not cart:
        await callback.answer("Корзина пуста", show_alert=True)
        return
    await callback.message.edit_text("📍 Выберите город:", reply_markup=city_keyboard())
    await state.set_state(CheckoutState.city)
    await callback.answer()


@router.callback_query(F.data.startswith("city_"), CheckoutState.city)
async def process_city(callback: CallbackQuery, state: FSMContext, lang: str):
    city = callback.data.split("_", 1)[1]
    await state.update_data(city=city)
    await callback.message.edit_text(
        f"Город: {city}\n\n"
        "Напишите одним сообщением:\n"
        "1. Место встречи\n"
        "2. Время\n"
        "3. Комментарий (или -)\n\n"
        "Пример:\nHauptbahnhof\nсегодня 18:30\n-"
    )
    await state.set_state(CheckoutState.place)
    await callback.answer()


@router.message(CheckoutState.place)
async def process_place(message: Message, state: FSMContext, lang: str):
    lines = (message.text or "").strip().split("\n")
    place = lines[0] if len(lines) > 0 else ""
    time = lines[1] if len(lines) > 1 else ""
    comment = lines[2] if len(lines) > 2 else "—"
    if comment == "-":
        comment = "—"

    await state.update_data(place=place, time=time, comment=comment)
    data = await state.get_data()
    cart = await get_cart(message.from_user.id)

    if not cart:
        await message.answer("Корзина пуста")
        await state.clear()
        return

    total = sum(item["price"] * item["quantity"] for item in cart)
    city = data.get("city", "")

    text = "🛒 Ваш заказ\n\n"
    for item in cart:
        text += f"• {item['name']} × {item['quantity']} = {item['price'] * item['quantity']}€\n"
    text += f"\nИтого: {total}€\n"
    text += f"📍 {city}"
    if place:
        text += f", {place}"
    text += f"\n🕒 {time}\n💬 {comment}\n\nВсё верно?"

    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить заказ", callback_data="cart_confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cart_cancel")]
        ])
    )


@router.callback_query(F.data == "cart_confirm")
async def cart_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot, lang: str):
    data = await state.get_data()
    cart = await get_cart(callback.from_user.id)
    user = callback.from_user

    if not cart:
        await callback.answer("Корзина пуста", show_alert=True)
        await state.clear()
        return

    total = sum(item["price"] * item["quantity"] for item in cart)
    city = data.get("city", "")
    place = data.get("place", "")
    time = data.get("time", "")
    comment = data.get("comment", "—")

    for item in cart:
        await create_order(user.id, item["product_id"])

    await clear_cart(user.id)
    await state.clear()

    admin_text = (
        f"🛒 Новый заказ из корзины\n\n"
        f"От: {user.full_name} (@{user.username or '—'})\n"
        f"ID: {user.id}\n\n"
    )
    for item in cart:
        admin_text += f"• {item['name']} × {item['quantity']} = {item['price'] * item['quantity']}€\n"
    admin_text += f"\nИтого: {total}€\n📍 {city}"
    if place:
        admin_text += f", {place}"
    admin_text += f"\n🕒 {time}\n💬 {comment}"

    try:
        await bot.send_message(ADMIN_ID, admin_text)
    except Exception:
        pass

    await callback.message.edit_text("✅ Заказ оформлен!\nАдминистратор скоро свяжется с вами.")
    await callback.answer()


@router.callback_query(F.data == "cart_cancel")
async def cart_cancel(callback: CallbackQuery, state: FSMContext, lang: str):
    await state.clear()
    await callback.message.edit_text("Заказ отменён")
    await callback.answer()


# ========== ПЕРЕСЫЛКА СООБЩЕНИЙ АДМИНУ (в самом конце!) ==========

@router.message(F.chat.type == "private", F.from_user.id != ADMIN_ID, StateFilter(None))
async def forward_to_admin(message: Message, bot: Bot, lang: str):
    menu_texts = [
        "🛍 Каталог", "🛍 Catalog", "🛍 Katalog",
        "👤 Профиль", "👤 Profile", "👤 Profil",
        "🔗 Реферальная программа", "🔗 Referral program", "🔗 Empfehlungsprogramm",
        "📜 Правила", "📜 Rules", "📜 Regeln",
        "💬 Поддержка", "💬 Support",
        "🌐 Язык", "🌐 Language", "🌐 Sprache",
        "🔧 Админ-панель", "🔧 Admin panel", "🔧 Admin-Panel",
        "Корзина", "🛒 \u041a\u043e\u0440\u0437\u0438\u043d\u0430",
    ]
    if message.text in menu_texts:
        return

    name = message.from_user.full_name or "—"
    username = message.from_user.username or "—"
    text = message.text or "(media/file)"

    admin_text = get_text(
        "ru", "admin_new_message",
        name=name,
        username=username,
        user_id=message.from_user.id,
        text=text
    )
    try:
        await bot.send_message(
            ADMIN_ID,
            admin_text + "\n\n" + get_text("ru", "reply_hint"),
            parse_mode="HTML"
        )
    except Exception:
        pass
