import aiosqlite
from datetime import datetime
from typing import Optional, List, Dict, Any

DB_PATH = "mono.db"


async def init_db():
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
        try:
            await db.execute("ALTER TABLE products ADD COLUMN photo_file_id TEXT")
        except Exception:
            pass
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_id INTEGER,
                status TEXT DEFAULT 'pending',
                used_discount INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)
        await db.commit()


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


async def create_order(user_id: int, product_id: int, used_discount: bool = False) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO orders (user_id, product_id, used_discount, created_at)
               VALUES (?, ?, ?, ?)""",
            (user_id, product_id, int(used_discount), datetime.now().isoformat())
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

        await db.execute("UPDATE orders SET status = 'completed' WHERE id = ?", (order_id,))
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


async def get_pending_orders() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT o.*, u.username, u.full_name, p.name as product_name 
               FROM orders o 
               JOIN users u ON o.user_id = u.user_id 
               LEFT JOIN products p ON o.product_id = p.id
               WHERE o.status = 'pending' ORDER BY o.created_at DESC"""
        ) as cursor:
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
