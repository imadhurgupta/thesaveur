import sqlite3
import hashlib
import os
import random
import string

# In Docker, DATA_DIR=/app/data (a persistent volume). Locally it uses the project folder.
_data_dir = os.environ.get('DATA_DIR', os.path.dirname(__file__))
os.makedirs(_data_dir, exist_ok=True)
DB_PATH = os.path.join(_data_dir, 'am_trader.db')

def generate_user_id():
    chars = string.ascii_uppercase + string.digits
    return "USR-" + "".join(random.choice(chars) for _ in range(8))

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Check if orders table has user_id column; if not, drop it and recreate it
    try:
        cursor.execute("SELECT user_id FROM orders LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
        if cursor.fetchone():
            print("[MIGRATION] 'orders' table is out of date (missing 'user_id'). Recreating 'orders' and 'order_items'...")
            cursor.execute("DROP TABLE IF EXISTS order_items")
            cursor.execute("DROP TABLE IF EXISTS orders")
            conn.commit()

    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            image_filename TEXT,
            price REAL DEFAULT 0.0,
            stocks INTEGER DEFAULT 0,
            is_bestseller INTEGER DEFAULT 0,
            unit TEXT DEFAULT '100g'
        );

        CREATE TABLE IF NOT EXISTS product_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            image_filename TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS enquiries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            product_interest TEXT,
            message TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            otp TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            total_amount REAL NOT NULL,
            shipping_address TEXT NOT NULL,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            zip_code TEXT NOT NULL,
            payment_method TEXT NOT NULL,
            status TEXT DEFAULT 'Processing',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products (id)
        );

        CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            discount_type TEXT NOT NULL DEFAULT 'percent',
            discount_value REAL NOT NULL,
            min_order_amount REAL DEFAULT 0,
            max_uses INTEGER DEFAULT 0,
            used_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            expires_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS email_verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            otp TEXT NOT NULL,
            purpose TEXT NOT NULL DEFAULT 'signup',
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS carousel_slides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_filename TEXT NOT NULL,
            badge_icon TEXT,
            badge_text TEXT,
            title TEXT NOT NULL,
            description TEXT,
            button_text TEXT DEFAULT 'Explore Products',
            button_link TEXT DEFAULT '/products',
            slide_order INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            description TEXT,
            image_filename TEXT,
            display_order INTEGER DEFAULT 0
        );

    ''')
    conn.commit()

    # Safe migration for existing users table
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Profile columns
    for col in ['phone TEXT', 'shipping_address TEXT', 'city TEXT', 'state TEXT', 'zip_code TEXT']:
        try:
            col_name = col.split()[0]
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col}")
            conn.commit()
            print(f"[MIGRATION] Added column '{col_name}' to 'users' table.")
        except sqlite3.OperationalError:
            pass

    # Safe migration for enquiries status column
    try:
        cursor.execute("ALTER TABLE enquiries ADD COLUMN status TEXT DEFAULT 'Pending'")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Safe migration for existing products table
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN price REAL DEFAULT 0.0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE products ADD COLUMN stocks INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Safe migration for discount_percent on products
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN discount_percent REAL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Safe migration for promo fields on orders
    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN discount_amount REAL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN promo_code TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Safe migration: alphanumeric order number
    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN order_number TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Seed default admin user if no admin exists
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
    admin_count = cursor.fetchone()[0]
    if admin_count == 0:
        admin_email = 'admin@thesaveur.com'
        admin_pass_hash = hashlib.sha256('admin123'.encode('utf-8')).hexdigest()
        cursor.execute(
            "INSERT INTO users (id, full_name, email, password_hash, is_admin) VALUES (?, ?, ?, ?, 1)",
            (generate_user_id(), 'System Admin', admin_email, admin_pass_hash)
        )
        conn.commit()
        print("[OK] Seeded default admin account (admin@thesaveur.com / admin123).")

    conn.close()
    print("[OK] Database initialized successfully.")

if __name__ == '__main__':
    init_db()

