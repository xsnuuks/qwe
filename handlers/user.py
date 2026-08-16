from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_ID, PRICE_NORMAL, PRICE_DISCOUNT
from database import (
    get_user, create_user, update_user_language, set_referrer,
    get_all_products, get_product, create_order, use_discount
)
from keyboards import (
    language_keyboard, main_menu_keyboard, catalog_keyboard,
    product_keyboard, back_keyboard
)
from locales import get_text

router = Router()


class SupportState(StatesGroup):
    waiting_message = State()


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
        await message.answer(
            get_text("ru", "choose_language"),
            reply_markup=language_keyboard()
        )
        return

    lang = existing["language"]
    if referrer_id and not existing.get("referrer_id"):
        await set_referrer(user_id, referrer_id)

    await message.answer(
        get_text(lang, "welcome"),
        reply_markup=main_menu_keyboard(lang, is_admin(user_id)),
        parse_mode="HTML"
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
        reply_markup=language_keyboard()
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


@router.message(F.chat.type == "private", F.from_user.id != ADMIN_ID)
async def forward_to_admin(message: Message, bot: Bot, lang: str):
    menu_texts = [
        "🛍 Каталог", "🛍 Catalog", "🛍 Katalog",
        "👤 Профиль", "👤 Profile", "👤 Profil",
        "🔗 Реферальная программа", "🔗 Referral program", "🔗 Empfehlungsprogramm",
        "📜 Правила", "📜 Rules", "📜 Regeln",
        "💬 Поддержка", "💬 Support",
        "🌐 Язык", "🌐 Language", "🌐 Sprache",
        "🔧 Админ-панель", "🔧 Admin panel", "🔧 Admin-Panel",
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
