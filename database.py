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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, product_id)
            )
        """)

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
                city TEXT,
                payment TEXT,
                place TEXT,
                items_text TEXT,
                total REAL,
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
                # === ОПТ ===
        await db.execute("""
            CREATE TABLE IF NOT EXISTS wholesale_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT
            )
        """)

        
        for category_name in [
            "Жижи",
            "Одноразки",
            "Поды",
            "Картриджи",
            "Снюс"
        ]:
            await db.execute(
                """
                INSERT INTO wholesale_categories (name, created_at)
                SELECT ?, ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM wholesale_categories
                    WHERE name = ?
                )
                """,
                (
                    category_name,
                    datetime.now().isoformat(),
                    category_name
                )
            )

        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS wholesale_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER,
                name TEXT NOT NULL,
                photo_url TEXT,
                is_visible INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY (category_id) REFERENCES wholesale_categories(id)
            )
        """)

        # Порядок отображения оптовых товаров
        async with db.execute(
            "PRAGMA table_info(wholesale_products)"
        ) as cursor:
            columns = [row[1] for row in await cursor.fetchall()]

        if "sort_order" not in columns:
            await db.execute(
                "ALTER TABLE wholesale_products "
                "ADD COLUMN sort_order INTEGER DEFAULT 0"
            )
            
        await db.execute("""
            CREATE TABLE IF NOT EXISTS wholesale_price_tiers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                min_qty INTEGER NOT NULL,
                price REAL NOT NULL,
                FOREIGN KEY (product_id) REFERENCES wholesale_products(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS wholesale_flavors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                name TEXT NOT NULL,
                stock INTEGER DEFAULT 0,
                FOREIGN KEY (product_id) REFERENCES wholesale_products(id)
            )
        """)
        await db.commit()

# === НОВАЯ РОЗНИЦА ===

        await db.execute("""
            CREATE TABLE IF NOT EXISTS retail_categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)

        for category_id, category_name in [
            (1, "Жижи"),
            (2, "Одноразки"),
            (3, "Поды"),
            (4, "Картриджи"),
            (5, "Снюс")
        ]:
            await db.execute(
                """
                INSERT OR IGNORE INTO retail_categories (id, name)
                VALUES (?, ?)
                """,
                (category_id, category_name)
            )

        await db.execute("""
            CREATE TABLE IF NOT EXISTS retail_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                photo_url TEXT,
                is_visible INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY (category_id)
                    REFERENCES retail_categories(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS retail_flavors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                stock INTEGER DEFAULT 0,
                FOREIGN KEY (product_id)
                    REFERENCES retail_products(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS retail_price_tiers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                min_qty INTEGER NOT NULL,
                price REAL NOT NULL,
                FOREIGN KEY (product_id)
                    REFERENCES retail_products(id)
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


async def get_all_orders():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT o.*, u.username, u.full_name
            FROM orders o
            LEFT JOIN users u ON u.user_id = o.user_id
            ORDER BY o.id DESC
            """
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_stats() -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            users = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM orders WHERE status = 'done'") as c:
            orders = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM products WHERE is_available = 1") as c:
            products = (await c.fetchone())[0]
        return {"users": users, "orders": orders, "products": products}


async def get_stats_period(period: str = "all") -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        if period == "today":
            date_filter = "AND date(created_at) = date('now', 'localtime')"
        elif period == "7d":
            date_filter = "AND date(created_at) >= date('now', 'localtime', '-7 day')"
        elif period == "30d":
            date_filter = "AND date(created_at) >= date('now', 'localtime', '-30 day')"
        else:
            date_filter = ""

        async with db.execute(
            f"SELECT COUNT(*) FROM orders WHERE status = 'done' {date_filter}"
        ) as c:
            orders = (await c.fetchone())[0]

        try:
            async with db.execute(
                f"SELECT COALESCE(SUM(total), 0) FROM orders WHERE status = 'done' {date_filter}"
            ) as c:
                revenue = (await c.fetchone())[0] or 0
        except Exception:
            revenue = 0

        return {"orders": orders, "revenue": revenue}


async def get_all_user_ids() -> List[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE is_blocked = 0") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def get_users_page(page: int = 0, per_page: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        offset = page * per_page
        async with db.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_users_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            return (await c.fetchone())[0]


async def block_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def unblock_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (user_id,))
        await db.commit()


async def is_user_blocked(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT is_blocked FROM users WHERE user_id = ?", (user_id,)) as c:
            row = await c.fetchone()
            return bool(row and row[0])


async def add_to_cart(user_id: int, product_id: int, quantity: int = 1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO cart (user_id, product_id, quantity)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, product_id) DO UPDATE SET quantity = quantity + ?""",
            (user_id, product_id, quantity, quantity)
        )
        await db.commit()


async def get_cart(user_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT c.*, p.name, p.price, p.photo_file_id
               FROM cart c
               JOIN products p ON c.product_id = p.id
               WHERE c.user_id = ?""",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def update_cart_quantity(user_id: int, product_id: int, quantity: int):
    async with aiosqlite.connect(DB_PATH) as db:
        if quantity <= 0:
            await db.execute("DELETE FROM cart WHERE user_id = ? AND product_id = ?", (user_id, product_id))
        else:
            await db.execute(
                "UPDATE cart SET quantity = ? WHERE user_id = ? AND product_id = ?",
                (quantity, user_id, product_id)
            )
        await db.commit()


async def clear_cart(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        await db.commit()


async def add_favorite(user_id: int, product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO favorites (user_id, product_id) VALUES (?, ?)",
            (user_id, product_id)
        )
        await db.commit()


async def remove_favorite(user_id: int, product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM favorites WHERE user_id = ? AND product_id = ?",
            (user_id, product_id)
        )
        await db.commit()


async def get_favorites(user_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT p.* FROM favorites f
               JOIN products p ON f.product_id = p.id
               WHERE f.user_id = ?""",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def is_favorite(user_id: int, product_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND product_id = ?",
            (user_id, product_id)
        ) as c:
            return await c.fetchone() is not None


async def assign_client_no(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT client_no FROM users WHERE user_id = ?", (user_id,)) as c:
            row = await c.fetchone()
            if row and row[0]:
                return
        async with db.execute("SELECT MAX(client_no) FROM users") as c:
            max_no = (await c.fetchone())[0] or 0
        await db.execute("UPDATE users SET client_no = ? WHERE user_id = ?", (max_no + 1, user_id))
        await db.commit()


async def get_order(order_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_order_status(order_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        await db.commit()


async def get_user_orders(user_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def add_message(user_id: int, text: str, from_admin: bool = False):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO messages (user_id, from_admin, text, created_at)
               VALUES (?, ?, ?, ?)""",
            (user_id, int(from_admin), text, datetime.now().isoformat())
        )
        await db.commit()


async def get_user_messages(user_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM messages WHERE user_id = ? ORDER BY id",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def delete_product(product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        await db.commit()

async def remove_from_cart(user_id: int, product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM cart WHERE user_id = ? AND product_id = ?",
            (user_id, product_id)
        )
        await db.commit()
        

async def get_cart_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM cart WHERE user_id = ?",
            (user_id,)
        ) as c:
            return (await c.fetchone())[0]


async def set_referrer_if_empty(user_id: int, referrer_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE users SET referrer_id = ?
               WHERE user_id = ? AND referrer_id IS NULL AND user_id != ?""",
            (referrer_id, user_id, referrer_id)
        )
        await db.commit()


async def set_user_blocked(user_id: int, blocked: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET is_blocked = ? WHERE user_id = ?",
            (int(blocked), user_id)
        )
        await db.commit()


async def set_order_status(order_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        async with db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)) as c:
            row = await c.fetchone()
        await db.commit()
        return dict(row) if row else None

async def get_messages(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM messages WHERE user_id = ? ORDER BY id",
            (user_id,)
        ) as c:
            rows = await c.fetchall()
            return [dict(r) for r in rows]


async def get_chat_list():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT m.user_id, u.username, u.full_name, 
                      MAX(m.id) as last_id, COUNT(*) as msg_count
               FROM messages m
               JOIN users u ON m.user_id = u.user_id
               GROUP BY m.user_id
               ORDER BY last_id DESC"""
        ) as c:
            rows = await c.fetchall()
            return [dict(r) for r in rows]


async def mark_messages_read(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE messages SET is_read = 1 WHERE user_id = ? AND from_admin = 0",
            (user_id,)
        )
        await db.commit()


async def get_profile(user_id: int):
    return await get_user(user_id)


async def on_first_order_referral(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT referrer_id FROM users WHERE user_id = ?", (user_id,)
        ) as c:
            row = await c.fetchone()
            if row and row[0]:
                await increment_referrals(row[0])


async def use_discount_and_decrement(user_id: int):
    await use_discount(user_id)


async def increment_purchases(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET purchases_count = purchases_count + 1 WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()


async def get_favorite_ids(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT product_id FROM favorites WHERE user_id = ?", (user_id,)
        ) as c:
            rows = await c.fetchall()
            return [r[0] for r in rows]


async def get_favorite_products(user_id: int):
    return await get_favorites(user_id)


async def delete_order(order_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        await db.commit()

async def get_categories():
    return []

async def create_category(name: str):
    return None

async def get_price_tiers(product_id: int = None):
    return []

async def set_price_tiers(product_id: int, tiers: list):
    return True

async def get_flavors(product_id: int = None):
    return []


# ==================== ОПТ ====================

async def get_wholesale_categories():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM wholesale_categories ORDER BY name") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def create_wholesale_category(name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO wholesale_categories (name, created_at) VALUES (?, ?)",
            (name, datetime.now().isoformat())
        )
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cursor:
            row = await cursor.fetchone()
            return row[0]
async def reorder_wholesale_products(
    category_id: int,
    product_ids: list[int]
):
    if len(product_ids) != len(set(product_ids)):
        raise ValueError("Повторяющиеся ID товаров")

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM wholesale_products WHERE category_id = ?",
            (category_id,)
        ) as cursor:
            rows = await cursor.fetchall()

        existing_ids = {row[0] for row in rows}

        if set(product_ids) != existing_ids:
            raise ValueError("Список товаров категории не совпадает")

        try:
            await db.execute("BEGIN")

            for position, product_id in enumerate(product_ids):
                await db.execute(
                    """
                    UPDATE wholesale_products
                    SET sort_order = ?
                    WHERE id = ? AND category_id = ?
                    """,
                    (position, product_id, category_id)
                )

            await db.commit()
        except Exception:
            await db.rollback()
            raise
            
async def get_wholesale_products(category_id: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        query = """
            SELECT
                p.*,
                (
                    SELECT COUNT(*)
                    FROM wholesale_flavors f
                    WHERE f.product_id = p.id
                ) AS flavors_count,
                (
                    SELECT COALESCE(SUM(f.stock), 0)
                    FROM wholesale_flavors f
                    WHERE f.product_id = p.id
                ) AS stock,
                (
                    SELECT COUNT(*)
                    FROM wholesale_price_tiers t
                    WHERE t.product_id = p.id
                ) AS prices
            FROM wholesale_products p
        """

        params = ()
        if category_id is not None:
            query += " WHERE p.category_id = ?"
            params = (category_id,)

        query += " ORDER BY p.sort_order ASC, p.name ASC"

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def create_wholesale_product(category_id: int, name: str, photo_url: str = None, tiers: list = None, flavors: list = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO wholesale_products 
               (category_id, name, photo_url, is_visible, created_at) 
               VALUES (?, ?, ?, 1, ?)""",
            (category_id, name, photo_url, datetime.now().isoformat())
        )
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cursor:
            row = await cursor.fetchone()
            product_id = row[0]

        if tiers:
            for t in tiers:
                await db.execute(
                    "INSERT INTO wholesale_price_tiers (product_id, min_qty, price) VALUES (?, ?, ?)",
                    (product_id, t["min_qty"], t["price"])
                )
        if flavors:
            for f in flavors:
                await db.execute(
                    "INSERT INTO wholesale_flavors (product_id, name, stock) VALUES (?, ?, ?)",
                    (product_id, f["name"], f.get("stock", 0))
                )
        await db.commit()
        return product_id

async def update_wholesale_product(product_id: int, name: str = None, photo_url: str = None, is_visible: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if photo_url is not None:
            updates.append("photo_url = ?")
            params.append(photo_url)
        if is_visible is not None:
            updates.append("is_visible = ?")
            params.append(is_visible)
        if updates:
            params.append(product_id)
            await db.execute(f"UPDATE wholesale_products SET {', '.join(updates)} WHERE id = ?", params)
            await db.commit()

async def delete_wholesale_product(product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM wholesale_flavors WHERE product_id = ?", (product_id,))
        await db.execute("DELETE FROM wholesale_price_tiers WHERE product_id = ?", (product_id,))
        await db.execute("DELETE FROM wholesale_products WHERE id = ?", (product_id,))
        await db.commit()

async def get_price_tiers(product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM wholesale_price_tiers WHERE product_id = ? ORDER BY min_qty",
            (product_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def add_price_tier(product_id: int, min_qty: int, price: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO wholesale_price_tiers (product_id, min_qty, price) VALUES (?, ?, ?)",
            (product_id, min_qty, price)
        )
        await db.commit()

async def update_price_tier(tier_id: int, min_qty: int, price: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE wholesale_price_tiers
            SET min_qty = ?, price = ?
            WHERE id = ?
            """,
            (min_qty, price, tier_id)
        )
        await db.commit()
        
async def delete_price_tier(tier_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM wholesale_price_tiers WHERE id = ?", (tier_id,))
        await db.commit()

async def get_flavors(product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM wholesale_flavors WHERE product_id = ? ORDER BY name",
            (product_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def add_flavor(product_id: int, name: str, stock: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO wholesale_flavors (product_id, name, stock) VALUES (?, ?, ?)",
            (product_id, name, stock)
        )
        await db.commit()

async def update_flavor_stock(
    flavor_id: int,
    stock: int,
    name: str = None
):
    async with aiosqlite.connect(DB_PATH) as db:
        if name is not None:
            await db.execute(
                "UPDATE wholesale_flavors SET name = ?, stock = ? WHERE id = ?",
                (name.strip(), stock, flavor_id)
            )
        else:
            await db.execute(
                "UPDATE wholesale_flavors SET stock = ? WHERE id = ?",
                (stock, flavor_id)
            )

        await db.commit()

async def delete_flavor(flavor_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM wholesale_flavors WHERE id = ?", (flavor_id,))
        await db.commit()
