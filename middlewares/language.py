from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from database import get_user


class LanguageMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if user:
            db_user = await get_user(user.id)
            if db_user and db_user.get("is_blocked"):
                return
            data["lang"] = db_user["language"] if db_user else "ru"
        else:
            data["lang"] = "ru"
        return await handler(event, data)
