from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from locales import get_text


def language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Русский 🇷🇺", callback_data="lang_ru"),
        InlineKeyboardButton(text="English 🇬🇧", callback_data="lang_en"),
    )
    builder.row(
        InlineKeyboardButton(text="Deutsch 🇩🇪", callback_data="lang_de"),
    )
    return builder.as_markup()


def main_menu_keyboard(lang: str, is_admin: bool = False) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=get_text(lang, "catalog")))
    builder.row(
        KeyboardButton(text=get_text(lang, "profile")),
        KeyboardButton(text=get_text(lang, "referral")),
    )
    builder.row(
        KeyboardButton(text=get_text(lang, "rules")),
        KeyboardButton(text=get_text(lang, "support")),
    )
    builder.row(KeyboardButton(text=get_text(lang, "change_lang")))
    if is_admin:
        builder.row(KeyboardButton(text=get_text(lang, "admin_menu")))
    return builder.as_markup(resize_keyboard=True)


def product_keyboard(lang: str, product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=get_text(lang, "buy"),
            callback_data=f"buy_{product_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=get_text(lang, "back"),
            callback_data="back_catalog"
        )
    )
    return builder.as_markup()


def catalog_keyboard(lang: str, products: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in products:
        builder.row(
            InlineKeyboardButton(
                text=f"{p['name']} — {p['price']}€",
                callback_data=f"product_{p['id']}"
            )
        )
    builder.row(
        InlineKeyboardButton(text=get_text(lang, "back"), callback_data="back_main")
    )
    return builder.as_markup()


def admin_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=get_text(lang, "admin_stats"), callback_data="admin_stats"),
    )
    builder.row(
        InlineKeyboardButton(text=get_text(lang, "admin_orders"), callback_data="admin_orders"),
    )
    builder.row(
        InlineKeyboardButton(text=get_text(lang, "admin_products"), callback_data="admin_products"),
        InlineKeyboardButton(text=get_text(lang, "admin_add_product"), callback_data="admin_add_product"),
    )
    builder.row(
        InlineKeyboardButton(text=get_text(lang, "admin_add_referral"), callback_data="admin_add_referral"),
    )
    builder.row(
        InlineKeyboardButton(text=get_text(lang, "admin_broadcast"), callback_data="admin_broadcast"),
    )
    builder.row(
        InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"),
    )
    builder.row(
        InlineKeyboardButton(text=get_text(lang, "back"), callback_data="back_main")
    )
    return builder.as_markup()


def products_admin_keyboard(lang: str, products: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in products:
        status = "✅" if p["is_available"] else "❌"
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {p['name']}",
                callback_data=f"admin_toggle_{p['id']}"
            )
        )
    builder.row(
        InlineKeyboardButton(text=get_text(lang, "back"), callback_data="admin_menu")
    )
    return builder.as_markup()


def order_actions_keyboard(lang: str, order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=get_text(lang, "complete_order"),
            callback_data=f"complete_order_{order_id}"
        )
    )
    return builder.as_markup()


def back_keyboard(lang: str, callback: str = "back_main") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=get_text(lang, "back"), callback_data=callback)
    )
    return builder.as_markup()

def cancel_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")
    )
    return builder.as_markup()


def users_list_keyboard(users: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for u in users:
        name = u.get("full_name") or "—"
        username = f"@{u['username']}" if u.get("username") else "без юзера"
        status = "🚫" if u.get("is_blocked") else "✅"
        text = f"{status} {name} ({username})"
        builder.row(
            InlineKeyboardButton(
                text=text,
                callback_data=f"user_info_{u['user_id']}"
            )
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="←", callback_data=f"users_page_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="→", callback_data=f"users_page_{page+1}"))
    if nav:
        builder.row(*nav)

    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")
    )
    return builder.as_markup()


def users_list_keyboard(users: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for u in users:
        name = u.get("full_name") or "—"
        username = f"@{u['username']}" if u.get("username") else "без юзера"
        status = "🚫" if u.get("is_blocked") else "✅"
        text = f"{status} {name} ({username})"
        builder.row(
            InlineKeyboardButton(
                text=text,
                callback_data=f"user_info_{u['user_id']}"
            )
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="←", callback_data=f"users_page_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="→", callback_data=f"users_page_{page+1}"))
    if nav:
        builder.row(*nav)

    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")
    )
    return builder.as_markup()
