"""Banner API for Puffy Store Mini App.

Add to api.py after `app = FastAPI()`:
    from banners import router as banners_router
    app.include_router(banners_router)

Uses the project's existing SQLite database and persistent /data/photos directory.
"""

import hashlib
import hmac
import json
import os
import time
import uuid
from urllib.parse import parse_qsl, urlsplit

import aiosqlite
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from config import ADMIN_ID, BOT_TOKEN
from database import DB_PATH

router = APIRouter()
PHOTO_DIR = "/data/photos"
MAX_IMAGE_BYTES = 5 * 1024 * 1024


async def _ensure_table() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS store_banners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_url TEXT NOT NULL,
                link_url TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


def _require_telegram_admin(
    x_telegram_init_data: str | None = Header(default=None),
) -> None:
    if not x_telegram_init_data or not BOT_TOKEN:
        raise HTTPException(status_code=401, detail="Откройте админку через Telegram")
    try:
        data = dict(parse_qsl(x_telegram_init_data, keep_blank_values=True))
        received_hash = data.pop("hash")
        check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(received_hash, expected_hash):
            raise ValueError("invalid hash")
        auth_date = int(data["auth_date"])
        if not -300 <= time.time() - auth_date <= 86400:
            raise ValueError("expired")
        user_id = int(json.loads(data["user"])["id"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Неверная авторизация Telegram")
    if user_id != int(ADMIN_ID):
        raise HTTPException(status_code=403, detail="Доступ запрещён")


def _clean_link(link: str) -> str:
    link = (link or "").strip()
    if not link:
        return ""
    if len(link) > 2048:
        raise HTTPException(status_code=400, detail="Ссылка слишком длинная")
    parts = urlsplit(link)
    if parts.scheme.lower() not in ("https", "http") or not parts.hostname:
        raise HTTPException(status_code=400, detail="Укажите ссылку с https:// или http://")
    return link


async def _save_image(file: UploadFile) -> str:
    content = await file.read(MAX_IMAGE_BYTES + 1)
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Фото должно быть не больше 5 МБ")
    if content.startswith(b"\xff\xd8\xff"):
        ext = ".jpg"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        ext = ".png"
    elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        ext = ".webp"
    else:
        raise HTTPException(status_code=400, detail="Поддерживаются JPG, PNG и WEBP")
    os.makedirs(PHOTO_DIR, exist_ok=True)
    filename = f"banner_{uuid.uuid4().hex}{ext}"
    with open(os.path.join(PHOTO_DIR, filename), "wb") as output:
        output.write(content)
    return f"/media/{filename}"


async def _get_list(active_only: bool) -> list[dict]:
    await _ensure_table()
    where = "WHERE is_active = 1" if active_only else ""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT id, image_url, link_url, is_active, sort_order FROM store_banners "
            f"{where} ORDER BY sort_order ASC, id DESC"
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.get("/api/banners")
async def public_banners():
    return {"banners": await _get_list(True)}


@router.get("/api/admin/banners")
async def admin_banners(_: None = Depends(_require_telegram_admin)):
    return {"banners": await _get_list(False)}


@router.post("/api/admin/banners")
async def create_banner(
    file: UploadFile = File(...),
    link_url: str = Form(""),
    _: None = Depends(_require_telegram_admin),
):
    link = _clean_link(link_url)
    await _ensure_table()
    image_url = await _save_image(file)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO store_banners (image_url, link_url) VALUES (?, ?)",
            (image_url, link),
        )
        await db.commit()
        new_id = cursor.lastrowid
    return {"ok": True, "id": new_id, "image_url": image_url, "link_url": link}


class BannerChange(BaseModel):
    link_url: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


@router.patch("/api/admin/banners/{banner_id}")
async def update_banner(
    banner_id: int,
    data: BannerChange,
    _: None = Depends(_require_telegram_admin),
):
    await _ensure_table()
    sets: list[str] = []
    values: list = []
    if data.link_url is not None:
        sets.append("link_url = ?")
        values.append(_clean_link(data.link_url))
    if data.is_active is not None:
        sets.append("is_active = ?")
        values.append(int(data.is_active))
    if data.sort_order is not None:
        sets.append("sort_order = ?")
        values.append(data.sort_order)
    if not sets:
        return {"ok": True}
    values.append(banner_id)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f"UPDATE store_banners SET {', '.join(sets)} WHERE id = ?", values
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Баннер не найден")
    return {"ok": True}


@router.post("/api/admin/banners/{banner_id}/photo")
async def change_banner_photo(
    banner_id: int,
    file: UploadFile = File(...),
    _: None = Depends(_require_telegram_admin),
):
    await _ensure_table()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM store_banners WHERE id = ?", (banner_id,)) as c:
            if not await c.fetchone():
                raise HTTPException(status_code=404, detail="Баннер не найден")
    image_url = await _save_image(file)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE store_banners SET image_url = ? WHERE id = ?", (image_url, banner_id))
        await db.commit()
    return {"ok": True, "image_url": image_url}


@router.delete("/api/admin/banners/{banner_id}")
async def delete_banner(
    banner_id: int,
    _: None = Depends(_require_telegram_admin),
):
    await _ensure_table()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM store_banners WHERE id = ?", (banner_id,))
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Баннер не найден")
    return {"ok": True}
