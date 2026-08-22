from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from database import get_all_products, create_order, get_user, create_user
from config import ADMIN_ID, BOT_TOKEN
from aiogram import Bot
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None


class OrderItem(BaseModel):
    product_id: int
    quantity: int


class CreateOrderRequest(BaseModel):
    user_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    city: str
    payment: str
    items: List[OrderItem]


@app.get("/")
async def root():
    return {"ok": True, "service": "mono-api"}


@app.get("/products")
async def products():
    rows = await get_all_products(only_available=False)
    result = []
    for p in rows:
        result.append({
            "id": p["id"],
            "name": p["name"],
            "volume": p.get("volume") or "30ML",
            "strength": p.get("strength") or "50MG",
            "price": p.get("price") or 15,
            "available": bool(p.get("is_available", 1)),
            "photo_file_id": p.get("photo_file_id"),
            "description": p.get("description") or "",
        })
    return result


@app.post("/orders")
async def create_order_api(data: CreateOrderRequest):
    user = await get_user(data.user_id)
    if not user:
        await create_user(data.user_id, data.username, data.full_name)

    order_ids = []
    lines = []
    total = 0

    products = await get_all_products(only_available=False)
    by_id = {p["id"]: p for p in products}

    for item in data.items:
        product = by_id.get(item.product_id)
        if not product:
            continue
        for _ in range(item.quantity):
            oid = await create_order(data.user_id, item.product_id, used_discount=False)
            order_ids.append(oid)
        price = float(product.get("price") or 15)
        total += price * item.quantity
        lines.append(f"{product['name']} x{item.quantity}")

    if bot and ADMIN_ID:
        text = (
            f"Новый заказ из Mini App\n\n"
            f"От: {data.full_name or '—'} (@{data.username or '—'})\n"
            f"ID: {data.user_id}\n"
            f"Город: {data.city}\n"
            f"Оплата: {data.payment}\n"
            f"Товары:\n" + "\n".join(f"• {l}" for l in lines) + f"\n\n"
            f"Итого: {total} €\n"
            f"Заказы: {', '.join(str(i) for i in order_ids)}"
        )
        try:
            await bot.send_message(ADMIN_ID, text)
        except Exception:
            pass

    return {"ok": True, "order_ids": order_ids, "total": total}
