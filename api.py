import os
import uuid
from datetime import datetime
from typing import List, Optional

import aiosqlite
from aiogram import Bot
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import ADMIN_ID, BOT_TOKEN
from database import (
    DB_PATH,
    add_product,
    complete_order,
    create_order,
    create_user,
    get_all_products,
    get_all_user_ids,
    get_pending_orders,
    get_stats,
    get_user,
    get_users_count,
    get_users_page,
    set_user_blocked,
    update_product,add_message,
    get_messages,
    get_chat_list,
    mark_messages_read,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PHOTOS_DIR = "/data/photos"
os.makedirs(PHOTOS_DIR, exist_ok=True)
app.mount("/media", StaticFiles(directory=PHOTOS_DIR), name="media")

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None


def check_admin(x_admin_id: Optional[str] = Header(None)):
    if not x_admin_id or int(x_admin_id) != int(ADMIN_ID):
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
    place: str = ""
    items: List[OrderItem]


class StatusRequest(BaseModel):
    status: str


class ProductCreate(BaseModel):
    name: str
    price: float = 15
    volume: str = "30ML"
    strength: str = "50MG"
    description: str = ""
    is_available: bool = True


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    volume: Optional[str] = None
    strength: Optional[str] = None
    description: Optional[str] = None
    is_available: Optional[bool] = None


class BroadcastRequest(BaseModel):
    text: str


class BlockRequest(BaseModel):
    blocked: bool


class WriteUserRequest(BaseModel):
    text: str


def product_to_dict(p: dict) -> dict:
    photo = p.get("photo_file_id") or ""
    photo_url = None
    if photo.startswith("http"):
        photo_url = photo
    elif photo.startswith("/media/"):
        photo_url = photo
    elif photo.endswith((".jpg", ".jpeg", ".png", ".webp")):
        photo_url = f"/media/{photo}"
    return {
        "id": p["id"],
        "name": p["name"],
        "volume": p.get("volume") or "30ML",
        "strength": p.get("strength") or "50MG",
        "price": float(p.get("price") or 15),
        "available": bool(p.get("is_available", 1)),
        "description": p.get("description") or "",
        "photo": photo_url,
    }


@app.get("/")
async def root():
    return {"ok": True, "service": "mono-api"}


@app.get("/products")
async def products():
    rows = await get_all_products(only_available=False)
    return [product_to_dict(p) for p in rows]


@app.post("/orders")
async def create_order_api(data: CreateOrderRequest):
    user = await get_user(data.user_id)
    if user and user.get("is_blocked"):
        raise HTTPException(status_code=403, detail="Blocked")

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
        price = float(product.get("price") or 15)
        total += price * item.quantity
        lines.append(f"{product['name']} x{item.quantity}")

    items_text = ", ".join(lines)

    for item in data.items:
        product = by_id.get(item.product_id)
        if not product:
            continue
        for _ in range(item.quantity):
            oid = await create_order(
                data.user_id,
                item.product_id,
                used_discount=False,
                city=data.city,
                payment=data.payment,
                place=data.place,
                items_text=items_text,
                total=total,
            )
            order_ids.append(oid)

    if bot and ADMIN_ID:
        text = (
            f"Новый заказ из Mini App\n\n"
            f"От: {data.full_name or '—'} (@{data.username or '—'})\n"
            f"ID: {data.user_id}\n"
            f"Город: {data.city}\n"
            f"Место: {data.place or '—'}\n"
            f"Оплата: {data.payment}\n"
            f"Товары:\n" + "\n".join(f"• {l}" for l in lines) + f"\n\n"
            f"Итого: {total} €"
        )
        try:
            await bot.send_message(ADMIN_ID, text)
        except Exception:
            pass

    return {"ok": True, "order_ids": order_ids, "total": total}


@app.get("/admin/orders")
async def admin_orders(x_admin_id: Optional[str] = Header(None)):
    check_admin(x_admin_id)
    return await get_pending_orders()


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


@app.post("/admin/products")
async def admin_product_create(data: ProductCreate, x_admin_id: Optional[str] = Header(None)):
    check_admin(x_admin_id)
    pid = await add_product(
        name=data.name,
        description=data.description,
        price=data.price,
        volume=data.volume,
        strength=data.strength,
    )
    if not data.is_available:
        await update_product(pid, is_available=0)
    return {"ok": True, "id": pid}


@app.post("/admin/products/{product_id}")
async def admin_product_update(product_id: int, data: ProductUpdate, x_admin_id: Optional[str] = Header(None)):
    check_admin(x_admin_id)
    payload = {}
    if data.name is not None:
        payload["name"] = data.name
    if data.price is not None:
        payload["price"] = data.price
    if data.volume is not None:
        payload["volume"] = data.volume
    if data.strength is not None:
        payload["strength"] = data.strength
    if data.description is not None:
        payload["description"] = data.description
    if data.is_available is not None:
        payload["is_available"] = 1 if data.is_available else 0
    if payload:
        await update_product(product_id, **payload)
    return {"ok": True}


@app.delete("/admin/products/{product_id}")
async def admin_product_delete(product_id: int, x_admin_id: Optional[str] = Header(None)):
    check_admin(x_admin_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        await db.commit()
    return {"ok": True}


@app.post("/admin/products/{product_id}/photo")
async def admin_product_photo(
    product_id: int,
    file: UploadFile = File(...),
    x_admin_id: Optional[str] = Header(None),
):
    check_admin(x_admin_id)
    ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        ext = ".jpg"
    filename = f"{product_id}_{uuid.uuid4().hex[:8]}{ext}"
    path = os.path.join(PHOTOS_DIR, filename)
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    await update_product(product_id, photo_file_id=filename)
    return {"ok": True, "photo": f"/media/{filename}"}


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


@app.post("/admin/users/{user_id}/message")
async def admin_write_user(user_id: int, data: WriteUserRequest, x_admin_id: Optional[str] = Header(None)):
    check_admin(x_admin_id)
    if not bot:
        raise HTTPException(status_code=500, detail="Bot not available")
    try:
        await bot.send_message(user_id, data.text)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/admin/broadcast")
async def admin_broadcast(data: BroadcastRequest, x_admin_id: Optional[str] = Header(None)):
    check_admin(x_admin_id)
    if not bot:
        return {"ok": False, "sent": 0, "failed": []}
    ids = await get_all_user_ids()
    sent = 0
    failed = []
    for uid in ids:
        try:
            await bot.send_message(uid, data.text)
            sent += 1
        except Exception:
            u = await get_user(uid)
            failed.append({
                "user_id": uid,
                "username": (u or {}).get("username"),
                "full_name": (u or {}).get("full_name") or "—",
            })
    return {"ok": True, "sent": sent, "failed": failed}


@app.get("/admin/stats")
async def admin_stats(x_admin_id: Optional[str] = Header(None)):
    check_admin(x_admin_id)
    return await get_stats()


@app.get("/profile/{user_id}")
async def profile(user_id: int):
    data = await get_profile(user_id)
    if not data:
        return {
            "user_id": user_id,
            "purchases_count": 0,
            "successful_referrals": 0,
            "has_discount": False,
            "is_blocked": False,
        }
    return data

class SupportMessageIn(BaseModel):
    user_id: int
    text: str


class AdminReplyIn(BaseModel):
    text: str


@app.post("/support/send")
async def support_send(data: SupportMessageIn):
    text = (data.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty")
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="Too long")

    user = await get_user(data.user_id)
    if user and user.get("is_blocked"):
        raise HTTPException(status_code=403, detail="Blocked")

    if not user:
        await create_user(data.user_id, None, None)

    msg_id = await add_message(data.user_id, text, from_admin=False)

    if bot and ADMIN_ID:
        name = (user or {}).get("full_name") or "—"
        username = (user or {}).get("username") or "—"
        try:
            await bot.send_message(
                ADMIN_ID,
                f"💬 Поддержка\n\nОт: {name} (@{username})\nID: {data.user_id}\n\n{text}\n\nОтветь в Mini App → Админ → Чаты",
            )
        except Exception:
            pass

    return {"ok": True, "id": msg_id}


@app.get("/support/messages/{user_id}")
async def support_messages(user_id: int):
    await mark_messages_read(user_id, from_admin_side=False)
    rows = await get_messages(user_id)
    return [
        {
            "id": r["id"],
            "text": r["text"],
            "from_admin": bool(r["from_admin"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@app.get("/admin/chats")
async def admin_chats(x_admin_id: Optional[str] = Header(None)):
    require_admin(x_admin_id)
    rows = await get_chat_list()
    return [
        {
            "user_id": r["user_id"],
            "username": r.get("username"),
            "full_name": r.get("full_name"),
            "last_text": r.get("last_text"),
            "last_at": r.get("last_at"),
            "unread": r.get("unread") or 0,
        }
        for r in rows
    ]


@app.get("/admin/chats/{user_id}")
async def admin_chat_messages(user_id: int, x_admin_id: Optional[str] = Header(None)):
    require_admin(x_admin_id)
    await mark_messages_read(user_id, from_admin_side=True)
    rows = await get_messages(user_id)
    return [
        {
            "id": r["id"],
            "text": r["text"],
            "from_admin": bool(r["from_admin"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@app.post("/admin/chats/{user_id}/reply")
async def admin_chat_reply(user_id: int, data: AdminReplyIn, x_admin_id: Optional[str] = Header(None)):
    require_admin(x_admin_id)
    text = (data.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty")

    msg_id = await add_message(user_id, text, from_admin=True)

    if bot:
        try:
            await bot.send_message(
                user_id,
                "💬 Поддержка ответила.\nОткройте магазин → Профиль → Поддержка",
            )
        except Exception:
            pass

    return {"ok": True, "id": msg_id}
