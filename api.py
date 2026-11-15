import os
import uuid
from datetime import datetime
from typing import List, Optional

import aiosqlite
from aiogram import Bot
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, Depends
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
    get_stats,get_stats_period,
    get_user,
    get_users_count,
    get_users_page,
    set_user_blocked,
    update_product,add_message,
    get_messages,
    get_chat_list,
    mark_messages_read, get_profile, on_first_order_referral,
    use_discount_and_decrement,
    increment_purchases,
    get_profile, on_first_order_referral,add_favorite,
    remove_favorite,
    get_favorite_ids,
    get_favorite_products,delete_order,get_all_orders, get_categories, create_category,
    get_price_tiers, set_price_tiers,
    get_flavors, get_wholesale_categories,
    create_wholesale_category,
    get_wholesale_products, get_retail_products,
    create_retail_product,
    get_retail_flavors,
    get_retail_price_tiers,
    reorder_wholesale_products,
    create_wholesale_product,
    update_wholesale_product,
    delete_wholesale_product,
    get_price_tiers as get_wholesale_price_tiers,
    add_price_tier, update_price_tier,
    delete_price_tier,
    get_flavors as get_wholesale_flavors,
    add_flavor,
    update_flavor_stock,
    delete_flavor,
)

app = FastAPI()
def require_admin(x_admin_id: Optional[str] = None):
    if not x_admin_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        if int(x_admin_id) != int(ADMIN_ID):
            raise HTTPException(status_code=403, detail="Forbidden")
    except ValueError:
        raise HTTPException(status_code=403, detail="Forbidden")

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

def require_admin(x_admin_id: Optional[str] = None):
    if not x_admin_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        if int(x_admin_id) != int(ADMIN_ID):
            raise HTTPException(status_code=403, detail="Forbidden")
    except ValueError:
        raise HTTPException(status_code=403, detail="Forbidden")

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
    user = await get_user(data.user_id)
    purchases_before = (user or {}).get("purchases_count") or 0
    has_disc = bool((user or {}).get("has_discount") or 0)

    lines = []
    total = 0.0
    products = await get_all_products(only_available=False)
    by_id = {p["id"]: p for p in products}

    for item in data.items:
        product = by_id.get(item.product_id)
        if not product:
            continue
        price = 10.0 if has_disc else float(product.get("price") or 15)
        total += price * item.quantity
        lines.append(f"{product['name']} x{item.quantity}")

    items_text = ", ".join(lines)

    # Один заказ на всю корзину
    first_product_id = data.items[0].product_id if data.items else 0
    oid = await create_order(
        data.user_id,
        first_product_id,
        used_discount=has_disc,
        city=data.city,
        payment=data.payment,
        place=data.place,
        items_text=items_text,
        total=total,
    )
    order_ids = [oid]

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

    if purchases_before == 0:
        await on_first_order_referral(data.user_id)

    if has_disc:
        await use_discount_and_decrement(data.user_id)

    await increment_purchases(data.user_id)
    return {"ok": True, "order_ids": order_ids, "total": total}


@app.get("/admin/orders")
async def admin_orders(x_admin_id: Optional[str] = Header(None)):
    check_admin(x_admin_id)
    return await get_all_orders()

class OrderStatusIn(BaseModel):
    status: str


@app.post("/admin/orders/{order_id}/status")
async def admin_set_order_status(
    order_id: int,
    data: OrderStatusIn,
    x_admin_id: Optional[str] = Header(None),
):
    require_admin(x_admin_id)
    status = (data.status or "").strip().lower()
    if status not in ("pending", "progress", "done", "cancelled", "new"):
        raise HTTPException(status_code=400, detail="Bad status")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = await cur.fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="Not found")
        await db.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status, order_id),
        )
        await db.commit()
        user_id = order["user_id"]

    labels = {
        "pending": "ожидает",
        "new": "ожидает",
        "progress": "в процессе",
        "done": "выполнен",
        "cancelled": "отменён",
    }
    if bot and user_id:
        try:
            await bot.send_message(
                user_id,
                f"Заказ #{order_id}: статус «{labels.get(status, status)}».",
            )
        except Exception:
            pass

    return {"ok": True, "status": status}

@app.delete("/admin/orders/{order_id}")
async def admin_delete_order(
    order_id: int,
    x_admin_id: Optional[str] = Header(None),
):
    require_admin(x_admin_id)
    ok = await delete_order(order_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
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

@app.post("/api/wholesale/products/{product_id}/photo")
async def upload_wholesale_photo(
    product_id: int,
    file: UploadFile = File(...),
    x_telegram_init_data: Optional[str] = Header(None)
):
    import hashlib
    import hmac
    import json
    import time
    from urllib.parse import parse_qsl

    if not x_telegram_init_data or not BOT_TOKEN:
        raise HTTPException(401, "Telegram authorization required")

    try:
        data = dict(parse_qsl(x_telegram_init_data))
        received_hash = data.pop("hash")
        check_string = "\n".join(
            f"{key}={value}"
            for key, value in sorted(data.items())
        )

        secret = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        expected_hash = hmac.new(
            secret,
            check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(received_hash, expected_hash):
            raise ValueError("Invalid signature")

        auth_date = int(data["auth_date"])
        if not 0 <= time.time() - auth_date <= 86400:
            raise ValueError("Expired authorization")

        user = json.loads(data["user"])
        if int(user["id"]) != int(ADMIN_ID):
            raise HTTPException(403, "Admin only")

    except HTTPException:
        raise
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(401, "Invalid Telegram authorization")

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM wholesale_products WHERE id = ?",
            (product_id,)
        ) as cursor:
            if not await cursor.fetchone():
                raise HTTPException(404, "Product not found")

    content = await file.read(5 * 1024 * 1024 + 1)

    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "Image too large")

    if content.startswith(b"\xff\xd8\xff"):
        ext = ".jpg"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        ext = ".png"
    elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        ext = ".webp"
    else:
        raise HTTPException(400, "Unsupported image format")

    filename = f"wholesale_{product_id}_{uuid.uuid4().hex}{ext}"
    path = os.path.join(PHOTOS_DIR, filename)

    with open(path, "wb") as output:
        output.write(content)

    photo_url = f"/media/{filename}"

    await update_wholesale_product(
        product_id,
        photo_url=photo_url
    )

    return {"ok": True, "photo_url": photo_url}

@app.post("/api/retail/products/{product_id}/photo")
async def upload_retail_photo(
    product_id: int,
    file: UploadFile = File(...),
    x_telegram_init_data: Optional[str] = Header(None),
):
    user_id = verify_telegram_init_data(
        x_telegram_init_data or ""
    )

    if user_id != int(ADMIN_ID):
        raise HTTPException(403, "Доступ запрещён")

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id FROM retail_products WHERE id = ?",
            (product_id,),
        )
        product = await cursor.fetchone()
        await cursor.close()

        if not product:
            raise HTTPException(404, "Товар не найден")

    content = await file.read(5 * 1024 * 1024 + 1)

    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "Фото больше 5 МБ")

    if content.startswith(b"\xff\xd8\xff"):
        ext = ".jpg"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        ext = ".png"
    elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        ext = ".webp"
    else:
        raise HTTPException(400, "Используйте JPG, PNG или WEBP")

    filename = f"retail_{product_id}_{uuid.uuid4().hex}{ext}"
    path = os.path.join(PHOTOS_DIR, filename)

    with open(path, "wb") as output:
        output.write(content)

    photo_url = f"/media/{filename}"

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE retail_products
            SET photo_url = ?
            WHERE id = ?
            """,
            (photo_url, product_id),
        )
        await db.commit()

    return {"ok": True, "photo_url": photo_url}
    
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
async def admin_stats(
    period: str = "all",
    x_admin_id: Optional[str] = Header(None),
):
    check_admin(x_admin_id)
    if period not in ("today", "7d", "30d", "all"):
        period = "all"
    return await get_stats_period(period)


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


@app.get("/favorites/{user_id}")
async def favorites_list(user_id: int):
    rows = await get_favorite_products(user_id)
    return [product_to_dict(p) for p in rows]


@app.get("/favorites/{user_id}/ids")
async def favorites_ids(user_id: int):
    return await get_favorite_ids(user_id)


@app.post("/favorites/{user_id}/{product_id}")
async def favorites_add(user_id: int, product_id: int):
    await add_favorite(user_id, product_id)
    return {"ok": True}


@app.delete("/favorites/{user_id}/{product_id}")
async def favorites_remove(user_id: int, product_id: int):
    await remove_favorite(user_id, product_id)
    return {"ok": True}

@app.get("/categories")
async def api_get_categories(is_wholesale: int = 0):
    categories = await get_categories(is_wholesale)
    return categories

@app.post("/admin/categories")
async def api_create_category(data: dict, admin: int = Depends(check_admin)):
    category_id = await create_category(data["name"], data.get("is_wholesale", 0))
    return {"id": category_id}

@app.get("/products/{product_id}/tiers")
async def api_get_tiers(product_id: int):
    tiers = await get_price_tiers(product_id)
    return tiers

@app.post("/admin/products/{product_id}/tiers")
async def api_set_tiers(product_id: int, data: dict, admin: int = Depends(check_admin)):
    await set_price_tiers(product_id, data["tiers"])
    return {"ok": True}

@app.get("/products/{product_id}/flavors")
async def api_get_flavors(product_id: int):
    flavors = await get_flavors(product_id)
    return flavors


# ==================== ОПТ API ====================

@app.get("/api/wholesale/categories")
async def api_get_wholesale_categories():
    categories = await get_wholesale_categories()
    return {"categories": categories}


@app.post("/api/wholesale/categories")
async def api_create_wholesale_category(
    name: str = Form(...),
    x_admin_id: Optional[str] = Header(None)
):
    check_admin(x_admin_id)
    cat_id = await create_wholesale_category(name)
    return {"id": cat_id, "name": name}

class WholesaleReorderRequest(BaseModel):
    category_id: int
    product_ids: List[int]


@app.post("/api/wholesale/products/reorder")
async def api_reorder_wholesale_products(
    data: WholesaleReorderRequest,
    x_admin_id: Optional[str] = Header(None)
):
    check_admin(x_admin_id)

    if data.category_id < 1:
        raise HTTPException(400, "Некорректная категория")

    if not data.product_ids:
        raise HTTPException(400, "Список товаров пуст")

    try:
        await reorder_wholesale_products(
            data.category_id,
            data.product_ids
        )
    except ValueError as error:
        raise HTTPException(400, str(error))

    return {"ok": True}
    
@app.get("/api/wholesale/products")
async def api_get_wholesale_products(category_id: int = None):
    products = await get_wholesale_products(category_id)
    return {"products": products}

@app.patch("/api/wholesale/products/{product_id}")
async def api_update_wholesale_product(
    product_id: int,
    name: str = Form(None),
    photo_url: str = Form(None),
    is_visible: int = Form(None)
):
    await update_wholesale_product(product_id, name, photo_url, is_visible)
    return {"ok": True}

@app.delete("/api/wholesale/products/{product_id}")
async def api_delete_wholesale_product(product_id: int):
    await delete_wholesale_product(product_id)
    return {"ok": True}

@app.get("/api/wholesale/products/{product_id}/tiers")
async def api_get_price_tiers(product_id: int):
    tiers = await get_price_tiers(product_id)
    return {"tiers": tiers}

@app.post("/api/wholesale/products/{product_id}/tiers")
async def api_add_price_tier(
    product_id: int,
    min_qty: int = Form(...),
    price: float = Form(...)
):
    await add_price_tier(product_id, min_qty, price)
    return {"ok": True}

@app.patch("/api/wholesale/tiers/{tier_id}")
async def api_update_price_tier(
    tier_id: int,
    min_qty: int = Form(...),
    price: float = Form(...),
    x_admin_id: Optional[str] = Header(None)
):
    import math

    check_admin(x_admin_id)

    if min_qty < 1:
        raise HTTPException(
            status_code=400,
            detail="Минимальное количество должно быть от 1"
        )

    if not math.isfinite(price) or price <= 0:
        raise HTTPException(
            status_code=400,
            detail="Цена должна быть больше нуля"
        )

    await update_price_tier(tier_id, min_qty, price)

    return {"ok": True}
    
@app.delete("/api/wholesale/tiers/{tier_id}")
async def api_delete_price_tier(tier_id: int):
    await delete_price_tier(tier_id)
    return {"ok": True}

@app.get("/api/wholesale/products/{product_id}/flavors")
async def api_get_flavors(product_id: int):
    flavors = await get_flavors(product_id)
    return {"flavors": flavors}

@app.post("/api/wholesale/products/{product_id}/flavors")
async def api_add_flavor(
    product_id: int,
    name: str = Form(...),
    stock: int = Form(0)
):
    await add_flavor(product_id, name, stock)
    return {"ok": True}

@app.patch("/api/wholesale/flavors/{flavor_id}")
async def api_update_flavor_stock(
    flavor_id: int,
    stock: int = Form(...),
    name: Optional[str] = Form(None),
    x_admin_id: Optional[str] = Header(None)
):
    check_admin(x_admin_id)

    if stock < 0:
        raise HTTPException(400, "Количество не может быть отрицательным")

    if name is not None and not name.strip():
        raise HTTPException(400, "Название не может быть пустым")

    await update_flavor_stock(flavor_id, stock, name)
    return {"ok": True}

@app.delete("/api/wholesale/flavors/{flavor_id}")
async def api_delete_flavor(flavor_id: int):
    await delete_flavor(flavor_id)
    return {"ok": True}


# ==================== ОПТ API ====================

@app.get("/api/wholesale/products")
async def api_get_wholesale_products(category_id: int = None):
    from database import get_wholesale_products
    products = await get_wholesale_products(category_id)
    return products

@app.post("/api/wholesale/products")
async def api_create_wholesale_product(data: dict, admin: int = Depends(check_admin)):
    from database import create_wholesale_product
    product_id = await create_wholesale_product(
        category_id=data.get("category_id"),
        name=data.get("name"),
        photo_url=data.get("photo_url"),
        tiers=data.get("tiers"),
        flavors=data.get("flavors"),
    )
    return {"id": product_id}

@app.post("/api/wholesale/products/{product_id}")
async def api_update_wholesale_product(product_id: int, data: dict, admin: int = Depends(check_admin)):
    from database import update_wholesale_product
    await update_wholesale_product(
        product_id,
        name=data.get("name"),
        photo_url=data.get("photo_url"),
        is_visible=data.get("is_visible")
    )
    return {"ok": True}

@app.delete("/api/wholesale/products/{product_id}")
async def api_delete_wholesale_product(product_id: int, admin: int = Depends(check_admin)):
    from database import delete_wholesale_product
    await delete_wholesale_product(product_id)
    return {"ok": True}

@app.get("/api/wholesale/products/{product_id}/tiers")
async def api_get_wholesale_tiers(product_id: int):
    from database import get_price_tiers
    tiers = await get_price_tiers(product_id)
    return tiers

@app.post("/api/wholesale/products/{product_id}/tiers")
async def api_set_wholesale_tiers(product_id: int, data: dict, admin: int = Depends(check_admin)):
    from database import set_price_tiers
    await set_price_tiers(product_id, data["tiers"])
    return {"ok": True}

@app.get("/api/wholesale/products/{product_id}/flavors")
async def api_get_wholesale_flavors(product_id: int):
    from database import get_flavors
    flavors = await get_flavors(product_id)
    return flavors


# ==================== НОВАЯ РОЗНИЦА ====================

@app.get("/api/retail/products")
async def api_get_retail_products(
    category_id: Optional[int] = None
):
    products = await get_retail_products(category_id)
    return {"products": products}
    
# Создание товара новой розницы

class RetailTierCreate(BaseModel):
    min_qty: int
    price: float


class RetailFlavorCreate(BaseModel):
    name: str
    stock: int = 0


class RetailProductCreate(BaseModel):
    category_id: int
    name: str
    description: str = ""
    tiers: List[RetailTierCreate]
    flavors: List[RetailFlavorCreate]


@app.post("/api/retail/products")
async def api_create_retail_product(
    data: RetailProductCreate,
    x_admin_id: Optional[str] = Header(None)
):
    check_admin(x_admin_id)

    if not data.name.strip():
        raise HTTPException(400, "Введите название товара")

    if not data.tiers:
        raise HTTPException(400, "Добавьте ценовые пороги")

    if not data.flavors:
        raise HTTPException(400, "Добавьте вкусы")

    try:
        product_id = await create_retail_product(
            category_id=data.category_id,
            name=data.name,
            description=data.description,
            tiers=[tier.model_dump() for tier in data.tiers],
            flavors=[flavor.model_dump() for flavor in data.flavors]
        )

    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(400, str(error))

    return {
        "ok": True,
        "id": product_id
    }

@app.get("/api/retail/products/{product_id}/flavors")
async def api_get_retail_flavors(
    product_id: int,
    x_telegram_init_data: Optional[str] = Header(None),
):
    flavors = await get_retail_flavors(product_id)

    is_admin = False
    if x_telegram_init_data:
        try:
            user_id = verify_telegram_init_data(x_telegram_init_data)
            is_admin = user_id == int(ADMIN_ID)
        except Exception:
            pass

    if not is_admin:
        flavors = [
            flavor for flavor in flavors
            if int(flavor.get("is_active", 1)) == 1
        ]

    return {"flavors": flavors}


@app.get("/api/retail/products/{product_id}/tiers")
async def api_get_retail_tiers(product_id: int):
    tiers = await get_retail_price_tiers(product_id)
    return {"tiers": tiers}

class RetailPriceTierIn(BaseModel):
    min_qty: int
    price: float


class RetailPriceTiersUpdateIn(BaseModel):
    tiers: list[RetailPriceTierIn]


@app.put("/api/retail/products/{product_id}/tiers")
async def api_update_retail_tiers(
    product_id: int,
    data: RetailPriceTiersUpdateIn,
    x_telegram_init_data: Optional[str] = Header(None),
):
    import math

    user_id = verify_telegram_init_data(
        x_telegram_init_data or ""
    )

    if user_id != int(ADMIN_ID):
        raise HTTPException(403, "Доступ запрещён")

    tiers = data.tiers

    if not tiers:
        raise HTTPException(400, "Добавьте хотя бы одну цену")

    quantities = [tier.min_qty for tier in tiers]

    if any(q < 1 for q in quantities):
        raise HTTPException(400, "Количество должно быть от 1")

    if len(quantities) != len(set(quantities)):
        raise HTTPException(400, "Пороги количества повторяются")

    if 1 not in quantities:
        raise HTTPException(400, "Нужна цена от 1 шт.")

    if any(
        not math.isfinite(tier.price) or tier.price <= 0
        for tier in tiers
    ):
        raise HTTPException(400, "Цена должна быть больше 0")

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("BEGIN IMMEDIATE")

            cursor = await db.execute(
                "SELECT id FROM retail_products WHERE id = ?",
                (product_id,),
            )
            product = await cursor.fetchone()
            await cursor.close()

            if not product:
                raise HTTPException(404, "Товар не найден")

            await db.execute(
                "DELETE FROM retail_price_tiers WHERE product_id = ?",
                (product_id,),
            )

            for tier in sorted(tiers, key=lambda t: t.min_qty):
                await db.execute(
                    """
                    INSERT INTO retail_price_tiers
                    (product_id, min_qty, price)
                    VALUES (?, ?, ?)
                    """,
                    (product_id, tier.min_qty, tier.price),
                )

            await db.commit()

        except Exception:
            await db.rollback()
            raise

    return {"ok": True, "product_id": product_id}
    
class RetailFlavorCreateIn(BaseModel):
    name: str
    stock: int = 0


@app.post("/api/retail/products/{product_id}/flavors")
async def api_create_retail_flavor(
    product_id: int,
    data: RetailFlavorCreateIn,
    x_telegram_init_data: Optional[str] = Header(None),
):
    user_id = verify_telegram_init_data(
        x_telegram_init_data or ""
    )

    if user_id != int(ADMIN_ID):
        raise HTTPException(403, "Доступ запрещён")

    name = data.name.strip()

    if not name:
        raise HTTPException(400, "Введите название вкуса")

    if data.stock < 0:
        raise HTTPException(400, "Остаток не может быть отрицательным")

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id FROM retail_products WHERE id = ?",
            (product_id,),
        )
        product = await cursor.fetchone()
        await cursor.close()

        if not product:
            raise HTTPException(404, "Товар не найден")

        cursor = await db.execute(
            """
            INSERT INTO retail_flavors (product_id, name, stock)
            VALUES (?, ?, ?)
            """,
            (product_id, name, data.stock),
        )

        flavor_id = cursor.lastrowid
        await db.commit()

    return {"ok": True, "flavor_id": flavor_id}

@app.delete("/api/retail/flavors/{flavor_id}")
async def api_delete_retail_flavor(
    flavor_id: int,
    x_telegram_init_data: Optional[str] = Header(None),
):
    user_id = verify_telegram_init_data(
        x_telegram_init_data or ""
    )

    if user_id != int(ADMIN_ID):
        raise HTTPException(403, "Доступ запрещён")

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("BEGIN IMMEDIATE")

            cursor = await db.execute(
                "SELECT stock FROM retail_flavors WHERE id = ?",
                (flavor_id,),
            )
            flavor = await cursor.fetchone()
            await cursor.close()

            if not flavor:
                raise HTTPException(404, "Вкус не найден")

            if flavor[0] > 0:
                raise HTTPException(
                    409,
                    "Сначала установите остаток вкуса на 0"
                )

            cursor = await db.execute(
                """
                SELECT COUNT(*)
                FROM retail_order_items
                WHERE flavor_id = ?
                """,
                (flavor_id,),
            )
            orders_count = (await cursor.fetchone())[0]
            await cursor.close()

            if orders_count > 0:
                raise HTTPException(
                    409,
                    "Вкус есть в истории заказов. Удаление запрещено"
                )

            await db.execute(
                "DELETE FROM retail_flavors WHERE id = ?",
                (flavor_id,),
            )

            await db.commit()

        except Exception:
            await db.rollback()
            raise

    return {"ok": True, "flavor_id": flavor_id}

class RetailFlavorUpdateIn(BaseModel):
    name: str
    stock: int
    is_active: bool = True


@app.patch("/api/retail/flavors/{flavor_id}")
async def api_update_retail_flavor(
    flavor_id: int,
    data: RetailFlavorUpdateIn,
    x_telegram_init_data: Optional[str] = Header(None),
):
    user_id = verify_telegram_init_data(
        x_telegram_init_data or ""
    )

    if user_id != int(ADMIN_ID):
        raise HTTPException(403, "Доступ запрещён")

    name = data.name.strip()

    if not name:
        raise HTTPException(400, "Название вкуса не может быть пустым")

    if data.stock < 0:
        raise HTTPException(400, "Остаток не может быть отрицательным")

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            UPDATE retail_flavors
            SET name = ?, stock = ?, is_active = ?
            WHERE id = ?
            """,
            (name, data.stock, int(data.is_active), flavor_id),
        )

        if cursor.rowcount == 0:
            raise HTTPException(404, "Вкус не найден")

        await db.commit()

    return {"ok": True, "flavor_id": flavor_id}
    
class RetailProductUpdateIn(BaseModel):
    name: str
    description: str = ""
    is_visible: bool = True
    photo_url: Optional[str] = None


@app.patch("/api/retail/products/{product_id}")
async def api_update_retail_product(
    product_id: int,
    data: RetailProductUpdateIn,
    x_telegram_init_data: Optional[str] = Header(None),
):
    user_id = verify_telegram_init_data(
        x_telegram_init_data or ""
    )

    if user_id != int(ADMIN_ID):
        raise HTTPException(403, "Доступ запрещён")

    name = data.name.strip()

    if not name:
        raise HTTPException(400, "Название не может быть пустым")

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            UPDATE retail_products
            SET name = ?,
                description = ?,
                is_visible = ?,
                photo_url = COALESCE(?, photo_url)
            WHERE id = ?
            """,
            (
                name,
                data.description.strip(),
                int(data.is_visible),
                data.photo_url,
                product_id,
            ),
        )

        if cursor.rowcount == 0:
            raise HTTPException(404, "Товар не найден")

        await db.commit()

    return {"ok": True, "product_id": product_id}
    
# === РОЗНИЧНЫЕ ЗАКАЗЫ ===

class RetailOrderItemIn(BaseModel):
    product_id: int
    flavor_id: int
    quantity: int


class RetailOrderCreateIn(BaseModel):
    user_id: Optional[int] = None
    request_id: str

    delivery_type: str
    first_name: str
    last_name: str
    phone: str
    email: Optional[str] = None

    city: Optional[str] = None
    postal_code: Optional[str] = None
    street: Optional[str] = None
    house: Optional[str] = None
    apartment: Optional[str] = None

    payment_method: str
    items: List[RetailOrderItemIn]

def verify_telegram_init_data(init_data: str) -> int:
    import hashlib
    import hmac
    import json
    import time
    from urllib.parse import parse_qsl

    if not BOT_TOKEN or not init_data:
        raise HTTPException(401, "Требуется авторизация Telegram")

    try:
        values = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = values.pop("hash", "")

        data_check_string = "\n".join(
            f"{key}={value}"
            for key, value in sorted(values.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        expected_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_hash, received_hash):
            raise ValueError("Invalid signature")

        auth_date = int(values["auth_date"])
        age = time.time() - auth_date

        if age < -60 or age > 86400:
            raise ValueError("Expired authorization")

        user = json.loads(values["user"])
        return int(user["id"])

    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(401, "Недействительная авторизация Telegram")

def get_telegram_username(init_data: str) -> str:
    import json
    from urllib.parse import parse_qsl

    # Проверяем подлинность данных Telegram
    verify_telegram_init_data(init_data)

    try:
        values = dict(parse_qsl(init_data, keep_blank_values=True))
        user = json.loads(values.get("user", "{}"))
        username = user.get("username", "")

        if isinstance(username, str):
            return username

        return ""
    except (ValueError, TypeError, json.JSONDecodeError):
        return ""

class WholesaleOrderItemIn(BaseModel):
    product_id: int
    flavor_id: int
    quantity: int


class WholesaleOrderCreateIn(BaseModel):
    request_id: str
    first_name: str
    last_name: str
    phone: str
    email: str = ""
    country: str
    city: str
    postal_code: str
    street: str
    house: str
    payment_method: str
    items: list[WholesaleOrderItemIn]

def validate_wholesale_order(data: WholesaleOrderCreateIn):
    if not data.request_id.strip() or len(data.request_id) > 100:
        raise HTTPException(400, "Неверный идентификатор заказа")

    if data.payment_method not in ("usdt", "uah"):
        raise HTTPException(400, "Неверный способ оплаты")

    required_fields = (
        data.first_name,
        data.last_name,
        data.phone,
        data.country,
        data.city,
        data.postal_code,
        data.street,
        data.house,
    )

    if any(not value.strip() for value in required_fields):
        raise HTTPException(400, "Заполните данные доставки")

    if not data.items:
        raise HTTPException(400, "Корзина пуста")

    if any(
        item.product_id <= 0
        or item.flavor_id <= 0
        or item.quantity <= 0
        for item in data.items
    ):
        raise HTTPException(400, "Неверное количество или товар")

    total_quantity = sum(item.quantity for item in data.items)

    if total_quantity < 20:
        raise HTTPException(
            400, "Минимальный оптовый заказ — 20 единиц"
        )

    pairs = [
        (item.product_id, item.flavor_id)
        for item in data.items
    ]

    if len(pairs) != len(set(pairs)):
        raise HTTPException(400, "Повторяющиеся позиции в корзине")

    return total_quantity

async def get_wholesale_order_price(
    db,
    product_id: int,
    total_quantity: int,
):
    from decimal import Decimal
    cursor = await db.execute(
        """
        SELECT price
        FROM wholesale_price_tiers
        WHERE product_id = ?
          AND min_qty <= ?
        ORDER BY min_qty DESC
        LIMIT 1
        """,
        (product_id, total_quantity),
    )

    tier = await cursor.fetchone()
    await cursor.close()

    if tier is None:
        raise HTTPException(
            status_code=400,
            detail="Для одного из товаров не найдена оптовая цена"
        )

    return Decimal(str(tier[0]))

async def prepare_wholesale_order_items(
    db,
    items: list[WholesaleOrderItemIn],
    total_quantity: int,
):
    from decimal import Decimal

    prepared = []
    total = Decimal("0.00")

    for item in items:
        cursor = await db.execute(
            """
            SELECT
                p.name,
                p.is_visible,
                f.name,
                f.stock
            FROM wholesale_products p
            JOIN wholesale_flavors f
                ON f.product_id = p.id
            WHERE p.id = ? AND f.id = ?
            """,
            (item.product_id, item.flavor_id),
        )
        product = await cursor.fetchone()
        await cursor.close()

        if not product or not product[1]:
            raise ValueError("Один из оптовых товаров недоступен")

        if item.quantity > product[3]:
            raise ValueError(
                f"Недостаточно на складе: {product[2]}"
            )

        unit_price = await get_wholesale_order_price(
            db,
            item.product_id,
            total_quantity,
        )

        line_total = unit_price * item.quantity
        total += line_total

        prepared.append({
            "product_id": item.product_id,
            "flavor_id": item.flavor_id,
            "product_name": product[0],
            "flavor_name": product[2],
            "quantity": item.quantity,
            "unit_price": unit_price,
            "line_total": line_total,
        })

    return prepared, total

@app.post("/api/wholesale/orders")
async def api_create_wholesale_order(
    data: WholesaleOrderCreateIn,
    x_telegram_init_data: Optional[str] = Header(None),
):
    from datetime import datetime, timezone
    import sqlite3

    user_id = verify_telegram_init_data(
        x_telegram_init_data or ""
    )

    buyer_username = get_telegram_username(
        x_telegram_init_data or ""
    )

    total_quantity = validate_wholesale_order(data)

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("BEGIN IMMEDIATE")

            cursor = await db.execute(
                """
                SELECT id, user_id
                FROM wholesale_orders
                WHERE request_id = ?
                """,
                (data.request_id,),
            )
            existing = await cursor.fetchone()
            await cursor.close()

            if existing:
                if existing[1] != user_id:
                    raise HTTPException(
                        409, "Идентификатор заказа уже используется"
                    )

                await db.rollback()
                return {
                    "ok": True,
                    "order_id": existing[0],
                    "already_created": True,
                }

            prepared, total = await prepare_wholesale_order_items(
                db,
                data.items,
                total_quantity,
            )

            cursor = await db.execute(
                """
                INSERT INTO wholesale_orders (
                    request_id, user_id,
                    first_name, last_name, phone, email,
                    country, city, postal_code, street, house,
                    payment_method, items_total, status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.request_id,
                    user_id,
                    data.first_name.strip(),
                    data.last_name.strip(),
                    data.phone.strip(),
                    data.email.strip(),
                    data.country.strip(),
                    data.city.strip(),
                    data.postal_code.strip(),
                    data.street.strip(),
                    data.house.strip(),
                    data.payment_method,
                    float(total),
                    "new",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

            order_id = cursor.lastrowid
            await cursor.close()

            for item in prepared:
                cursor = await db.execute(
                    """
                    UPDATE wholesale_flavors
                    SET stock = stock - ?
                    WHERE id = ?
                      AND product_id = ?
                      AND stock >= ?
                    """,
                    (
                        item["quantity"],
                        item["flavor_id"],
                        item["product_id"],
                        item["quantity"],
                    ),
                )

                changed = cursor.rowcount
                await cursor.close()

                if changed != 1:
                    raise HTTPException(
                        409, "Недостаточно товара на складе"
                    )

                await db.execute(
                    """
                    INSERT INTO wholesale_order_items (
                        order_id, product_id, flavor_id,
                        product_name, flavor_name,
                        quantity, unit_price, line_total
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        item["product_id"],
                        item["flavor_id"],
                        item["product_name"],
                        item["flavor_name"],
                        item["quantity"],
                        float(item["unit_price"]),
                        float(item["line_total"]),
                    ),
                )

            await db.commit()

            # Уведомление администратору о новом заказе
            if bot and ADMIN_ID:
                from zoneinfo import ZoneInfo

                order_time = datetime.now(
                    ZoneInfo("Europe/Berlin")
                ).strftime("%d.%m.%Y %H:%M")

                items_text = "\n".join(
                    f"• {item['product_name']} — {item['flavor_name']}\n"
                    f"  {item['quantity']} шт. × {float(item['unit_price']):.2f} €"
                    for item in prepared
                )

                message = (
                    f"📦 PUFFY WHOLESALE — Заказ №{order_id}\n"
                    f"📅 {order_time} (Германия)\n\n"

                    f"👤 ПОКУПАТЕЛЬ\n"
                    f"Имя: {data.first_name}\n"
                    f"Фамилия: {data.last_name}\n"
                    f"Telegram ID: {user_id}\n"
                    f"Telegram: {('@' + buyer_username) if buyer_username else 'Не указан'}\n"
                    f"Телефон: {data.phone}\n"
                    f"Email: {data.email or 'Не указан'}\n\n"

                    f"📍 ДОСТАВКА\n"
                    f"Страна: {data.country}\n"
                    f"Город: {data.city}\n"
                    f"Индекс: {data.postal_code}\n"
                    f"Улица: {data.street}\n"
                    f"Дом: {data.house}\n\n"

                    f"📦 ТОВАРЫ\n"
                    f"{items_text}\n\n"

                    f"💳 Оплата: {data.payment_method}\n"
                    f"💰 Сумма товаров: {float(total):.2f} €\n"
                    f"🚚 Доставка: рассчитывается отдельно\n"
                    f"📋 Статус: Новый"
                )

                try:
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

                    reply_markup = None

                    if buyer_username:
                        reply_markup = InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text="💬 Связаться с покупателем",
                                        url=f"https://t.me/{buyer_username}",
                                    )
                                ]
                            ]
                        )

                    await bot.send_message(
                        chat_id=ADMIN_ID,
                        text=message,
                        reply_markup=reply_markup,
                    )
                except Exception:
                    pass

            return {
                "ok": True,
                "order_id": order_id,
                "items_total": float(total),
                "total_quantity": total_quantity,
                "already_created": False,
            }

        except HTTPException:
            await db.rollback()
            raise
        except ValueError as error:
            await db.rollback()
            raise HTTPException(400, str(error))
        except sqlite3.IntegrityError:
            await db.rollback()
            raise HTTPException(
                409, "Конфликт при создании заказа"
            )
        except Exception:
            await db.rollback()
            raise

@app.get("/api/wholesale/my-orders")
async def api_get_my_wholesale_orders(
    x_telegram_init_data: Optional[str] = Header(None),
):
    user_id = verify_telegram_init_data(x_telegram_init_data or "")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT *
            FROM wholesale_orders
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,),
        )
        orders = [dict(row) for row in await cursor.fetchall()]
        await cursor.close()

        for order in orders:
            cursor = await db.execute(
                """
                SELECT *
                FROM wholesale_order_items
                WHERE order_id = ?
                ORDER BY id
                """,
                (order["id"],),
            )
            order["items"] = [
                dict(row) for row in await cursor.fetchall()
            ]
            await cursor.close()

    return {"orders": orders}

class WholesaleOrderStatusIn(BaseModel):
    status: str


@app.patch("/api/admin/wholesale/orders/{order_id}/status")
async def api_update_wholesale_order_status(
    order_id: int,
    data: WholesaleOrderStatusIn,
    x_telegram_init_data: Optional[str] = Header(None),
):
    user_id = verify_telegram_init_data(x_telegram_init_data or "")

    if int(user_id) != int(ADMIN_ID):
        raise HTTPException(403, "Доступ запрещён")

    if data.status not in ("done", "cancelled"):
        raise HTTPException(400, "Недопустимый статус заказа")

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("BEGIN IMMEDIATE")

            cursor = await db.execute(
                "SELECT status FROM wholesale_orders WHERE id = ?",
                (order_id,),
            )
            order = await cursor.fetchone()
            await cursor.close()

            if not order:
                raise HTTPException(404, "Заказ не найден")

            old_status = order[0]

            if old_status in ("done", "cancelled"):
                if old_status != data.status:
                    raise HTTPException(
                        400, "Завершённый заказ нельзя изменить"
                    )
                await db.rollback()
                return {
                    "ok": True,
                    "order_id": order_id,
                    "status": old_status,
                    "already_updated": True,
                }

            if old_status != "new":
                raise HTTPException(400, "Неизвестный статус заказа")

            if data.status == "cancelled":
                cursor = await db.execute(
                    """
                    SELECT flavor_id, quantity
                    FROM wholesale_order_items
                    WHERE order_id = ?
                    """,
                    (order_id,),
                )
                items = await cursor.fetchall()
                await cursor.close()

                for flavor_id, quantity in items:
                    await db.execute(
                        """
                        UPDATE wholesale_flavors
                        SET stock = stock + ?
                        WHERE id = ?
                        """,
                        (quantity, flavor_id),
                    )

            await db.execute(
                """
                UPDATE wholesale_orders
                SET status = ?
                WHERE id = ?
                """,
                (data.status, order_id),
            )
            await db.commit()

        except Exception:
            await db.rollback()
            raise

    # Статус сохранён. Получаем Telegram ID покупателя.
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id FROM wholesale_orders WHERE id = ?",
            (order_id,),
        )
        buyer = await cursor.fetchone()
        await cursor.close()

    if buyer and bot:
        buyer_id = int(buyer[0])

        if data.status == "done":
            message = (
                f"✅ Ваш заказ №{order_id} выполнен!\n\n"
                "Спасибо за заказ в Puffy Store!"
            )
        else:
            message = (
                f"❌ Ваш заказ №{order_id} отменён.\n\n"
                "Для уточнения деталей свяжитесь с менеджером."
            )

        try:
            await bot.send_message(
                chat_id=buyer_id,
                text=message,
            )
        except Exception:
            # Ошибка Telegram не отменяет сохранённый статус.
            pass

    return {
        "ok": True,
        "order_id": order_id,
        "status": data.status,
        "already_updated": False,
    }

@app.get("/api/admin/wholesale/orders")
async def api_get_admin_wholesale_orders(
    x_telegram_init_data: Optional[str] = Header(None),
):
    user_id = verify_telegram_init_data(x_telegram_init_data or "")

    if int(user_id) != int(ADMIN_ID):
        raise HTTPException(status_code=403, detail="Доступ запрещён")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT *
            FROM wholesale_orders
            ORDER BY id DESC
            """
        )
        orders = [dict(row) for row in await cursor.fetchall()]
        await cursor.close()

        for order in orders:
            cursor = await db.execute(
                """
                SELECT *
                FROM wholesale_order_items
                WHERE order_id = ?
                ORDER BY id
                """,
                (order["id"],),
            )
            order["items"] = [
                dict(row) for row in await cursor.fetchall()
            ]
            await cursor.close()

    return {"orders": orders}
    
@app.post("/api/retail/orders")
async def api_create_retail_order(
    data: RetailOrderCreateIn,
    x_telegram_init_data: Optional[str] = Header(None),
):
    from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
    verified_user_id = verify_telegram_init_data(
        x_telegram_init_data or ""
    )

    if data.user_id is not None and data.user_id != verified_user_id:
        raise HTTPException(403, "Неверный Telegram ID")

    if data.delivery_type not in ("pickup", "delivery"):
        raise HTTPException(400, "Неверный способ получения")

    if data.payment_method not in (
        ("usdt", "uah", "cash")
        if data.delivery_type == "pickup"
        else ("usdt", "uah")
    ):
        raise HTTPException(400, "Неверный способ оплаты")

    if data.delivery_type == "delivery":
        if not data.first_name.strip() or not data.last_name.strip():
            raise HTTPException(400, "Укажите имя и фамилию")

        if not data.phone.strip():
            raise HTTPException(400, "Укажите телефон")

    if data.delivery_type == "delivery":
        if not all([
            data.email and data.email.strip(),
            data.city and data.city.strip(),
            data.postal_code and data.postal_code.strip(),
            data.street and data.street.strip(),
            data.house and data.house.strip(),
        ]):
            raise HTTPException(400, "Заполните адрес и контакты")

    if not data.items or len(data.items) > 100:
        raise HTTPException(400, "Некорректная корзина")

    quantities = {}
    product_totals = {}

    for item in data.items:
        if item.product_id <= 0 or item.flavor_id <= 0:
            raise HTTPException(400, "Некорректный товар")

        if item.quantity < 1 or item.quantity > 1000:
            raise HTTPException(400, "Некорректное количество")

        key = (item.product_id, item.flavor_id)

        quantities[key] = quantities.get(key, 0) + item.quantity
        product_totals[item.product_id] = (
            product_totals.get(item.product_id, 0) + item.quantity
        )

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        try:
            # Блокируем запись других заказов на время проверки
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                """
                SELECT order_id
                FROM retail_order_requests
                WHERE request_id = ?
                """,
                (data.request_id,)
            )

            existing_order = await cursor.fetchone()
            await cursor.close()

            if existing_order:
                await db.rollback()
                return {
                    "ok": True,
                    "order_id": existing_order["order_id"],
                    "status": "existing",
                }

            prepared_items = []
            total = Decimal("0.00")

            for (product_id, flavor_id), quantity in quantities.items():
                cursor = await db.execute(
                    """
                    SELECT
                        p.name AS product_name,
                        p.is_visible,
                        f.name AS flavor_name,
                        f.stock
                    FROM retail_products p
                    JOIN retail_flavors f ON f.product_id = p.id
                    WHERE p.id = ? AND f.id = ?
                    """,
                    (product_id, flavor_id)
                )
                product = await cursor.fetchone()
                await cursor.close()

                if not product or not product["is_visible"]:
                    raise ValueError("Один из товаров недоступен")

                if quantity > product["stock"]:
                    raise ValueError(
                        f"Недостаточный остаток: {product['flavor_name']}"
                    )

                cursor = await db.execute(
                    """
                    SELECT price
                    FROM retail_price_tiers
                    WHERE product_id = ?
                      AND min_qty <= ?
                    ORDER BY min_qty DESC
                    LIMIT 1
                    """,
                    (product_id, product_totals[product_id])
                )
                tier = await cursor.fetchone()
                await cursor.close()

                if not tier:
                    raise ValueError("У товара отсутствует цена")

                try:
                    price = Decimal(str(tier["price"]))
                    price = price.quantize(
                        Decimal("0.01"),
                        rounding=ROUND_HALF_UP
                    )
                except (InvalidOperation, ValueError):
                    raise ValueError("Некорректная цена")

                if not price.is_finite() or price <= 0:
                    raise ValueError("Некорректная цена")

                line_total = price * quantity
                total += line_total

                prepared_items.append({
                    "product_id": product_id,
                    "flavor_id": flavor_id,
                    "product_name": product["product_name"],
                    "flavor_name": product["flavor_name"],
                    "quantity": quantity,
                    "unit_price": float(price),
                    "line_total": float(line_total),
                })

            cursor = await db.execute(
                """
                INSERT INTO retail_orders (
                    user_id, delivery_type,
                    first_name, last_name, phone, email,
                    country, city, postal_code, street,
                    house, apartment,
                    payment_method, items_total,
                    delivery_price, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    verified_user_id,
                    data.delivery_type,
                    data.first_name.strip(),
                    data.last_name.strip(),
                    data.phone.strip(),
                    data.email,
                    "Germany",
                    data.city,
                    data.postal_code,
                    data.street,
                    data.house,
                    data.apartment,
                    data.payment_method,
                    float(total),
                    None,
                    "new",
                    datetime.now().isoformat(),
                )
            )

            order_id = cursor.lastrowid
            await cursor.close()

            for item in prepared_items:
                await db.execute(
                    """
                    INSERT INTO retail_order_items (
                        order_id, product_id, flavor_id,
                        product_name, flavor_name,
                        quantity, unit_price, line_total
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        item["product_id"],
                        item["flavor_id"],
                        item["product_name"],
                        item["flavor_name"],
                        item["quantity"],
                        item["unit_price"],
                        item["line_total"],
                    )
                )

                cursor = await db.execute(
    """
    UPDATE retail_flavors
    SET stock = stock - ?
    WHERE id = ?
      AND is_active = 1
      AND stock >= ?
    """,
    (
        item["quantity"],
        item["flavor_id"],
        item["quantity"],
    ),
)

                if cursor.rowcount != 1:
                    raise ValueError(
                        "Один из вкусов скрыт или закончился. "
                        "Обновите корзину и попробуйте снова."
                    )

                await cursor.close()

            await db.execute(
                """
                INSERT INTO retail_order_requests (
                    request_id, order_id, created_at
                )
                VALUES (?, ?, ?)
                """,
                (
                    data.request_id,
                    order_id,
                    datetime.now().isoformat(),
                )
            )

            await db.commit()

        except ValueError as exc:
            await db.rollback()
            raise HTTPException(400, str(exc))

        except Exception:
            await db.rollback()
            raise

    # Уведомление администратору после сохранения заказа
    if bot and ADMIN_ID:
        from zoneinfo import ZoneInfo
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        buyer_username = get_telegram_username(
            x_telegram_init_data or ""
        )

        order_time = datetime.now(
            ZoneInfo("Europe/Berlin")
        ).strftime("%d.%m.%Y %H:%M")

        items_text = "\n".join(
            f"• {item['product_name']} — {item['flavor_name']}\n"
            f"  {item['quantity']} шт. × {item['unit_price']:.2f} €"
            f" = {item['line_total']:.2f} €"
            for item in prepared_items
        )

        if data.delivery_type == "pickup":
            delivery_text = "Самовывоз по договорённости с менеджером"
        else:
            delivery_text = (
                f"Доставка GLS\n"
                f"Имя: {data.first_name}\n"
                f"Фамилия: {data.last_name}\n"
                f"Телефон: {data.phone}\n"
                f"Email: {data.email}\n"
                f"Страна: Германия\n"
                f"Город: {data.city}\n"
                f"Индекс: {data.postal_code}\n"
                f"Улица: {data.street}\n"
                f"Дом: {data.house}\n"
                f"Квартира: {data.apartment or 'Не указана'}"
            )

        message = (
            f"🛍 PUFFY STORE — Новый заказ №{order_id}\n\n"
            f"📅 {order_time} (Германия)\n"
            f"👤 Telegram ID: {verified_user_id}\n"
            f"💬 Telegram: "
            f"{('@' + buyer_username) if buyer_username else 'Не указан'}\n\n"
            f"📦 ТОВАРЫ\n{items_text}\n\n"
            f"🚚 ПОЛУЧЕНИЕ\n{delivery_text}\n\n"
            f"💳 Оплата: {data.payment_method}\n"
            f"💰 Сумма товаров: {float(total):.2f} €\n"
            f"🚚 Стоимость доставки: рассчитывается отдельно\n"
            f"📋 Статус: Новый"
        )

        reply_markup = None
        if buyer_username:
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💬 Связаться с покупателем",
                            url=f"https://t.me/{buyer_username}",
                        )
                    ]
                ]
            )

        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=message,
                reply_markup=reply_markup,
            )
        except Exception:
            pass

    return {
        "ok": True,
        "order_id": order_id,
        "items_total": float(total),
        "delivery_price": None,
        "status": "new",
    }

@app.get("/api/admin/retail/orders")
async def api_admin_retail_orders(
    x_telegram_init_data: Optional[str] = Header(None),
):
    verified_user_id = verify_telegram_init_data(
        x_telegram_init_data or ""
    )

    if verified_user_id != int(ADMIN_ID):
        raise HTTPException(403, "Доступ запрещён")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT *
            FROM retail_orders
            WHERE is_archived = 0
            ORDER BY id DESC
            LIMIT 200
            """
        )
        orders = [dict(row) for row in await cursor.fetchall()]
        await cursor.close()

        for order in orders:
            cursor = await db.execute(
                """
                SELECT product_name, flavor_name,
                       quantity, unit_price, line_total
                FROM retail_order_items
                WHERE order_id = ?
                ORDER BY id
                """,
                (order["id"],)
            )
            order["items"] = [
                dict(row) for row in await cursor.fetchall()
            ]
            await cursor.close()

    return {"orders": orders}

@app.delete("/api/admin/retail/orders/{order_id}")
async def api_archive_retail_order(
    order_id: int,
    x_telegram_init_data: Optional[str] = Header(None),
):
    user_id = verify_telegram_init_data(
        x_telegram_init_data or ""
    )

    if user_id != int(ADMIN_ID):
        raise HTTPException(403, "Доступ запрещён")

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            UPDATE retail_orders
            SET is_archived = 1
            WHERE id = ? AND is_archived = 0
            """,
            (order_id,),
        )
        changed = cursor.rowcount
        await cursor.close()

        if changed != 1:
            raise HTTPException(
                404, "Заказ не найден или уже удалён"
            )

        await db.commit()

    return {"ok": True, "order_id": order_id}
    
class RetailOrderStatusIn(BaseModel):
    status: str


@app.patch("/api/admin/retail/orders/{order_id}/status")
async def api_update_retail_order_status(
    order_id: int,
    data: RetailOrderStatusIn,
    x_telegram_init_data: Optional[str] = Header(None),
):
    verified_user_id = verify_telegram_init_data(
        x_telegram_init_data or ""
    )

    if verified_user_id != int(ADMIN_ID):
        raise HTTPException(403, "Доступ запрещён")

    allowed_statuses = ("new", "shipped", "done", "cancelled")

    if data.status not in allowed_statuses:
        raise HTTPException(400, "Неверный статус заказа")

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("BEGIN IMMEDIATE")

            cursor = await db.execute(
                """
                SELECT delivery_type, status
                FROM retail_orders
                WHERE id = ?
                """,
                (order_id,),
            )
            order = await cursor.fetchone()
            await cursor.close()

            if not order:
                raise HTTPException(404, "Заказ не найден")

            delivery_type, old_status = order

            if delivery_type == "pickup" and data.status == "shipped":
                raise HTTPException(
                    400, "Самовывоз нельзя отметить отправленным"
                )

            if old_status == "cancelled" and data.status != "cancelled":
                raise HTTPException(
                    400, "Отменённый заказ нельзя восстановить"
                )

            if data.status == "cancelled" and old_status != "cancelled":
                cursor = await db.execute(
                    """
                    SELECT flavor_id, quantity
                    FROM retail_order_items
                    WHERE order_id = ?
                    """,
                    (order_id,),
                )
                items = await cursor.fetchall()
                await cursor.close()

                for flavor_id, quantity in items:
                    await db.execute(
                        """
                        UPDATE retail_flavors
                        SET stock = stock + ?
                        WHERE id = ?
                        """,
                        (quantity, flavor_id),
                    )

            await db.execute(
                """
                UPDATE retail_orders
                SET status = ?
                WHERE id = ?
                """,
                (data.status, order_id),
            )

            await db.commit()

        except Exception:
            await db.rollback()
            raise

    # Уведомляем покупателя только при изменении статуса
    if old_status != data.status and data.status in ("done", "cancelled"):
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT user_id FROM retail_orders WHERE id = ?",
                (order_id,),
            )
            buyer = await cursor.fetchone()
            await cursor.close()

        if buyer and bot:
            buyer_id = int(buyer[0])

            if data.status == "done":
                message = (
                    f"✅ Ваш заказ №{order_id} выполнен!\n\n"
                    "Спасибо за заказ в Puffy Store!"
                )
            else:
                message = (
                    f"❌ Ваш заказ №{order_id} отменён.\n\n"
                    "Для уточнения деталей свяжитесь с менеджером."
                )

            try:
                await bot.send_message(
                    chat_id=buyer_id,
                    text=message,
                )
            except Exception:
                pass

    return {"ok": True, "order_id": order_id, "status": data.status}

@app.get("/api/retail/my-orders")
async def api_retail_my_orders(
    x_telegram_init_data: Optional[str] = Header(None),
):
    user_id = verify_telegram_init_data(
        x_telegram_init_data or ""
    )

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT *
            FROM retail_orders
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 100
            """,
            (user_id,),
        )
        orders = [dict(row) for row in await cursor.fetchall()]
        await cursor.close()

        for order in orders:
            cursor = await db.execute(
                """
                SELECT product_id, flavor_id,
                       product_name, flavor_name,
                       quantity, unit_price, line_total
                FROM retail_order_items
                WHERE order_id = ?
                ORDER BY id
                """,
                (order["id"],),
            )
            order["items"] = [
                dict(row) for row in await cursor.fetchall()
            ]
            await cursor.close()

    return {"orders": orders}

@app.post("/api/retail/my-orders/{order_id}/cancel")
async def api_cancel_my_retail_order(
    order_id: int,
    x_telegram_init_data: Optional[str] = Header(None),
):
    user_id = verify_telegram_init_data(
        x_telegram_init_data or ""
    )

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("BEGIN IMMEDIATE")

            cursor = await db.execute(
                """
                SELECT status
                FROM retail_orders
                WHERE id = ? AND user_id = ?
                """,
                (order_id, user_id),
            )
            order = await cursor.fetchone()
            await cursor.close()

            if not order:
                raise HTTPException(404, "Заказ не найден")

            if order[0] == "cancelled":
                await db.rollback()
                return {
                    "ok": True,
                    "order_id": order_id,
                    "status": "cancelled",
                }

            if order[0] != "new":
                raise HTTPException(
                    400,
                    "Этот заказ уже нельзя отменить самостоятельно"
                )

            cursor = await db.execute(
                """
                SELECT flavor_id, quantity
                FROM retail_order_items
                WHERE order_id = ?
                """,
                (order_id,),
            )
            items = await cursor.fetchall()
            await cursor.close()

            for flavor_id, quantity in items:
                await db.execute(
                    """
                    UPDATE retail_flavors
                    SET stock = stock + ?
                    WHERE id = ?
                    """,
                    (quantity, flavor_id),
                )

            await db.execute(
                """
                UPDATE retail_orders
                SET status = 'cancelled'
                WHERE id = ?
                """,
                (order_id,),
            )

            await db.commit()

        except Exception:
            await db.rollback()
            raise
            
    if bot:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"❌ Ваш заказ №{order_id} отменён.\n\n"
                    "Заказ успешно отменён, товары возвращены на склад.\n\n"
                    "Вы можете оформить новый заказ в Puffy Store."
                ),
            )
        except Exception:
            import logging
            logging.exception(
                "Не удалось отправить уведомление об отмене заказа %s",
                order_id,
            )

    return {
        "ok": True,
        "order_id": order_id,
        "status": "cancelled",
    }

