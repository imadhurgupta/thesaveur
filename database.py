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

    # Seed products only if table is empty
    cursor.execute("SELECT COUNT(*) FROM products")
    count = cursor.fetchone()[0]

    if count == 0:
        products = [
            # (name, category, description, image_filename, price, stocks, is_bestseller, unit)
            (
                'Premium Black Tea',
                'Tea',
                'Rich, full-bodied Assam black tea with a bold malty flavour. Perfect for a classic morning brew with milk.',
                'Tea.jpg',
                180.0,
                50,
                1,
                '250g'
            ),
            (
                'Green Tea',
                'Tea',
                'Hand-picked premium green tea leaves with a delicate, grassy aroma and antioxidant-rich benefits.',
                'Green-Tea.jpg',
                120.0,
                35,
                1,
                '100g'
            ),
            (
                'Black Pepper',
                'Spice',
                'Whole black peppercorns with a sharp, pungent aroma. Freshly ground to elevate every dish.',
                'Black-Papper.jpg',
                220.0,
                120,
                1,
                '200g'
            ),
            (
                'Black Salt (Kala Namak)',
                'Spice',
                'Natural volcanic black salt with a distinctive sulphurous aroma, used in chutneys, chaats, and ayurvedic recipes.',
                'Black-Salt.jpg',
                80.0,
                80,
                0,
                '250g'
            ),
            (
                'Aamchur Powder',
                'Spice',
                'Sun-dried raw mango powder with a tangy, fruity sourness – the secret ingredient for authentic Indian street food.',
                'Aamchur-Powder.jpg',
                95.0,
                40,
                0,
                '100g'
            ),
            (
                'Coriander Powder',
                'Spice',
                'Freshly ground coriander seeds with a warm, citrusy flavour. A staple spice in Indian, Middle Eastern, and Mexican cuisine.',
                'Coriandar-Powder.jpg',
                110.0,
                65,
                0,
                '200g'
            ),
            (
                'Cumin Powder',
                'Spice',
                'Stone-ground cumin with an earthy, nutty aroma that forms the backbone of countless spice blends and curries.',
                'Cumin-Powder.jpg',
                130.0,
                90,
                1,
                '100g'
            ),
            (
                'Garam Masala',
                'Spice',
                'A warm, aromatic blend of whole spices – cinnamon, cardamom, cloves, and more – slow-roasted and ground in-house.',
                'Garam-Masala.jpg',
                150.0,
                75,
                1,
                '100g'
            ),
            (
                'Red Chilli Powder',
                'Spice',
                'Vibrant, fiery red chilli powder made from sun-dried Kashmiri and Byadgi chillies. Adds colour and heat.',
                'Red-Chilli-Powder.jpg',
                145.0,
                110,
                0,
                '200g'
            ),
            (
                'Turmeric Powder',
                'Spice',
                'Pure, high-curcumin turmeric root powder with an intense golden colour and earthy, slightly bitter taste.',
                'Turmeric-Powder.jpg',
                115.0,
                150,
                1,
                '200g'
            ),
        ]

        cursor.executemany(
            "INSERT INTO products (name, category, description, image_filename, price, stocks, is_bestseller, unit) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            products
        )
        conn.commit()
        print(f"[OK] Seeded {len(products)} products.")
    else:
        # Update existing products with default price and stocks if they are 0.0 or 0
        cursor.execute("UPDATE products SET price = 180.0, stocks = 50 WHERE name = 'Premium Black Tea' AND price = 0.0")
        cursor.execute("UPDATE products SET price = 120.0, stocks = 35 WHERE name = 'Green Tea' AND price = 0.0")
        cursor.execute("UPDATE products SET price = 220.0, stocks = 120 WHERE name = 'Black Pepper' AND price = 0.0")
        cursor.execute("UPDATE products SET price = 80.0, stocks = 80 WHERE name = 'Black Salt (Kala Namak)' AND price = 0.0")
        cursor.execute("UPDATE products SET price = 95.0, stocks = 40 WHERE name = 'Aamchur Powder' AND price = 0.0")
        cursor.execute("UPDATE products SET price = 110.0, stocks = 65 WHERE name = 'Coriander Powder' AND price = 0.0")
        cursor.execute("UPDATE products SET price = 130.0, stocks = 90 WHERE name = 'Cumin Powder' AND price = 0.0")
        cursor.execute("UPDATE products SET price = 150.0, stocks = 75 WHERE name = 'Garam Masala' AND price = 0.0")
        cursor.execute("UPDATE products SET price = 145.0, stocks = 110 WHERE name = 'Red Chilli Powder' AND price = 0.0")
        cursor.execute("UPDATE products SET price = 115.0, stocks = 150 WHERE name = 'Turmeric Powder' AND price = 0.0")
        conn.commit()
        print("[OK] Migrated existing products default prices and stocks.")

    # Seed product images if product_images is empty
    cursor.execute("SELECT COUNT(*) FROM product_images")
    img_count = cursor.fetchone()[0]
    if img_count == 0:
        all_prods = cursor.execute("SELECT id, image_filename FROM products").fetchall()
        for p in all_prods:
            cursor.execute("INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (p['id'], p['image_filename']))
            # Add secondary image
            secondary_img = 'Turmeric-Powder.jpg' if p['image_filename'] != 'Turmeric-Powder.jpg' else 'Green-Tea.jpg'
            cursor.execute("INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (p['id'], secondary_img))
        conn.commit()
        print("[OK] Seeded default product images (multiple images per product).")
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

    # Seed carousel slides if empty
    cursor.execute("SELECT COUNT(*) FROM carousel_slides")
    slide_count = cursor.fetchone()[0]
    if slide_count == 0:
        slides_data = [
            (
                'hero_tea_garden.png',
                'leaf',
                'Direct from the Source',
                "Nature's Finest\nTea & Spices\nfor Every Kitchen",
                'Premium quality, authentically sourced teas and spices, delivered across India. From Assam\'s tea gardens to Kerala\'s spice farms — pure, natural, trusted.',
                'Explore Products',
                '/products',
                0
            ),
            (
                'Green-Tea.jpg',
                'star',
                'Premium Sourcing',
                "Assam tea gardens\nRich Aroma & Taste\nHandpicked with Care",
                'Experience the finest hand-selected tea leaves processed under strict quality standards. Delightful color, refreshing body, and premium taste in every cup.',
                'Explore Teas',
                '/products?category=Tea',
                1
            ),
            (
                'Garam-Masala.jpg',
                'sparkles',
                'Pure Spices',
                "Authentic Flavors\n100% Pure Spices\nSourced from Farmers",
                'Sun-dried, expertly ground spices with zero additives, fillers, or artificial colors. Enhancing Indian kitchens with rich heritage, aroma, and taste.',
                'Explore Spices',
                '/products?category=Spice',
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
            ('Tea', 'Premium Teas', 'Assam Black Tea, Green Tea, Herbal Infusions, and special blend leaves.', 'Tea.jpg', 0),
            ('Spice', 'Authentic Spices', 'Garam Masala, Turmeric, Red Chilli, Cardamom, Black Pepper, and more.', 'Garam-Masala.jpg', 1)
        ]
        cursor.executemany(
            "INSERT INTO categories (name, display_name, description, image_filename, display_order) VALUES (?, ?, ?, ?, ?)",
            categories_data
        )
        conn.commit()
        print("[OK] Seeded default categories.")

    conn.close()
    print("[OK] Database initialized successfully.")

if __name__ == '__main__':
    init_db()
