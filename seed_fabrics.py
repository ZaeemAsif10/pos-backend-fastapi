import os
from sqlalchemy import text
from app.db.database import SessionLocal, engine
from app.db.base import Base
from app.models.product import Category, Brand, Product, ProductVariant
from app.models.user import User, Role, Permission
from app.models.order import Order, OrderItem
from app.models.customer import Customer
from app.models.payment_method import PaymentMethod
from app.core.security import get_password_hash

def seed_database():
    print("Re-creating database tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()

    # 1. Permissions & Roles
    permissions_data = [
        {"name": "manage_products", "description": "Can add, edit, or delete products"},
        {"name": "manage_stock", "description": "Can update stock quantities"},
        {"name": "manage_users", "description": "Can add or remove cashiers/staff"},
        {"name": "process_sales", "description": "Can create orders and process checkouts"},
        {"name": "void_sales", "description": "Can return, refund or void an invoice"},
        {"name": "view_reports", "description": "Can see profit/loss and sales reports"}
    ]
    for p in permissions_data:
        db.add(Permission(**p))
    db.commit()

    all_perms = db.query(Permission).all()
    sales_perm = next(p for p in all_perms if p.name == "process_sales")

    super_admin_role = Role(name="Super Admin", description="Owner - Has access to everything", permissions=all_perms)
    manager_role = Role(name="Manager", description="Manager", permissions=[p for p in all_perms if p.name not in ["manage_users"]])
    cashier_role = Role(name="Cashier", description="Cashier", permissions=[sales_perm])
    
    db.add_all([super_admin_role, manager_role, cashier_role])
    db.commit()

    # 2. Admin User & Customer
    admin_user = User(
        name="Super Admin",
        email="admin@gmail.com",
        password=get_password_hash("admin123"),
        is_active=True,
        role_id=super_admin_role.id
    )
    walk_in_customer = Customer(
        name="Walk-in Customer",
        phone="N/A-WALKIN",
        email="walkin@pos.com",
        address="Counter Sale"
    )
    db.add_all([admin_user, walk_in_customer])
    db.commit()

    # Seed Payment Methods
    pm_data = [
        {"name": "Cash", "description": "Cash payment at counter"},
        {"name": "Card", "description": "Debit or Credit Card POS machine"},
        {"name": "Bank Transfer", "description": "Direct bank account transfer"},
        {"name": "EasyPaisa", "description": "EasyPaisa mobile wallet"},
        {"name": "JazzCash", "description": "JazzCash mobile wallet"},
        {"name": "Cheque", "description": "Bank Cheque payment"}
    ]
    for pm in pm_data:
        db.add(PaymentMethod(**pm))
    db.commit()

    # 3. Fabric Categories
    categories_data = [
        {"name": "Wash & Wear", "description": "Wrinkle-resistant luxury wash & wear fabrics for men"},
        {"name": "Cotton Fabric", "description": "100% Pure Egyptian & Soft Cotton unstitched suits"},
        {"name": "Lawn & Linen", "description": "Lightweight summer lawn and cozy winter linen"},
        {"name": "Karandi & Khaddar", "description": "Traditional hand-woven winter karandi and khaddar"},
        {"name": "Silk & Velvet", "description": "Premium raw silk, shamoz silk and micro velvet"},
        {"name": "Woolen & Boski", "description": "Classic Chinese Boski and pure Australian woolen fabric"}
    ]

    cat_objs = {}
    for c_data in categories_data:
        c = Category(**c_data)
        db.add(c)
        db.commit()
        db.refresh(c)
        cat_objs[c.name] = c

    # 4. Fabric Brands
    brands_data = [
        {"name": "Grace Fabrics", "description": "Premium unstitched & wash and wear men's collection"},
        {"name": "Pasha Fabrics", "description": "Luxury Egyptian cottons and latha fabrics"},
        {"name": "Junaid Jamshed", "description": "Classic Pakistani ethnic fabric and unstitched suits"},
        {"name": "Gul Ahmed", "description": "Signature lawn, cotton, and winter fabrics"},
        {"name": "Alkaram", "description": "Quality cotton, lawn and velvet suits"},
        {"name": "Sapphire", "description": "Organic mercerized cotton and summer lawns"},
        {"name": "Khaadi", "description": "Authentic handloom khaddar and printed summer lawn"},
        {"name": "Bareeze", "description": "Embroidered Swiss lawn, karandi and raw silks"},
        {"name": "Sana Safinaz", "description": "Luxury unstitched lawn and formal collections"},
        {"name": "Nishat Linen", "description": "High-end linen and textured winter suits"},
        {"name": "Bonanza Satrangi", "description": "Wool khaddar and seasonal unstitched suits"},
        {"name": "Asim Jofa", "description": "Micro 9000 velvet and luxury embroidered suits"},
        {"name": "China Boski", "description": "Original Chinese Boski silk for gents"}
    ]

    brand_objs = {}
    for b_data in brands_data:
        b = Brand(**b_data)
        db.add(b)
        db.commit()
        db.refresh(b)
        brand_objs[b.name] = b

    # Fabric Image Collection (Unsplash High Quality Fabrics)
    fabric_images = [
        "https://images.unsplash.com/photo-1584100936595-c0654b55a2e2?w=500&auto=format&fit=crop&q=60",
        "https://images.unsplash.com/photo-1604719312566-8912e9227c6a?w=500&auto=format&fit=crop&q=60",
        "https://images.unsplash.com/photo-1528459801416-a9e53bbf4e17?w=500&auto=format&fit=crop&q=60",
        "https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?w=500&auto=format&fit=crop&q=60",
        "https://images.unsplash.com/photo-1579684385127-1ef15d508118?w=500&auto=format&fit=crop&q=60",
        "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=500&auto=format&fit=crop&q=60",
        "https://images.unsplash.com/photo-1534452203293-494d7ddbf7e0?w=500&auto=format&fit=crop&q=60",
        "https://images.unsplash.com/photo-1489987707025-afc232f7ea0f?w=500&auto=format&fit=crop&q=60"
    ]

    # 5. 30 Fabric Products with Category and Brand IDs
    products_list = [
        # Wash & Wear
        ("Grace Executive Wash & Wear Unstitched", "Wash & Wear", 4500.0, 3200.0, "Grace Fabrics", fabric_images[0]),
        ("Pasha Latha Wash & Wear Premium", "Wash & Wear", 5800.0, 4100.0, "Pasha Fabrics", fabric_images[1]),
        ("J. Soft Blend Wash & Wear 4.5m", "Wash & Wear", 3950.0, 2800.0, "Junaid Jamshed", fabric_images[2]),
        ("Gul Ahmed All-Season Wash & Wear", "Wash & Wear", 4200.0, 3000.0, "Gul Ahmed", fabric_images[3]),
        ("Alkaram Wrinkle-Free Wash & Wear", "Wash & Wear", 3700.0, 2600.0, "Alkaram", fabric_images[4]),

        # Cotton Fabric
        ("Royal Egyptian Supima Cotton 4.5m", "Cotton Fabric", 6500.0, 4800.0, "Pasha Fabrics", fabric_images[5]),
        ("J. Imperial Soft Cotton Suit", "Cotton Fabric", 5200.0, 3700.0, "Junaid Jamshed", fabric_images[6]),
        ("Gul Ahmed Chairman Latha Cotton", "Cotton Fabric", 5900.0, 4300.0, "Gul Ahmed", fabric_images[7]),
        ("Grace Sovereign Cotton Unstitched", "Cotton Fabric", 4800.0, 3400.0, "Grace Fabrics", fabric_images[0]),
        ("Sapphire Organic Mercerized Cotton", "Cotton Fabric", 4600.0, 3300.0, "Sapphire", fabric_images[1]),

        # Lawn & Linen
        ("Khaadi Printed Summer Lawn 3-Piece", "Lawn & Linen", 3850.0, 2500.0, "Khaadi", fabric_images[2]),
        ("Gul Ahmed Premium Digital Lawn Suit", "Lawn & Linen", 4950.0, 3400.0, "Gul Ahmed", fabric_images[3]),
        ("Bareeze Embroidered Swiss Lawn 3-Piece", "Lawn & Linen", 8900.0, 6200.0, "Bareeze", fabric_images[4]),
        ("Sana Safinaz Luxury Lawn Collection", "Lawn & Linen", 7500.0, 5200.0, "Sana Safinaz", fabric_images[5]),
        ("Nishat Linen Winter Twill Suit", "Lawn & Linen", 3400.0, 2300.0, "Nishat Linen", fabric_images[6]),

        # Karandi & Khaddar
        ("Khaadi Handloom Khaddar Unstitched", "Karandi & Khaddar", 3200.0, 2100.0, "Khaadi", fabric_images[7]),
        ("Bareeze Karandi Embroidered Suit", "Karandi & Khaddar", 9500.0, 6800.0, "Bareeze", fabric_images[0]),
        ("J. Heavy Texture Winter Khaddar", "Karandi & Khaddar", 4100.0, 2900.0, "Junaid Jamshed", fabric_images[1]),
        ("Nishat Textured Karandi 3-Piece", "Karandi & Khaddar", 4400.0, 3100.0, "Nishat Linen", fabric_images[2]),
        ("Bonanza Satrangi Wool Khaddar", "Karandi & Khaddar", 3600.0, 2500.0, "Bonanza Satrangi", fabric_images[3]),

        # Silk & Velvet
        ("Pure China Shamoz Silk Unstitched", "Silk & Velvet", 7800.0, 5500.0, "Bareeze", fabric_images[4]),
        ("Micro 9000 Velvet Unstitched Suit", "Silk & Velvet", 11500.0, 8200.0, "Asim Jofa", fabric_images[5]),
        ("Raw Silk Embroidered Formal Fabric", "Silk & Velvet", 9200.0, 6400.0, "Sana Safinaz", fabric_images[6]),
        ("J. Festive Pure Silk Collection", "Silk & Velvet", 8500.0, 6000.0, "Junaid Jamshed", fabric_images[7]),
        ("Alkaram Velvet Embroidered Suit", "Silk & Velvet", 10500.0, 7500.0, "Alkaram", fabric_images[0]),

        # Woolen & Boski
        ("Original China Boski 8 Pound (7 Yards)", "Woolen & Boski", 12500.0, 9500.0, "China Boski", fabric_images[1]),
        ("Pure Australian Wool Suit Fabric", "Woolen & Boski", 14000.0, 10200.0, "Pasha Fabrics", fabric_images[2]),
        ("J. Traditional Boski 6 Pound", "Woolen & Boski", 9800.0, 7200.0, "Junaid Jamshed", fabric_images[3]),
        ("Grace Tropical Woolen Blend Suit", "Woolen & Boski", 6800.0, 4900.0, "Grace Fabrics", fabric_images[4]),
        ("Gul Ahmed Signature Boski Suit", "Woolen & Boski", 11000.0, 8100.0, "Gul Ahmed", fabric_images[5]),
    ]

    sku_count = 101
    for name, cat_name, b_price, c_price, brand_name, img in products_list:
        p = Product(
            category_id=cat_objs[cat_name].id,
            brand_id=brand_objs[brand_name].id,
            name=name,
            description=f"Premium quality {name} fabric. Authentic unstitched suit by {brand_name}.",
            image_url=img,
            base_price=b_price,
            cost_price=c_price
        )
        db.add(p)
        db.commit()
        db.refresh(p)

        # Add Product Variant with stock = 50
        variant = ProductVariant(
            product_id=p.id,
            size="Unstitched 4.5m",
            color="Standard Color",
            sku=f"FAB-{sku_count}",
            barcode=f"89012345{sku_count}",
            stock_quantity=50,
            price_adjustment=0.0
        )
        db.add(variant)
        db.commit()
        sku_count += 1

    print(f"Successfully seeded {len(products_list)} Fabric products with brand_id & category_id right after id!")

    # 6. Sample Orders with Paid, Partial, and Due statuses
    cash_pm = db.query(PaymentMethod).filter(PaymentMethod.name == "Cash").first()
    card_pm = db.query(PaymentMethod).filter(PaymentMethod.name == "Card").first()
    easypaisa_pm = db.query(PaymentMethod).filter(PaymentMethod.name == "EasyPaisa").first()

    o1 = Order(
        user_id=admin_user.id,
        customer_id=walk_in_customer.id,
        payment_method_id=easypaisa_pm.id if easypaisa_pm else 1,
        total_amount=11600.0,
        discount=0.0,
        tax=0.0,
        final_amount=11600.0,
        paid_amount=11600.0,
        due_amount=0.0,
        status="Paid"
    )
    o2 = Order(
        user_id=admin_user.id,
        customer_id=walk_in_customer.id,
        payment_method_id=cash_pm.id if cash_pm else 1,
        total_amount=5200.0,
        discount=0.0,
        tax=0.0,
        final_amount=5200.0,
        paid_amount=2600.0,
        due_amount=2600.0,
        status="Partial"
    )
    o3 = Order(
        user_id=admin_user.id,
        customer_id=walk_in_customer.id,
        payment_method_id=card_pm.id if card_pm else 1,
        total_amount=4500.0,
        discount=0.0,
        tax=0.0,
        final_amount=4500.0,
        paid_amount=0.0,
        due_amount=4500.0,
        status="Due"
    )
    db.add_all([o1, o2, o3])
    db.commit()
    print("Seeded sample orders with Paid, Partial, and Due payment statuses.")

    db.close()

if __name__ == "__main__":
    seed_database()
