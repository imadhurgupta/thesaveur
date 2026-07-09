import sqlite3
import hashlib
import os
import random
import string

# In Docker, DATA_DIR=/app/data (a persistent volume). Locally it uses the project folder.
_data_dir = os.environ.get('DATA_DIR', os.path.dirname(__file__))
os.makedirs(_data_dir, exist_ok=True)
DB_PATH = os.path.join(_data_dir, 'thesaveur.db')


def generate_user_id():
    chars = string.ascii_uppercase + string.digits
    return "USR-" + "".join(random.choice(chars) for _ in range(8))


def generate_product_id():
    chars = string.ascii_uppercase + string.digits
    return "PROD-" + "".join(random.choice(chars) for _ in range(8))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
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

    # ---- SQLite-only legacy migrations ----
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
    PK = "INTEGER PRIMARY KEY AUTOINCREMENT"
    REAL = "REAL"

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
            paypal_order_id TEXT,
            paypal_payment_id TEXT,
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
        "ALTER TABLE orders ADD COLUMN paypal_order_id TEXT",
        "ALTER TABLE orders ADD COLUMN paypal_payment_id TEXT",
        "ALTER TABLE orders ADD COLUMN shipping_charge REAL DEFAULT 0.0",
        "ALTER TABLE order_items ADD COLUMN original_price REAL DEFAULT 0",
        "ALTER TABLE order_items ADD COLUMN discount_percent REAL DEFAULT 0",
    ]
    for stmt in alter_stmts:
        _safe_alter(cursor, conn, stmt)

    # ---- SEED: products ----
    products = [
        ('PROD-TEA-ASSAM', 'Assam Black Tea', 'Tea', 'Black Tea',
         'Rich, full-bodied Assam black tea with a bold malty flavor. Sourced directly from single-estate tea gardens.',
         'Tea.jpg', 180.0, 50, 1, '250g'),
        ('PROD-TEA-GREEN', 'Organic Green Tea', 'Tea', 'Green Tea',
         'Fresh, anti-oxidant rich green tea leaves with a clean, delicate finish.',
         'Green-Tea.jpg', 220.0, 40, 0, '200g'),
        ('PROD-SPICE-GARAM', 'Garam Masala', 'Spices', 'Blend Spices',
         'A highly aromatic blend of premium roasted spices including cardamom, cinnamon, cloves, and nutmeg.',
         'Garam-Masala.jpg', 150.0, 80, 1, '100g'),
        ('PROD-SPICE-TURMERIC', 'Pure Turmeric Powder', 'Spices', 'Ground Spices',
         'High-curcumin golden turmeric powder ground from sun-dried roots.',
         'Turmeric-Powder.jpg', 110.0, 120, 0, '200g'),
        ('PROD-SPICE-PEPPER', 'Black Pepper Powder', 'Spices', 'Ground Spices',
         'Bold, pungent ground black pepper sourced from Malabar.',
         'Black-Papper.jpg', 130.0, 60, 0, '100g'),
        ('PROD-SPICE-CHILLI', 'Red Chilli Powder', 'Spices', 'Ground Spices',
         'Vibrant, medium-hot ground red chillies for rich color and heat.',
         'Red-Chilli-Powder.jpg', 120.0, 90, 1, '150g'),
        ('PROD-SPICE-AAMCHUR', 'Aamchur Powder', 'Spices', 'Ground Spices',
         'Tangy dry mango powder perfect for adding a sour punch to dishes.',
         'Aamchur-Powder.jpg', 95.0, 70, 0, '100g'),
        ('PROD-CLOTH-TSHIRT', 'Premium Cotton T-Shirt', 'Cloths', 'Apparel',
         'Classic fit crew neck t-shirt made of 100% organic cotton. Super soft and breathable.',
         'fashion.png', 599.0, 150, 1, '1 Unit'),
        ('PROD-CLOTH-TOTE', 'Canvas Tote Bag', 'Cloths', 'Accessories',
         'Heavy-duty cotton canvas tote bag with reinforced handles for everyday utility.',
         'fashion.png', 349.0, 110, 0, '1 Unit'),
    ]
    seeded_count = 0
    for p in products:
        cursor.execute("SELECT 1 FROM products WHERE id = ?", (p[0],))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO products (id, name, category, sub_category, description, image_filename, price, stocks, is_bestseller, unit) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                p
            )
            seeded_count += 1
    if seeded_count > 0:
        conn.commit()
        print(f"[OK] Seeded {seeded_count} products.")

    # ---- SEED: product_images ----
    all_prods = cursor.execute("SELECT id, image_filename FROM products").fetchall()
    images_seeded = False
    for p in all_prods:
        pid = _pid(p)
        try:
            img = p['image_filename']
        except (KeyError, TypeError):
            img = p[1]
        
        cursor.execute("SELECT 1 FROM product_images WHERE product_id = ?", (pid,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (pid, img)
            )
            cursor.execute(
                "INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (pid, img)
            )
            images_seeded = True
    if images_seeded:
        conn.commit()
        print("[OK] Seeded default product images.")

    # ---- SEED: admin user ----
    cursor.execute("SELECT 1 FROM users WHERE id = ?", ('USR-ADMIN',))
    if not cursor.fetchone():
        admin_pass_hash = hashlib.sha256('admin123'.encode('utf-8')).hexdigest()
        cursor.execute(
            "INSERT INTO users (id, full_name, email, password_hash, is_admin) VALUES (?, ?, ?, ?, 1)",
            ('USR-ADMIN', 'System Admin', 'admin@thesaveur.com', admin_pass_hash)
        )
        conn.commit()
        print("[OK] Seeded default admin account (admin@thesaveur.com / admin123).")

    # ---- SEED: carousel slides ----
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
    slides_seeded = False
    for slide in slides_data:
        cursor.execute("SELECT 1 FROM carousel_slides WHERE title = ?", (slide[3],))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO carousel_slides (image_filename, badge_icon, badge_text, title, description, button_text, button_link, slide_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                slide
            )
            slides_seeded = True
    if slides_seeded:
        conn.commit()
        print("[OK] Seeded default carousel slides.")

    # ---- SEED: categories ----
    categories_data = [
        ('Tea', 'Premium Tea', 'Finest handpicked teas from single-estate gardens.', 'Tea.jpg', 0),
        ('Spices', 'Authentic Spices', 'Pure, aromatic ground and whole spices.', 'Garam-Masala.jpg', 1),
        ('Cloths', 'Apparel & Cloths', 'Premium wear made from organic cotton.', 'fashion.png', 2),
    ]
    categories_seeded = False
    for cat in categories_data:
        cursor.execute("SELECT 1 FROM categories WHERE name = ?", (cat[0],))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO categories (name, display_name, description, image_filename, display_order) VALUES (?, ?, ?, ?, ?)",
                cat
            )
            categories_seeded = True
    if categories_seeded:
        conn.commit()
        print("[OK] Seeded default categories.")

    # ---- SEED: subcategories ----
    subcategories_data = [
        ('Tea', 'Green Tea', 'Green Tea', 'Fresh, organic green tea leaves.', 0),
        ('Tea', 'Black Tea', 'Black Tea', 'Bold, premium estate black teas.', 1),
        ('Spices', 'Blend Spices', 'Blend Spices', 'Perfect mixes of ground spices.', 0),
        ('Spices', 'Ground Spices', 'Ground Spices', 'Single-ingredient ground spices.', 1),
        ('Cloths', 'Apparel', 'Apparel', 'Premium organic cotton clothing.', 0),
        ('Cloths', 'Accessories', 'Accessories', 'Sustainably sourced cloth accessories.', 1),
    ]
    subcategories_seeded = False
    for subcat in subcategories_data:
        cursor.execute("SELECT 1 FROM subcategories WHERE category_name = ? AND name = ?", (subcat[0], subcat[1]))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO subcategories (category_name, name, display_name, description, display_order) VALUES (?, ?, ?, ?, ?)",
                subcat
            )
            subcategories_seeded = True
    if subcategories_seeded:
        conn.commit()
        print("[OK] Seeded default subcategories.")

    # ---- SEED: reviews (using real TEXT product IDs) ----
    reviews_data = [
        ('PROD-TEA-ASSAM', 'Aarav Sharma', 5,
         'Absolutely loved the malty flavor of this Assam tea. Tastes exactly like traditional estate tea! Perfect morning brew.'),
        ('PROD-TEA-ASSAM', 'Priya Patel', 4,
         'Great quality whole leaves. Very aromatic and soothing. Highly recommended for tea lovers.'),
        ('PROD-SPICE-GARAM', 'Rohan Das', 5,
         'Extremely fresh and strong aroma. This Garam Masala is a game changer for my cooking!'),
        ('PROD-SPICE-GARAM', 'Anjali Gupta', 5,
         'The perfect spice blend for my curries. Premium warmth and richness. Will definitely buy again.'),
        ('PROD-SPICE-TURMERIC', 'Vikram Malhotra', 4,
         'Very vibrant yellow color. High curcumin content and extremely pure.'),
        ('PROD-SPICE-TURMERIC', 'Meera Sen', 5,
         'Excellent purity. Tastes authentic and earthy. Perfect for cooking and making golden milk!'),
        ('PROD-SPICE-CHILLI', 'Suresh Kumar', 5,
         'Very hot and vibrant red color. Excellent quality chilli powder.'),
    ]
    reviews_seeded = False
    for rev in reviews_data:
        cursor.execute("SELECT 1 FROM reviews WHERE product_id = ? AND user_name = ?", (rev[0], rev[1]))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO reviews (product_id, user_name, rating, comment) VALUES (?, ?, ?, ?)",
                rev
            )
            reviews_seeded = True
    if reviews_seeded:
        conn.commit()
        print("[OK] Seeded default reviews.")

    # ---- SEED: location shipping ----
    loc_charges = [
        ('Delhi', 40.0), ('New Delhi', 40.0), ('Maharashtra', 80.0),
        ('Karnataka', 90.0), ('Assam', 100.0), ('West Bengal', 70.0),
        ('Tamil Nadu', 90.0), ('Haryana', 50.0), ('Uttar Pradesh', 50.0),
        ('Default', 60.0),
    ]
    loc_seeded = False
    for loc in loc_charges:
        cursor.execute("SELECT 1 FROM location_shipping_charges WHERE state = ?", (loc[0],))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO location_shipping_charges (state, charge) VALUES (?, ?)",
                loc
            )
            loc_seeded = True
    if loc_seeded:
        conn.commit()
        print(f"[OK] Seeded default location shipping rates.")

    # ---- DYNAMIC REPAIR: Resolve category name changes in subcategories and products ----
    try:
        # Get all category technical names (slugs)
        cursor.execute("SELECT name FROM categories")
        valid_cats = {row[0] for row in cursor.fetchall()}

        # Find orphaned subcategories
        cursor.execute("SELECT DISTINCT category_name FROM subcategories")
        subcat_parents = [row[0] for row in cursor.fetchall()]
        
        for parent in subcat_parents:
            if parent not in valid_cats:
                # Try to map close names, e.g. "Dry Fruits & Nuts" to "Nut & Dry Fruits"
                # If "Nut & Dry Fruits" or "Dry Fruits" exists as a category, migrate the parent
                for candidate in ["Nut & Dry Fruits", "Dry Fruits", "Dry Fruits & Nuts"]:
                    if candidate in valid_cats:
                        print(f"[REPAIR] Migrating subcategory parent '{parent}' to '{candidate}'")
                        cursor.execute("UPDATE subcategories SET category_name = ? WHERE category_name = ?", (candidate, parent))
                        cursor.execute("UPDATE products SET category = ? WHERE category = ?", (candidate, parent))
                        conn.commit()
                        break
    except Exception as repair_err:
        print(f"[WARNING] Database repair runner encountered an error: {repair_err}")

    conn.close()
    print("[OK] Database initialized successfully.")


if __name__ == '__main__':
    init_db()
