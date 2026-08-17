from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Filter

from config import ADMIN_ID
from database import (
    get_stats, get_pending_orders, complete_order, get_all_products,
    add_product, get_user, increment_referrals, get_product, update_product,
    get_all_user_ids, get_users_page, get_users_count, set_user_blocked
)
from keyboards import (
    admin_menu_keyboard, products_admin_keyboard,
    order_actions_keyboard, main_menu_keyboard, back_keyboard,
    cancel_keyboard, users_list_keyboard
)
from locales import get_text

router = Router()


class IsAdmin(Filter):
    async def __call__(self, message: Message | CallbackQuery) -> bool:
        user = message.from_user if isinstance(message, Message) else message.from_user
        return user.id == ADMIN_ID


class AddProductState(StatesGroup):
    name = State()
    description = State()
    volume = State()
    strength = State()
    price = State()
    photo = State()


class AddReferralState(StatesGroup):
    user_id = State()
class BroadcastState(StatesGroup):
    message = State()


@router.message(F.text.in_(["🔧 Админ-панель", "🔧 Admin panel", "🔧 Admin-Panel"]), IsAdmin())
async def admin_panel(message: Message, lang: str):
    await message.answer(
        get_text(lang, "admin_menu"),
        reply_markup=admin_menu_keyboard(lang)
    )


@router.callback_query(F.data == "admin_menu", IsAdmin())
async def admin_menu_cb(callback: CallbackQuery, lang: str):
    await callback.message.edit_text(
        get_text(lang, "admin_menu"),
        reply_markup=admin_menu_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data == "admin_stats", IsAdmin())
async def admin_stats(callback: CallbackQuery, lang: str):
    stats = await get_stats()
    text = get_text(
        lang, "stats_text",
        users=stats["users"],
        orders=stats["orders"],
        products=stats["products"]
    )
    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard(lang, "admin_menu"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_orders", IsAdmin())
async def admin_orders(callback: CallbackQuery, lang: str):
    orders = await get_pending_orders()
    if not orders:
        await callback.message.edit_text(
            get_text(lang, "no_orders"),
            reply_markup=back_keyboard(lang, "admin_menu")
        )
        await callback.answer()
        return

    for order in orders[:10]:
        discount = "Да" if order.get("used_discount") else "Нет"
        text = get_text(
            lang, "order_item",
            id=order["id"],
            name=order.get("full_name") or "—",
            username=order.get("username") or "—",
            product=order.get("product_name") or "—",
            discount=discount,
            status=order.get("status", "pending")
        )
        await callback.message.answer(
            text,
            reply_markup=order_actions_keyboard(lang, order["id"]),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("complete_order_"), IsAdmin())
async def complete_order_cb(callback: CallbackQuery, lang: str):
    order_id = int(callback.data.split("_")[2])
    success = await complete_order(order_id)
    if success:
        await callback.message.edit_text(
            get_text(lang, "order_completed", id=order_id)
        )
    else:
        await callback.answer("Error", show_alert=True)
    await callback.answer()


@router.callback_query(F.data == "admin_products", IsAdmin())
async def admin_products(callback: CallbackQuery, lang: str):
    products = await get_all_products(only_available=False)
    if not products:
        await callback.message.edit_text(
            "Нет товаров. Добавьте первый.",
            reply_markup=back_keyboard(lang, "admin_menu")
        )
    else:
        await callback.message.edit_text(
            get_text(lang, "admin_products"),
            reply_markup=products_admin_keyboard(lang, products)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_toggle_"), IsAdmin())
async def admin_toggle_product(callback: CallbackQuery, lang: str):
    product_id = int(callback.data.split("_")[2])
    product = await get_product(product_id)
    if not product:
        await callback.answer("Not found", show_alert=True)
        return

    new_status = 0 if product["is_available"] else 1
    await update_product(product_id, is_available=new_status)
    
    status_text = "в наличии ✅" if new_status else "нет в наличии ❌"
    await callback.answer(f"{product['name']} — {status_text}")

    products = await get_all_products(only_available=False)
    await callback.message.edit_text(
        get_text(lang, "admin_products"),
        reply_markup=products_admin_keyboard(lang, products)
    )


@router.callback_query(F.data == "admin_add_product", IsAdmin())
async def admin_add_product_start(callback: CallbackQuery, state: FSMContext, lang: str):
    await callback.message.edit_text(
    get_text(lang, "enter_product_name"),
    reply_markup=cancel_keyboard()
)
    await state.set_state(AddProductState.name)
    await callback.answer()


@router.message(AddProductState.name, IsAdmin())
async def process_product_name(message: Message, state: FSMContext, lang: str):
    await state.update_data(name=message.text)
    await message.answer(
    get_text(lang, "enter_product_desc"),
    reply_markup=cancel_keyboard()
)
    await state.set_state(AddProductState.description)


@router.message(AddProductState.description, IsAdmin())
async def process_product_desc(message: Message, state: FSMContext, lang: str):
    desc = message.text if message.text != "-" else ""
    await state.update_data(description=desc)
    await message.answer(
    get_text(lang, "enter_product_volume"),
    reply_markup=cancel_keyboard()
)
    await state.set_state(AddProductState.volume)


@router.message(AddProductState.volume, IsAdmin())
async def process_product_volume(message: Message, state: FSMContext, lang: str):
    await state.update_data(volume=message.text)
    await message.answer(
    get_text(lang, "enter_product_strength"),
    reply_markup=cancel_keyboard()
)
    await state.set_state(AddProductState.strength)


@router.message(AddProductState.strength, IsAdmin())
async def process_product_strength(message: Message, state: FSMContext, lang: str):
    await state.update_data(strength=message.text)
    await message.answer(
    get_text(lang, "enter_product_price"),
    reply_markup=cancel_keyboard()
)
    await state.set_state(AddProductState.price)


@router.message(AddProductState.price, IsAdmin())
async def process_product_price(message: Message, state: FSMContext, lang: str):
    try:
        price = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Введите число, например 15")
        return

    await state.update_data(price=price)
    await message.answer(
    "Отправьте фото товара (или напишите «-» чтобы пропустить):",
    reply_markup=cancel_keyboard()
)
    await state.set_state(AddProductState.photo)


@router.message(AddProductState.photo, IsAdmin())
async def process_product_photo(message: Message, state: FSMContext, lang: str):
    photo_file_id = None
    if message.photo:
        photo_file_id = message.photo[-1].file_id
    elif message.text and message.text.strip() != "-":
        await message.answer("Отправьте фото или напишите «-»")
        return

    data = await state.get_data()
    await add_product(
        name=data["name"],
        description=data.get("description", ""),
        price=data["price"],
        volume=data.get("volume", "30ML"),
        strength=data.get("strength", "50MG"),
        photo_file_id=photo_file_id
    )
    await state.clear()
    await message.answer(
        get_text(lang, "product_added", name=data["name"]),
        reply_markup=main_menu_keyboard(lang, is_admin=True)
    )


@router.callback_query(F.data == "admin_add_referral", IsAdmin())
async def admin_add_referral_start(callback: CallbackQuery, state: FSMContext, lang: str):
    await callback.message.edit_text(
    get_text(lang, "enter_user_id_referral"),
    reply_markup=cancel_keyboard()
)
    await state.set_state(AddReferralState.user_id)
    await callback.answer()


@router.message(AddReferralState.user_id, IsAdmin())
async def process_add_referral(message: Message, state: FSMContext, lang: str):
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("Введите числовой ID")
        return

    user = await get_user(target_id)
    if not user:
        await message.answer(get_text(lang, "user_not_found"))
        await state.clear()
        return

    await increment_referrals(target_id)
    await state.clear()
    await message.answer(
        get_text(lang, "referral_added", user_id=target_id),
        reply_markup=main_menu_keyboard(lang, is_admin=True)
    )


@router.message(IsAdmin(), F.reply_to_message)
async def admin_reply_to_user(message: Message, bot: Bot, lang: str):
    replied = message.reply_to_message
    if not replied or not replied.text:
        return

    import re
    match = re.search(r"ID: <code>(\d+)</code>", replied.text) or re.search(r"ID: (\d+)", replied.text)
    if not match:
        match = re.search(r"ID:\s*`?(\d+)`?", replied.text)
    if not match:
        return

    target_user_id = int(match.group(1))
    text = message.text or ""

    try:
        await bot.send_message(
            target_user_id,
            get_text("ru", "message_from_admin", text=text),
            parse_mode="HTML"
        )
        await message.answer("✅ Отправлено клиенту")
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить: {e}")


@router.callback_query(F.data == "admin_broadcast", IsAdmin())
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext, lang: str):
    await callback.message.edit_text(
    "Введите текст рассылки:",
    reply_markup=cancel_keyboard()
)
    await state.set_state(BroadcastState.message)
    await callback.answer()


@router.message(BroadcastState.message, IsAdmin())
async def process_broadcast(message: Message, state: FSMContext, bot: Bot, lang: str):
    text = message.text
    if not text:
        await message.answer("Нужен текст")
        return

    user_ids = await get_all_user_ids()
    success = 0
    fail = 0

    for uid in user_ids:
        try:
            await bot.send_message(uid, text)
            success += 1
        except Exception:
            fail += 1

    await state.clear()
    await message.answer(
        f"✅ Рассылка завершена\nУспешно: {success}\nНе доставлено: {fail}",
        reply_markup=main_menu_keyboard(lang, is_admin=True)
    )

@router.callback_query(F.data == "admin_cancel", IsAdmin())
async def admin_cancel_cb(callback: CallbackQuery, state: FSMContext, lang: str):
    await state.clear()
    await callback.message.edit_text(
        get_text(lang, "admin_menu"),
        reply_markup=admin_menu_keyboard(lang)
    )
    await callback.answer("Отменено")


@router.callback_query(F.data == "admin_users", IsAdmin())
async def admin_users(callback: CallbackQuery, lang: str):
    page = 0
    users = await get_users_page(page)
    total = await get_users_count()
    total_pages = max(1, (total + 4) // 5)

    text = f"👥 Пользователи (стр. {page+1}/{total_pages})\nВсего: {total}"
    await callback.message.edit_text(
        text,
        reply_markup=users_list_keyboard(users, page, total_pages)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("users_page_"), IsAdmin())
async def users_page(callback: CallbackQuery, lang: str):
    page = int(callback.data.split("_")[2])
    users = await get_users_page(page)
    total = await get_users_count()
    total_pages = max(1, (total + 4) // 5)

    text = f"👥 Пользователи (стр. {page+1}/{total_pages})\nВсего: {total}"
    await callback.message.edit_text(
        text,
        reply_markup=users_list_keyboard(users, page, total_pages)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("user_info_"), IsAdmin())
async def user_info(callback: CallbackQuery, lang: str):
    user_id = int(callback.data.split("_")[2])
    user = await get_user(user_id)
    if not user:
        await callback.answer("Не найден", show_alert=True)
        return

    name = user.get("full_name") or "—"
    username = f"@{user['username']}" if user.get("username") else "нет"
    blocked = "Да 🚫" if user.get("is_blocked") else "Нет ✅"

    text = (
        f"👤 {name}\n"
        f"Username: {username}\n"
        f"ID: <code>{user_id}</code>\n"
        f"Заблокирован: {blocked}"
    )

    builder = InlineKeyboardBuilder()
    if user.get("is_blocked"):
        builder.row(InlineKeyboardButton(text="✅ Разблокировать", callback_data=f"unblock_{user_id}"))
    else:
        builder.row(InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"block_{user_id}"))
    
    builder.row(InlineKeyboardButton(text="✉️ Написать", callback_data=f"write_{user_id}"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_users"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("block_"), IsAdmin())
async def block_user(callback: CallbackQuery, lang: str):
    user_id = int(callback.data.split("_")[1])
    await set_user_blocked(user_id, True)
    await callback.answer("Пользователь заблокирован")
    # Обновляем карточку
    callback.data = f"user_info_{user_id}"
    await user_info(callback, lang)


@router.callback_query(F.data.startswith("unblock_"), IsAdmin())
async def unblock_user(callback: CallbackQuery, lang: str):
    user_id = int(callback.data.split("_")[1])
    await set_user_blocked(user_id, False)
    await callback.answer("Пользователь разблокирован")
    callback.data = f"user_info_{user_id}"
    await user_info(callback, lang)
