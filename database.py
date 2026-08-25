
import aiosqlite
from datetime import datetime
from typing import Optional, List, Dict, Any

DB_PATH = "/data/mono.db"


async def init_db():
    import os
    os.makedirs("/data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                language TEXT DEFAULT 'ru',
                referrer_id INTEGER,
                referrals_count INTEGER DEFAULT 0,
                successful_referrals INTEGER DEFAULT 0,
                purchases_count INTEGER DEFAULT 0,
                has_discount INTEGER DEFAULT 0,
                is_blocked INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                price REAL DEFAULT 15,
                volume TEXT,
                strength TEXT,
                photo_file_id TEXT,
                is_available INTEGER DEFAULT 1,
                created_at TEXT
            )
        """)
        await db.execute(
            "CREATE TABLE IF NOT EXISTS favorites ("
            "user_id INTEGER NOT NULL, "
            "product_id INTEGER NOT NULL, "
            "PRIMARY KEY (user_id, product_id))"
        )
        try:
            await db.execute("ALTER TABLE products ADD COLUMN photo_file_id TEXT")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE orders ADD COLUMN city TEXT")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE orders ADD COLUMN payment TEXT")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE orders ADD COLUMN place TEXT")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE orders ADD COLUMN items_text TEXT")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE orders ADD COLUMN total REAL")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE users ADD COLUMN client_no INTEGER")
        except Exception:
            pass
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_id INTEGER,
                status TEXT DEFAULT 'new',
                used_discount INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cart (
                user_id INTEGER,
                product_id INTEGER,
                quantity INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, product_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)
        await db.commit()


        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                from_admin INTEGER DEFAULT 0,
                text TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)


async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_user(user_id: int, username: str = None, full_name: str = None,
                      language: str = "ru", referrer_id: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR IGNORE INTO users 
               (user_id, username, full_name, language, referrer_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, username, full_name, language, referrer_id, datetime.now().isoformat())
        )
        await db.commit()
    await assign_client_no(user_id)


async def update_user_language(user_id: int, language: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET language = ? WHERE user_id = ?", (language, user_id))
        await db.commit()


async def set_referrer(user_id: int, referrer_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE users SET referrer_id = ? 
               WHERE user_id = ? AND referrer_id IS NULL AND user_id != ?""",
            (referrer_id, user_id, referrer_id)
        )
        await db.commit()


async def increment_referrals(referrer_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET successful_referrals = successful_referrals + 1 WHERE user_id = ?",
            (referrer_id,)
        )
        async with db.execute(
            "SELECT successful_referrals FROM users WHERE user_id = ?", (referrer_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0] >= 2:
                await db.execute(
                    "UPDATE users SET has_discount = 1, successful_referrals = 0 WHERE user_id = ?",
                    (referrer_id,)
                )
        await db.commit()


async def use_discount(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET has_discount = 0 WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_all_products(only_available: bool = True) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM products"
        if only_available:
            query += " WHERE is_available = 1"
        query += " ORDER BY id"
        async with db.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_product(product_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM products WHERE id = ?", (product_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def add_product(name: str, description: str = "", price: float = 15,
                      volume: str = "30ML", strength: str = "50MG",
                      photo_file_id: str = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO products (name, description, price, volume, strength, photo_file_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, description, price, volume, strength, photo_file_id, datetime.now().isoformat())
        )
        await db.commit()
        return cursor.lastrowid


async def update_product(product_id: int, **kwargs):
    if not kwargs:
        return
    fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [product_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE products SET {fields} WHERE id = ?", values)
        await db.commit()


async def create_order(
    user_id: int,
    product_id: int,
    used_discount: bool = False,
    city: str = None,
    payment: str = None,
    place: str = None,
    items_text: str = None,
    total: float = None,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        sql = """
            INSERT INTO orders (
                user_id, product_id, used_discount, status, created_at,
                city, payment, place, items_text, total
            ) VALUES (?, ?, ?, 'new', ?, ?, ?, ?, ?, ?)
        """
        cursor = await db.execute(
            sql,
            (
                user_id,
                product_id,
                int(used_discount),
                datetime.now().isoformat(),
                city,
                payment,
                place,
                items_text,
                total,
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def complete_order(order_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)) as cursor:
            order = await cursor.fetchone()
            if not order:
                return False
            order = dict(order)

        await db.execute("UPDATE orders SET status = 'done' WHERE id = ?", (order_id,))
        await db.execute(
            "UPDATE users SET purchases_count = purchases_count + 1 WHERE user_id = ?",
            (order["user_id"],)
        )

        async with db.execute(
            "SELECT referrer_id FROM users WHERE user_id = ?", (order["user_id"],)
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                referrer_id = row[0]
                await db.execute(
                    "UPDATE users SET successful_referrals = successful_referrals + 1 WHERE user_id = ?",
                    (referrer_id,)
                )
                async with db.execute(
                    "SELECT successful_referrals FROM users WHERE user_id = ?", (referrer_id,)
                ) as c2:
                    ref_row = await c2.fetchone()
                    if ref_row and ref_row[0] >= 2:
                        await db.execute(
                            "UPDATE users SET has_discount = 1, successful_referrals = 0 WHERE user_id = ?",
                            (referrer_id,)
                        )
        await db.commit()
        return True


async def get_pending_orders():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT o.*, u.username, u.full_name, p.name as product_name "
            "FROM orders o "
            "JOIN users u ON o.user_id = u.user_id "
            "LEFT JOIN products p ON o.product_id = p.id "
            "WHERE o.status IN ('new', 'pending', 'progress') "
            "ORDER BY o.created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_stats() -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            users = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed'") as c:
            orders = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM products WHERE is_available = 1") as c:
            products = (await c.fetchone())[0]
        return {"users": users, "orders": orders, "products": products}




async def get_all_user_ids() -> List[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def set_user_blocked(user_id: int, blocked: bool = True):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET is_blocked = ? WHERE user_id = ?",
            (1 if blocked else 0, user_id)
        )
        await db.commit()


async def get_users_page(page: int = 0, per_page: int = 5) -> List[Dict[str, Any]]:
    offset = page * per_page
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, username, full_name, is_blocked FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_users_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def add_to_cart(user_id: int, product_id: int, quantity: int = 1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO cart (user_id, product_id, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, product_id) DO UPDATE SET quantity = quantity + ?",
            (user_id, product_id, quantity, quantity),
        )
        await db.commit()


async def remove_from_cart(user_id: int, product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM cart WHERE user_id = ? AND product_id = ?",
            (user_id, product_id)
        )
        await db.commit()


async def update_cart_quantity(user_id: int, product_id: int, quantity: int):
    async with aiosqlite.connect(DB_PATH) as db:
        if quantity <= 0:
            await db.execute(
                "DELETE FROM cart WHERE user_id = ? AND product_id = ?",
                (user_id, product_id)
            )
        else:
            await db.execute(
                "UPDATE cart SET quantity = ? WHERE user_id = ? AND product_id = ?",
                (quantity, user_id, product_id)
            )
        await db.commit()


async def get_cart(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT c.product_id, c.quantity, p.name, p.price, p.photo_file_id "
            "FROM cart c JOIN products p ON p.id = c.product_id WHERE c.user_id = ?",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def clear_cart(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_cart_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM cart WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def set_order_status(order_id: int, status: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)) as cursor:
            order = await cursor.fetchone()
            if not order:
                return None
            order = dict(order)

        await db.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status, order_id)
        )
        await db.commit()
        return order


async def delete_order(order_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        await db.commit()
        return cursor.rowcount > 0


async def get_profile(user_id: int):
    user = await get_user(user_id)
    if not user:
        return None
    client_no = await assign_client_no(user_id)
    return {
        "user_id": user["user_id"],
        "username": user.get("username"),
        "full_name": user.get("full_name"),
        "purchases_count": user.get("purchases_count") or 0,
        "successful_referrals": user.get("successful_referrals") or 0,
        "has_discount": bool(user.get("has_discount") or 0),
        "is_blocked": bool(user.get("is_blocked") or 0),
        "client_no": client_no,
    }



async def add_message(user_id: int, text: str, from_admin: bool = False) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO messages (user_id, from_admin, text, is_read, created_at) VALUES (?, ?, ?, 0, ?)",
            (user_id, int(from_admin), text, datetime.now().isoformat()),
        )
        await db.commit()
        return cursor.lastrowid


async def get_chat_list():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        sql = (
            "SELECT m.user_id AS user_id, u.username AS username, u.full_name AS full_name, "
            "m.text AS last_text, m.created_at AS last_at, "
            "(SELECT COUNT(*) FROM messages mx WHERE mx.user_id = m.user_id "
            "AND mx.from_admin = 0 AND mx.is_read = 0) AS unread "
            "FROM messages m "
            "LEFT JOIN users u ON u.user_id = m.user_id "
            "INNER JOIN (SELECT user_id, MAX(id) AS max_id FROM messages GROUP BY user_id) t "
            "ON t.user_id = m.user_id AND t.max_id = m.id "
            "ORDER BY m.id DESC"
        )
        cursor = await db.execute(sql)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def mark_messages_read(user_id: int, from_admin_side: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        if from_admin_side:
            await db.execute(
                "UPDATE messages SET is_read = 1 WHERE user_id = ? AND from_admin = 0",
                (user_id,),
            )
        else:
            await db.execute(
                "UPDATE messages SET is_read = 1 WHERE user_id = ? AND from_admin = 1",
                (user_id,),
            )
        await db.commit()


async def on_first_order_referral(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT referrer_id, purchases_count FROM users WHERE user_id = ?",
            (user_id,),
        )
        user = await cur.fetchone()
        if not user:
            return
        if (user["purchases_count"] or 0) > 0:
            return
        ref = user["referrer_id"]
        if not ref:
            return
        await db.execute(
            "UPDATE users SET successful_referrals = COALESCE(successful_referrals, 0) + 1 WHERE user_id = ?",
            (ref,),
        )
        cur2 = await db.execute(
            "SELECT successful_referrals FROM users WHERE user_id = ?",
            (ref,),
        )
        ref_user = await cur2.fetchone()
        if ref_user and (ref_user["successful_referrals"] or 0) >= 2:
            await db.execute(
                "UPDATE users SET has_discount = 1 WHERE user_id = ?",
                (ref,),
            )
        await db.commit()


async def use_discount_and_decrement(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT has_discount, successful_referrals FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cur.fetchone()
        if not row or not row["has_discount"]:
            return False
        refs = max(0, (row["successful_referrals"] or 0) - 2)
        await db.execute(
            "UPDATE users SET has_discount = 0, successful_referrals = ? WHERE user_id = ?",
            (refs, user_id),
        )
        await db.commit()
        return True


async def increment_purchases(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET purchases_count = COALESCE(purchases_count, 0) + 1 WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()


async def set_referrer_if_empty(user_id: int, referrer_id: int) -> bool:
    if user_id == referrer_id:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT referrer_id FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cur.fetchone()
        if not row:
            return False
        if row["referrer_id"]:
            return False
        cur2 = await db.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            (referrer_id,),
        )
        if not await cur2.fetchone():
            return False
        await db.execute(
            "UPDATE users SET referrer_id = ? WHERE user_id = ? AND (referrer_id IS NULL OR referrer_id = 0)",
            (referrer_id, user_id),
        )
        await db.commit()
        return True


async def get_messages(user_id: int, limit: int = 100):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM messages WHERE user_id = ? ORDER BY id ASC LIMIT ?",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def assign_client_no(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT client_no FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cur.fetchone()
        if row and row["client_no"]:
            return int(row["client_no"])
        cur2 = await db.execute(
            "SELECT COALESCE(MAX(client_no), 0) FROM users"
        )
        m = await cur2.fetchone()
        next_no = int(m[0] or 0) + 1
        await db.execute(
            "UPDATE users SET client_no = ? WHERE user_id = ?",
            (next_no, user_id),
        )
        await db.commit()
        return next_no


async def add_favorite(user_id: int, product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO favorites (user_id, product_id) VALUES (?, ?)",
            (user_id, product_id),
        )
        await db.commit()


async def remove_favorite(user_id: int, product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM favorites WHERE user_id = ? AND product_id = ?",
            (user_id, product_id),
        )
        await db.commit()


async def get_favorite_ids(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT product_id FROM favorites WHERE user_id = ?",
            (user_id,),
        )
        rows = await cur.fetchall()
        return [r[0] for r in rows]


async def get_favorite_products(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT p.* FROM favorites f "
            "JOIN products p ON p.id = f.product_id "
            "WHERE f.user_id = ? ORDER BY p.name",
            (user_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
