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

def generate_product_id():
    chars = string.ascii_uppercase + string.digits
    return "PROD-" + "".join(random.choice(chars) for _ in range(8))

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Check if products table exists and has INTEGER id type; if so, migrate
    try:
        cursor.execute("PRAGMA table_info(products)")
        columns = cursor.fetchall()
        if columns:
            id_col = next((c for c in columns if c[1] == 'id'), None)
            if id_col and 'INTEGER' in id_col[2].upper():
                print("[MIGRATION] 'products' table is using INTEGER IDs. Dropping product-related tables for alphanumeric migration...")
                cursor.execute("DROP TABLE IF EXISTS reviews")
                cursor.execute("DROP TABLE IF EXISTS product_images")
                cursor.execute("DROP TABLE IF EXISTS order_items")
                cursor.execute("DROP TABLE IF EXISTS products")
                conn.commit()
    except sqlite3.OperationalError:
        pass

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
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            image_filename TEXT,
            price REAL DEFAULT 0.0,
            stocks INTEGER DEFAULT 0,
            is_bestseller INTEGER DEFAULT 0,
            unit TEXT DEFAULT '100g',
            shipping_charge REAL DEFAULT 0.0,
            gst_rate REAL DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS product_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            image_filename TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            user_name TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            image_filename TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
            contact_name TEXT,
            contact_email TEXT,
            contact_phone TEXT,
            razorpay_order_id TEXT,
            razorpay_payment_id TEXT,
            razorpay_signature TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            original_price REAL DEFAULT 0,
            discount_percent REAL DEFAULT 0,
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

        CREATE TABLE IF NOT EXISTS location_shipping_charges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state TEXT NOT NULL UNIQUE,
            charge REAL NOT NULL DEFAULT 0.0
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

    # Safe migration for image_filename on reviews
    try:
        cursor.execute("ALTER TABLE reviews ADD COLUMN image_filename TEXT")
        conn.commit()
        print("[MIGRATION] Added column 'image_filename' to 'reviews' table.")
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

    # Safe migration for gst_rate on products
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN gst_rate REAL DEFAULT 0.0")
        conn.commit()
        print("[MIGRATION] Added column 'gst_rate' to 'products' table.")
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

    # Safe migration: contact information on orders
    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN contact_name TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN contact_email TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN contact_phone TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Safe migration: Razorpay integration columns
    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN razorpay_order_id TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN razorpay_payment_id TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN razorpay_signature TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Safe migration: original_price and discount_percent on order_items
    try:
        cursor.execute("ALTER TABLE order_items ADD COLUMN original_price REAL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE order_items ADD COLUMN discount_percent REAL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Safe migration: shipping_charge on products
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN shipping_charge REAL DEFAULT 0.0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Safe migration: shipping_charge on orders
    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN shipping_charge REAL DEFAULT 0.0")
        conn.commit()
    except sqlite3.OperationalError:
        pass


    # Seed products only if table is empty
    cursor.execute("SELECT COUNT(*) FROM products")
    count = cursor.fetchone()[0]
    if count == 0:
        products = [
            ('Assam Black Tea', 'Tea', 'Rich, full-bodied Assam black tea with a bold malty flavor. Sourced directly from single-estate tea gardens.', 'Tea.jpg', 180.0, 50, 1, '250g'),
            ('Organic Green Tea', 'Tea', 'Fresh, anti-oxidant rich green tea leaves with a clean, delicate finish.', 'Green-Tea.jpg', 220.0, 40, 0, '200g'),
            ('Garam Masala', 'Spices', 'A highly aromatic blend of premium roasted spices including cardamom, cinnamon, cloves, and nutmeg.', 'Garam-Masala.jpg', 150.0, 80, 1, '100g'),
            ('Pure Turmeric Powder', 'Spices', 'High-curcumin golden turmeric powder ground from sun-dried roots.', 'Turmeric-Powder.jpg', 110.0, 120, 0, '200g'),
            ('Black Pepper Powder', 'Spices', 'Bold, pungent ground black pepper sourced from Malabar.', 'Black-Papper.jpg', 130.0, 60, 0, '100g'),
            ('Red Chilli Powder', 'Spices', 'Vibrant, medium-hot ground red chillies for rich color and heat.', 'Red-Chilli-Powder.jpg', 120.0, 90, 1, '150g'),
            ('Aamchur Powder', 'Spices', 'Tangy dry mango powder perfect for adding a sour punch to dishes.', 'Aamchur-Powder.jpg', 95.0, 70, 0, '100g'),
            ('Premium Cotton T-Shirt', 'Cloths', 'Classic fit crew neck t-shirt made of 100% organic cotton. Super soft and breathable.', 'fashion.png', 599.0, 150, 1, '1 Unit'),
            ('Canvas Tote Bag', 'Cloths', 'Heavy-duty cotton canvas tote bag with reinforced handles for everyday utility.', 'fashion.png', 349.0, 110, 0, '1 Unit')
        ]
        seeded_products = []
        for idx, p in enumerate(products):
            prod_id = generate_product_id()
            seeded_products.append((prod_id,) + p)
            
        cursor.executemany(
            "INSERT INTO products (id, name, category, description, image_filename, price, stocks, is_bestseller, unit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            seeded_products
        )
        conn.commit()
        print(f"[OK] Seeded {len(products)} products with alphanumeric IDs.")

    # Seed product images if product_images is empty
    cursor.execute("SELECT COUNT(*) FROM product_images")
    img_count = cursor.fetchone()[0]
    if img_count == 0:
        all_prods = cursor.execute("SELECT id, image_filename FROM products").fetchall()
        for p in all_prods:
            cursor.execute("INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (p['id'], p['image_filename']))
            cursor.execute("INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (p['id'], p['image_filename']))
        conn.commit()
        print("[OK] Seeded default product images.")

    # Seed default admin user if no admin exists
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
    admin_count = cursor.fetchone()[0]
    if admin_count == 0:
        admin_email = 'admin@thesaveur.com'
        admin_pass_hash = hashlib.sha256('admin123'.encode('utf-8')).hexdigest()
        cursor.execute(
            "INSERT INTO users (id, full_name, email, password_hash, is_admin) VALUES (?, ?, ?, ?, 1)",
            ('USR-ADMIN', 'System Admin', admin_email, admin_pass_hash)
        )
        conn.commit()
        print("[OK] Seeded default admin account (admin@thesaveur.com / admin123).")

    # Seed carousel slides if empty
    cursor.execute("SELECT COUNT(*) FROM carousel_slides")
    slide_count = cursor.fetchone()[0]
    if slide_count == 0:
        slides_data = [
            (
                'hero_tea_garden.png',
                'leaf',
                'Direct from Source',
                "Premium Handpicked\nOrganic Tea",
                'Sourced from single-estate organic gardens in Assam and Darjeeling. 100% natural, whole-leaf teas.',
                'Shop Teas',
                '/products?category=tea',
                0
            ),
            (
                'Garam-Masala.jpg',
                'sparkles',
                'Aromatic & Pure',
                "Rich & Authentic\nIndian Spices",
                'Pure, high-essential-oil spices ground to perfection. No artificial colors or additives.',
                'Explore Spices',
                '/products?category=spices',
                1
            ),
            (
                'fashion.png',
                'shirt',
                '100% Cotton',
                "Premium Organic\nApparel & Cloths",
                'Sleek, everyday wear crafted from breathable, sustainably sourced organic cotton.',
                'Shop Apparel',
                '/products?category=cloths',
                2
            )
        ]
        cursor.executemany(
            "INSERT INTO carousel_slides (image_filename, badge_icon, badge_text, title, description, button_text, button_link, slide_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            slides_data
        )
        conn.commit()
        print("[OK] Seeded default carousel slides.")

    # Seed categories if empty
    cursor.execute("SELECT COUNT(*) FROM categories")
    cat_count = cursor.fetchone()[0]
    if cat_count == 0:
        categories_data = [
            ('Tea', 'Premium Tea', 'Finest handpicked teas from single-estate gardens.', 'Tea.jpg', 0),
            ('Spices', 'Authentic Spices', 'Pure, aromatic ground and whole spices to elevate your cooking.', 'Garam-Masala.jpg', 1),
            ('Cloths', 'Apparel & Cloths', 'Comfortable and stylish premium wear made from organic cotton.', 'fashion.png', 2)
        ]
        cursor.executemany(
            "INSERT INTO categories (name, display_name, description, image_filename, display_order) VALUES (?, ?, ?, ?, ?)",
            categories_data
        )
        conn.commit()
        print("[OK] Seeded default categories.")

    # Seed default reviews if table is empty
    cursor.execute("SELECT COUNT(*) FROM reviews")
    review_count = cursor.fetchone()[0]
    if review_count == 0:
        reviews_data = [
            (1, 'Aarav Sharma', 5, 'Absolutely loved the malty flavor of this Assam tea. Tastes exactly like traditional estate tea! Perfect morning brew.'),
            (1, 'Priya Patel', 4, 'Great quality whole leaves. Very aromatic and soothing. Highly recommended for tea lovers.'),
            (3, 'Rohan Das', 5, 'Extremely fresh and strong aroma. A little goes a long way. This Garam Masala is a game changer for my cooking!'),
            (3, 'Anjali Gupta', 5, 'The perfect spice blend for my curries. It adds a premium warmth and richness to the dishes. Will definitely buy again.'),
            (4, 'Vikram Malhotra', 4, 'Very vibrant yellow color. You can tell it has high curcumin content and is extremely pure.'),
            (4, 'Meera Sen', 5, 'Excellent purity. Tastes authentic and earthy. Perfect for cooking and making golden milk!'),
            (6, 'Suresh Kumar', 5, 'Very hot and vibrant red color. Excellent quality chilli powder.')
        ]
        cursor.executemany(
            "INSERT INTO reviews (product_id, user_name, rating, comment) VALUES (?, ?, ?, ?)",
            reviews_data
        )
        conn.commit()
        print("[OK] Seeded default reviews.")

    # Seed location shipping charges if table is empty
    cursor.execute("SELECT COUNT(*) FROM location_shipping_charges")
    loc_charge_count = cursor.fetchone()[0]
    if loc_charge_count == 0:
        loc_charges = [
            ('Delhi', 40.0),
            ('New Delhi', 40.0),
            ('Maharashtra', 80.0),
            ('Karnataka', 90.0),
            ('Assam', 100.0),
            ('West Bengal', 70.0),
            ('Tamil Nadu', 90.0),
            ('Haryana', 50.0),
            ('Uttar Pradesh', 50.0),
            ('Default', 60.0)
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
