import sqlite3
import hashlib
import os
import random
import string

# In Docker, DATA_DIR=/app/data (a persistent volume). Locally it uses the project folder.
_data_dir = os.environ.get('DATA_DIR', os.path.dirname(__file__))
os.makedirs(_data_dir, exist_ok=True)
DB_PATH = os.path.join(_data_dir, 'am_trader.db')


def translate_to_postgres(sql):
    """Convert SQLite-style SQL to PostgreSQL-compatible SQL."""
    sql = sql.replace('?', '%s')
    sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
    sql = sql.replace('AUTOINCREMENT', '')
    sql = sql.replace(' REAL', ' DOUBLE PRECISION')
    return sql


def _normalize_error(e):
    """Re-raise any DB exception as a sqlite3-compatible error."""
    import sqlite3 as _sq3
    e_name = type(e).__name__
    e_str = str(e)
    if any(x in e_name for x in ('IntegrityError', 'UniqueViolation', 'ForeignKeyViolation',
                                   'NotNullViolation', 'CheckViolation', 'ExclusionViolation')):
        raise _sq3.IntegrityError(e_str) from e
    if any(x in e_name for x in ('OperationalError', 'ProgrammingError', 'UndefinedTable',
                                   'UndefinedColumn', 'ActiveSqlTransaction', 'DatabaseError',
                                   'DuplicateColumn', 'DuplicateTable', 'InvalidTextRepresentation')):
        raise _sq3.OperationalError(e_str) from e
    raise e


class PostgresCursorWrapper:
    """Wraps a psycopg2 cursor to behave like a sqlite3 cursor."""

    def __init__(self, cur):
        self.cur = cur
        self.lastrowid = None

    def execute(self, sql, params=None):
        if params is not None:
            if not isinstance(params, (list, tuple)):
                params = (params,)
            sql = sql.replace('?', '%s')

        sql_stripped = sql.strip()
        is_insert = sql_stripped.upper().startswith('INSERT')
        if is_insert and 'RETURNING' not in sql_stripped.upper():
            sql = sql_stripped + ' RETURNING id'

        try:
            self.cur.execute(sql, params)
        except Exception as e:
            try:
                self.cur.connection.rollback()
            except Exception:
                pass
            _normalize_error(e)

        if is_insert:
            try:
                row = self.cur.fetchone()
                if row is not None:
                    try:
                        self.lastrowid = row[0]
                    except (KeyError, IndexError, TypeError):
                        self.lastrowid = row.get('id') if hasattr(row, 'get') else None
            except Exception:
                pass
        return self

    def executemany(self, sql, seq_of_parameters):
        sql = sql.replace('?', '%s')
        try:
            self.cur.executemany(sql, seq_of_parameters)
        except Exception as e:
            try:
                self.cur.connection.rollback()
            except Exception:
                pass
            _normalize_error(e)
        return self

    def executescript(self, script_str):
        statements = [s.strip() for s in script_str.split(';')]
        for stmt in statements:
            if not stmt:
                continue
            translated = translate_to_postgres(stmt)
            try:
                self.cur.execute(translated)
            except Exception as e:
                try:
                    self.cur.connection.rollback()
                except Exception:
                    pass
                _normalize_error(e)

    def fetchone(self):
        return self.cur.fetchone()

    def fetchall(self):
        return self.cur.fetchall()

    def __iter__(self):
        return iter(self.cur)

    @property
    def rowcount(self):
        return self.cur.rowcount

    @property
    def description(self):
        return self.cur.description


class PostgresConnectionWrapper:
    """Wraps a psycopg2 connection to behave like a sqlite3 connection."""

    def __init__(self, conn):
        self.conn = conn

    def cursor(self):
        import psycopg2.extras
        raw_conn = self.conn.conn if hasattr(self.conn, 'conn') else self.conn
        cur = raw_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        return PostgresCursorWrapper(cur)

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def executescript(self, script_str):
        cur = self.cursor()
        cur.executescript(script_str)
        return cur

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


def generate_user_id():
    chars = string.ascii_uppercase + string.digits
    return "USR-" + "".join(random.choice(chars) for _ in range(8))


def generate_product_id():
    chars = string.ascii_uppercase + string.digits
    return "PROD-" + "".join(random.choice(chars) for _ in range(8))


def get_db():
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        try:
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(db_url)
            return PostgresConnectionWrapper(conn)
        except Exception as e:
            print(f"[WARNING] Failed to connect to PostgreSQL: {e}. Falling back to SQLite.")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _safe_alter(cursor, conn, sql):
    """Run ALTER TABLE ... ADD COLUMN ... silently if column already exists."""
    try:
        cursor.execute(sql)
        conn.commit()
    except Exception as e:
        err = str(e).lower()
        if 'duplicate column' in err or 'already exists' in err:
            pass
        else:
            try:
                conn.rollback()
            except Exception:
                pass


def _row_count(cursor, table):
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    row = cursor.fetchone()
    if row is None:
        return 0
    try:
        return row[0]
    except (KeyError, IndexError, TypeError):
        return 0


def _pid(row):
    """Get product id from a row regardless of row type."""
    try:
        return row['id']
    except (KeyError, TypeError):
        return row[0]


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = isinstance(conn, PostgresConnectionWrapper)

    # ---- SQLite-only legacy migrations ----
    if not is_postgres:
        try:
            cursor.execute("PRAGMA table_info(products)")
            columns = cursor.fetchall()
            if columns:
                id_col = next((c for c in columns if c[1] == 'id'), None)
                if id_col and 'INTEGER' in id_col[2].upper():
                    print("[MIGRATION] Dropping INTEGER-id product tables for alphanumeric migration...")
                    for t in ["reviews", "product_images", "order_items", "products"]:
                        cursor.execute(f"DROP TABLE IF EXISTS {t}")
                    conn.commit()
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("SELECT user_id FROM orders LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
            if cursor.fetchone():
                print("[MIGRATION] Recreating orders and order_items...")
                cursor.execute("DROP TABLE IF EXISTS order_items")
                cursor.execute("DROP TABLE IF EXISTS orders")
                conn.commit()

    # ---- CREATE TABLES ----
    PK = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    REAL = "DOUBLE PRECISION" if is_postgres else "REAL"

    create_stmts = [
        f"""CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            sub_category TEXT,
            description TEXT,
            image_filename TEXT,
            price {REAL} DEFAULT 0.0,
            stocks INTEGER DEFAULT 0,
            is_bestseller INTEGER DEFAULT 0,
            unit TEXT DEFAULT '100g',
            shipping_charge {REAL} DEFAULT 0.0,
            gst_rate {REAL} DEFAULT 0.0,
            discount_percent {REAL} DEFAULT 0
        )""",

        f"""CREATE TABLE IF NOT EXISTS product_images (
            id {PK},
            product_id TEXT NOT NULL,
            image_filename TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        )""",

        f"""CREATE TABLE IF NOT EXISTS reviews (
            id {PK},
            product_id TEXT NOT NULL,
            user_name TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            image_filename TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        )""",

        f"""CREATE TABLE IF NOT EXISTS enquiries (
            id {PK},
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            product_interest TEXT,
            message TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",

        f"""CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            phone TEXT,
            shipping_address TEXT,
            city TEXT,
            state TEXT,
            zip_code TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",

        f"""CREATE TABLE IF NOT EXISTS password_resets (
            id {PK},
            email TEXT NOT NULL,
            otp TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",

        f"""CREATE TABLE IF NOT EXISTS orders (
            id {PK},
            user_id TEXT NOT NULL,
            total_amount {REAL} NOT NULL,
            shipping_address TEXT NOT NULL,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            zip_code TEXT NOT NULL,
            payment_method TEXT NOT NULL,
            status TEXT DEFAULT 'Processing',
            contact_name TEXT,
            contact_email TEXT,
            contact_phone TEXT,
            razorpay_order_id TEXT,
            razorpay_payment_id TEXT,
            razorpay_signature TEXT,
            discount_amount {REAL} DEFAULT 0,
            promo_code TEXT DEFAULT '',
            order_number TEXT DEFAULT '',
            shipping_charge {REAL} DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )""",

        f"""CREATE TABLE IF NOT EXISTS order_items (
            id {PK},
            order_id INTEGER NOT NULL,
            product_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price {REAL} NOT NULL,
            original_price {REAL} DEFAULT 0,
            discount_percent {REAL} DEFAULT 0,
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )""",

        f"""CREATE TABLE IF NOT EXISTS promo_codes (
            id {PK},
            code TEXT NOT NULL UNIQUE,
            discount_type TEXT NOT NULL DEFAULT 'percent',
            discount_value {REAL} NOT NULL,
            min_order_amount {REAL} DEFAULT 0,
            max_uses INTEGER DEFAULT 0,
            used_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            expires_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",

        f"""CREATE TABLE IF NOT EXISTS email_verifications (
            id {PK},
            email TEXT NOT NULL,
            otp TEXT NOT NULL,
            purpose TEXT NOT NULL DEFAULT 'signup',
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",

        f"""CREATE TABLE IF NOT EXISTS carousel_slides (
            id {PK},
            image_filename TEXT NOT NULL,
            badge_icon TEXT,
            badge_text TEXT,
            title TEXT NOT NULL,
            description TEXT,
            button_text TEXT DEFAULT 'Explore Products',
            button_link TEXT DEFAULT '/products',
            slide_order INTEGER DEFAULT 0
        )""",

        f"""CREATE TABLE IF NOT EXISTS categories (
            id {PK},
            name TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            description TEXT,
            image_filename TEXT,
            display_order INTEGER DEFAULT 0
        )""",

        f"""CREATE TABLE IF NOT EXISTS subcategories (
            id {PK},
            category_name TEXT NOT NULL,
            name TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            description TEXT,
            display_order INTEGER DEFAULT 0,
            FOREIGN KEY (category_name) REFERENCES categories (name) ON DELETE CASCADE
        )""",

        f"""CREATE TABLE IF NOT EXISTS location_shipping_charges (
            id {PK},
            state TEXT NOT NULL UNIQUE,
            charge {REAL} NOT NULL DEFAULT 0.0
        )""",
    ]

    for stmt in create_stmts:
        try:
            cursor.execute(stmt)
            conn.commit()
        except Exception as e:
            err = str(e).lower()
            if 'already exists' in err:
                try:
                    conn.rollback()
                except Exception:
                    pass
            else:
                print(f"[WARNING] CREATE TABLE failed: {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass

    # ---- SAFE ADD COLUMNS ----
    alter_stmts = [
        "ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN phone TEXT",
        "ALTER TABLE users ADD COLUMN shipping_address TEXT",
        "ALTER TABLE users ADD COLUMN city TEXT",
        "ALTER TABLE users ADD COLUMN state TEXT",
        "ALTER TABLE users ADD COLUMN zip_code TEXT",
        "ALTER TABLE enquiries ADD COLUMN status TEXT DEFAULT 'Pending'",
        "ALTER TABLE reviews ADD COLUMN image_filename TEXT",
        "ALTER TABLE products ADD COLUMN price REAL DEFAULT 0.0",
        "ALTER TABLE products ADD COLUMN stocks INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN discount_percent REAL DEFAULT 0",
        "ALTER TABLE products ADD COLUMN gst_rate REAL DEFAULT 0.0",
        "ALTER TABLE products ADD COLUMN shipping_charge REAL DEFAULT 0.0",
        "ALTER TABLE orders ADD COLUMN discount_amount REAL DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN promo_code TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN order_number TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN contact_name TEXT",
        "ALTER TABLE orders ADD COLUMN contact_email TEXT",
        "ALTER TABLE orders ADD COLUMN contact_phone TEXT",
        "ALTER TABLE orders ADD COLUMN razorpay_order_id TEXT",
        "ALTER TABLE orders ADD COLUMN razorpay_payment_id TEXT",
        "ALTER TABLE orders ADD COLUMN razorpay_signature TEXT",
        "ALTER TABLE orders ADD COLUMN shipping_charge REAL DEFAULT 0.0",
        "ALTER TABLE order_items ADD COLUMN original_price REAL DEFAULT 0",
        "ALTER TABLE order_items ADD COLUMN discount_percent REAL DEFAULT 0",
    ]
    for stmt in alter_stmts:
        _safe_alter(cursor, conn, stmt)

    # ---- SEED: products ----
    if _row_count(cursor, 'products') == 0:
        products = [
            ('Assam Black Tea', 'Tea', 'Black Tea',
             'Rich, full-bodied Assam black tea with a bold malty flavor. Sourced directly from single-estate tea gardens.',
             'Tea.jpg', 180.0, 50, 1, '250g'),
            ('Organic Green Tea', 'Tea', 'Green Tea',
             'Fresh, anti-oxidant rich green tea leaves with a clean, delicate finish.',
             'Green-Tea.jpg', 220.0, 40, 0, '200g'),
            ('Garam Masala', 'Spices', 'Blend Spices',
             'A highly aromatic blend of premium roasted spices including cardamom, cinnamon, cloves, and nutmeg.',
             'Garam-Masala.jpg', 150.0, 80, 1, '100g'),
            ('Pure Turmeric Powder', 'Spices', 'Ground Spices',
             'High-curcumin golden turmeric powder ground from sun-dried roots.',
             'Turmeric-Powder.jpg', 110.0, 120, 0, '200g'),
            ('Black Pepper Powder', 'Spices', 'Ground Spices',
             'Bold, pungent ground black pepper sourced from Malabar.',
             'Black-Papper.jpg', 130.0, 60, 0, '100g'),
            ('Red Chilli Powder', 'Spices', 'Ground Spices',
             'Vibrant, medium-hot ground red chillies for rich color and heat.',
             'Red-Chilli-Powder.jpg', 120.0, 90, 1, '150g'),
            ('Aamchur Powder', 'Spices', 'Ground Spices',
             'Tangy dry mango powder perfect for adding a sour punch to dishes.',
             'Aamchur-Powder.jpg', 95.0, 70, 0, '100g'),
            ('Premium Cotton T-Shirt', 'Cloths', 'Apparel',
             'Classic fit crew neck t-shirt made of 100% organic cotton. Super soft and breathable.',
             'fashion.png', 599.0, 150, 1, '1 Unit'),
            ('Canvas Tote Bag', 'Cloths', 'Accessories',
             'Heavy-duty cotton canvas tote bag with reinforced handles for everyday utility.',
             'fashion.png', 349.0, 110, 0, '1 Unit'),
        ]
        for p in products:
            prod_id = generate_product_id()
            cursor.execute(
                "INSERT INTO products (id, name, category, sub_category, description, image_filename, price, stocks, is_bestseller, unit) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (prod_id,) + p
            )
            conn.commit()
        print(f"[OK] Seeded {len(products)} products.")

    # ---- SEED: product_images ----
    if _row_count(cursor, 'product_images') == 0:
        all_prods = cursor.execute("SELECT id, image_filename FROM products").fetchall()
        for p in all_prods:
            pid = _pid(p)
            try:
                img = p['image_filename']
            except (KeyError, TypeError):
                img = p[1]
            cursor.execute(
                "INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (pid, img)
            )
            cursor.execute(
                "INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (pid, img)
            )
        conn.commit()
        print("[OK] Seeded default product images.")

    # ---- SEED: admin user ----
    if _row_count(cursor, 'users WHERE is_admin = 1') == 0:
        admin_pass_hash = hashlib.sha256('admin123'.encode('utf-8')).hexdigest()
        cursor.execute(
            "INSERT INTO users (id, full_name, email, password_hash, is_admin) VALUES (?, ?, ?, ?, 1)",
            ('USR-ADMIN', 'System Admin', 'admin@thesaveur.com', admin_pass_hash)
        )
        conn.commit()
        print("[OK] Seeded default admin account (admin@thesaveur.com / admin123).")

    # ---- SEED: carousel slides ----
    if _row_count(cursor, 'carousel_slides') == 0:
        slides_data = [
            ('hero_tea_garden.png', 'leaf', 'Direct from Source',
             'Premium Handpicked\nOrganic Tea',
             'Sourced from single-estate organic gardens in Assam and Darjeeling. 100% natural, whole-leaf teas.',
             'Shop Teas', '/products?category=tea', 0),
            ('Garam-Masala.jpg', 'sparkles', 'Aromatic & Pure',
             'Rich & Authentic\nIndian Spices',
             'Pure, high-essential-oil spices ground to perfection. No artificial colors or additives.',
             'Explore Spices', '/products?category=spices', 1),
            ('fashion.png', 'shirt', '100% Cotton',
             'Premium Organic\nApparel & Cloths',
             'Sleek, everyday wear crafted from breathable, sustainably sourced organic cotton.',
             'Shop Apparel', '/products?category=cloths', 2),
        ]
        cursor.executemany(
            "INSERT INTO carousel_slides (image_filename, badge_icon, badge_text, title, description, button_text, button_link, slide_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            slides_data
        )
        conn.commit()
        print("[OK] Seeded default carousel slides.")

    # ---- SEED: categories ----
    if _row_count(cursor, 'categories') == 0:
        categories_data = [
            ('Tea', 'Premium Tea', 'Finest handpicked teas from single-estate gardens.', 'Tea.jpg', 0),
            ('Spices', 'Authentic Spices', 'Pure, aromatic ground and whole spices.', 'Garam-Masala.jpg', 1),
            ('Cloths', 'Apparel & Cloths', 'Premium wear made from organic cotton.', 'fashion.png', 2),
        ]
        cursor.executemany(
            "INSERT INTO categories (name, display_name, description, image_filename, display_order) VALUES (?, ?, ?, ?, ?)",
            categories_data
        )
        conn.commit()
        print("[OK] Seeded default categories.")

    # ---- SEED: subcategories ----
    if _row_count(cursor, 'subcategories') == 0:
        subcategories_data = [
            ('Tea', 'Green Tea', 'Green Tea', 'Fresh, organic green tea leaves.', 0),
            ('Tea', 'Black Tea', 'Black Tea', 'Bold, premium estate black teas.', 1),
            ('Spices', 'Blend Spices', 'Blend Spices', 'Perfect mixes of ground spices.', 0),
            ('Spices', 'Ground Spices', 'Ground Spices', 'Single-ingredient ground spices.', 1),
            ('Cloths', 'Apparel', 'Apparel', 'Premium organic cotton clothing.', 0),
            ('Cloths', 'Accessories', 'Accessories', 'Sustainably sourced cloth accessories.', 1),
        ]
        cursor.executemany(
            "INSERT INTO subcategories (category_name, name, display_name, description, display_order) VALUES (?, ?, ?, ?, ?)",
            subcategories_data
        )
        conn.commit()
        print("[OK] Seeded default subcategories.")

    # ---- SEED: reviews (using real TEXT product IDs) ----
    if _row_count(cursor, 'reviews') == 0:
        all_prods = cursor.execute("SELECT id FROM products ORDER BY name ASC").fetchall()
        if len(all_prods) >= 7:
            reviews_data = [
                (_pid(all_prods[0]), 'Aarav Sharma', 5,
                 'Absolutely loved the malty flavor of this Assam tea. Tastes exactly like traditional estate tea! Perfect morning brew.'),
                (_pid(all_prods[0]), 'Priya Patel', 4,
                 'Great quality whole leaves. Very aromatic and soothing. Highly recommended for tea lovers.'),
                (_pid(all_prods[2]), 'Rohan Das', 5,
                 'Extremely fresh and strong aroma. This Garam Masala is a game changer for my cooking!'),
                (_pid(all_prods[2]), 'Anjali Gupta', 5,
                 'The perfect spice blend for my curries. Premium warmth and richness. Will definitely buy again.'),
                (_pid(all_prods[3]), 'Vikram Malhotra', 4,
                 'Very vibrant yellow color. High curcumin content and extremely pure.'),
                (_pid(all_prods[3]), 'Meera Sen', 5,
                 'Excellent purity. Tastes authentic and earthy. Perfect for cooking and making golden milk!'),
                (_pid(all_prods[5]), 'Suresh Kumar', 5,
                 'Very hot and vibrant red color. Excellent quality chilli powder.'),
            ]
            cursor.executemany(
                "INSERT INTO reviews (product_id, user_name, rating, comment) VALUES (?, ?, ?, ?)",
                reviews_data
            )
            conn.commit()
            print("[OK] Seeded default reviews.")

    # ---- SEED: location shipping ----
    if _row_count(cursor, 'location_shipping_charges') == 0:
        loc_charges = [
            ('Delhi', 40.0), ('New Delhi', 40.0), ('Maharashtra', 80.0),
            ('Karnataka', 90.0), ('Assam', 100.0), ('West Bengal', 70.0),
            ('Tamil Nadu', 90.0), ('Haryana', 50.0), ('Uttar Pradesh', 50.0),
            ('Default', 60.0),
        ]
        cursor.executemany(
            "INSERT INTO location_shipping_charges (state, charge) VALUES (?, ?)",
            loc_charges
        )
        conn.commit()
        print(f"[OK] Seeded {len(loc_charges)} location shipping rates.")

    conn.close()
    print("[OK] Database initialized successfully.")


if __name__ == '__main__':
    init_db()
