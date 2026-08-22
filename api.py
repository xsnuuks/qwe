from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from database import (
    get_all_products, create_order, get_user, create_user,
    get_pending_orders, update_product, get_users_page, get_users_count,
    set_user_blocked, get_all_user_ids, get_stats, complete_order
)
from config import ADMIN_ID, BOT_TOKEN
from aiogram import Bot
import aiosqlite
from database import DB_PATH
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None


def check_admin(x_admin_id: Optional[str] = Header(None)):
    if not x_admin_id or int(x_admin_id) != ADMIN_ID:
        raise HTTPException(status_code=403, detail="Forbidden")


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


class StatusRequest(BaseModel):
    status: str  # done | cancelled | new


class ProductUpdate(BaseModel):
    is_available: Optional[bool] = None
    name: Optional[str] = None
    price: Optional[float] = None


class BroadcastRequest(BaseModel):
    text: str


class BlockRequest(BaseModel):
    blocked: bool


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
    total = 0.0

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


# ===== ADMIN =====

@app.get("/admin/orders")
async def admin_orders(x_admin_id: Optional[str] = Header(None)):
    check_admin(x_admin_id)
    rows = await get_pending_orders()
    return rows


@app.post("/admin/orders/{order_id}/status")
async def admin_order_status(order_id: int, data: StatusRequest, x_admin_id: Optional[str] = Header(None)):
    check_admin(x_admin_id)
    if data.status == "done":
        await complete_order(order_id)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE orders SET status = ? WHERE id = ?", (data.status, order_id))
            await db.commit()
    return {"ok": True}


@app.post("/admin/products/{product_id}")
async def admin_product_update(product_id: int, data: ProductUpdate, x_admin_id: Optional[str] = Header(None)):
    check_admin(x_admin_id)
    payload = {}
    if data.is_available is not None:
        payload["is_available"] = 1 if data.is_available else 0
    if data.name is not None:
        payload["name"] = data.name
    if data.price is not None:
        payload["price"] = data.price
    if payload:
        await update_product(product_id, **payload)
    return {"ok": True}


@app.get("/admin/users")
async def admin_users(page: int = 0, x_admin_id: Optional[str] = Header(None)):
    check_admin(x_admin_id)
    users = await get_users_page(page=page, per_page=10)
    total = await get_users_count()
    return {"users": users, "total": total, "page": page}


@app.post("/admin/users/{user_id}/block")
async def admin_block_user(user_id: int, data: BlockRequest, x_admin_id: Optional[str] = Header(None)):
    check_admin(x_admin_id)
    await set_user_blocked(user_id, data.blocked)
    return {"ok": True}


@app.post("/admin/broadcast")
async def admin_broadcast(data: BroadcastRequest, x_admin_id: Optional[str] = Header(None)):
    check_admin(x_admin_id)
    if not bot:
        return {"ok": False, "sent": 0}
    ids = await get_all_user_ids()
    sent = 0
    for uid in ids:
        try:
            await bot.send_message(uid, data.text)
            sent += 1
        except Exception:
            pass
    return {"ok": True, "sent": sent}


@app.get("/admin/stats")
async def admin_stats(x_admin_id: Optional[str] = Header(None)):
    check_admin(x_admin_id)
    return await get_stats()
