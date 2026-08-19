from sqlalchemy.orm import Session # pyrefly: ignore [missing-import]
from sqlalchemy import text # pyrefly: ignore [missing-import]
from app.models.user import Role, Permission, User # pyrefly: ignore [missing-import]
from app.models.business import Business # pyrefly: ignore [missing-import]
from app.models.branch import Branch # pyrefly: ignore [missing-import]
from app.models.product import Category, Brand, Product # pyrefly: ignore [missing-import]
from app.models.customer import Customer # pyrefly: ignore [missing-import]
from app.models.payment_method import PaymentMethod # pyrefly: ignore [missing-import]
from app.models.order import Order # pyrefly: ignore [missing-import]
from app.core.security import get_password_hash # pyrefly: ignore [missing-import]

def run_safe_alters(engine):
    alters = [
        "ALTER TABLE permissions ADD COLUMN module VARCHAR(50) NULL AFTER name",
        "ALTER TABLE roles ADD COLUMN business_id INT NULL AFTER id",
        "ALTER TABLE roles ADD COLUMN is_system_role BOOLEAN DEFAULT FALSE AFTER description",
        "ALTER TABLE users ADD COLUMN business_id INT NULL AFTER id",
        "ALTER TABLE users ADD COLUMN branch_id INT NULL AFTER business_id",
        "ALTER TABLE categories ADD COLUMN business_id INT NULL AFTER id",
        "ALTER TABLE brands ADD COLUMN business_id INT NULL AFTER id",
        "ALTER TABLE products ADD COLUMN business_id INT NULL AFTER id",
        "ALTER TABLE customers ADD COLUMN business_id INT NULL AFTER id",
        "ALTER TABLE payment_methods ADD COLUMN business_id INT NULL AFTER id",
        "ALTER TABLE orders ADD COLUMN business_id INT NULL AFTER id",
        "ALTER TABLE orders ADD COLUMN branch_id INT NULL AFTER business_id"
    ]
    with engine.connect() as conn:
        for stmt in alters:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass

def init_db(db: Session):
    # 1. Seed Default Permissions
    permissions_data = [
        {"name": "manage_products", "module": "Inventory", "description": "Can add, edit, or delete products"},
        {"name": "manage_stock", "module": "Inventory", "description": "Can update stock quantities"},
        {"name": "manage_users", "module": "Users", "description": "Can manage staff users"},
        {"name": "process_sales", "module": "Sales", "description": "Can create orders and process POS sales"},
        {"name": "void_sales", "module": "Sales", "description": "Can return, refund or void an invoice"},
        {"name": "view_reports", "module": "Reports", "description": "Can see profit/loss and sales reports"},
        {"name": "manage_branches", "module": "Settings", "description": "Can manage business locations and branches"},
        {"name": "manage_business_roles", "module": "Settings", "description": "Can create and assign custom roles and permissions"}
    ]

    for p_data in permissions_data:
        perm = db.query(Permission).filter(Permission.name == p_data["name"]).first()
        if not perm:
            db.add(Permission(**p_data))
    db.commit()

    all_perms = db.query(Permission).all()

    # 2. Seed Default System Roles
    system_roles = [
        {"name": "Super Admin", "description": "Global System Administrator", "is_system_role": True},
        {"name": "Business Admin", "description": "Business Owner - Full business and branch control", "is_system_role": True},
        {"name": "Branch Manager", "description": "Branch Manager - Manages sales, stock, and staff for a branch", "is_system_role": True},
        {"name": "Cashier", "description": "POS Cashier - Can process sales and collect payments", "is_system_role": True}
    ]

    for r_data in system_roles:
        role = db.query(Role).filter(Role.name == r_data["name"]).first()
        if not role:
            role = Role(name=r_data["name"], description=r_data["description"], is_system_role=r_data["is_system_role"])
            if r_data["name"] in ["Super Admin", "Business Admin"]:
                role.permissions = all_perms
            elif r_data["name"] == "Branch Manager":
                role.permissions = [p for p in all_perms if p.name not in ["manage_branches", "manage_business_roles"]]
            elif r_data["name"] == "Cashier":
                role.permissions = [p for p in all_perms if p.name in ["process_sales", "void_sales"]]
            db.add(role)
    db.commit()

    # 3. Seed Default Demo Business
    default_business = db.query(Business).filter(Business.name == "Shahenshah Main Store").first()
    if not default_business:
        default_business = Business(
            name="Shahenshah Main Store",
            slug="shahenshah-main-store",
            phone="+923001234567",
            email="admin@shahenshah.com",
            address="Main Market, Gulberg III, Lahore",
            currency="PKR",
            status="Active"
        )
        db.add(default_business)
        db.commit()
        db.refresh(default_business)

    # 4. Seed Default Main Branch
    default_branch = db.query(Branch).filter(Branch.business_id == default_business.id, Branch.is_main_branch == True).first()
    if not default_branch:
        default_branch = Branch(
            business_id=default_business.id,
            name="Main Branch - Lahore",
            code="LHR-01",
            address="Main Market, Gulberg III, Lahore",
            phone="+923001234567",
            is_main_branch=True,
            is_active=True
        )
        db.add(default_branch)
        db.commit()
        db.refresh(default_branch)

    # 5. Seed Super Admin User & Business Admin User
    super_admin_role = db.query(Role).filter(Role.name == "Super Admin").first()
    business_admin_role = db.query(Role).filter(Role.name == "Business Admin").first()

    super_admin = db.query(User).filter(User.email == "admin@gmail.com").first()
    if not super_admin and super_admin_role:
        super_admin = User(
            name="Super Admin",
            email="admin@gmail.com",
            password=get_password_hash("admin123"),
            is_active=True,
            role_id=super_admin_role.id,
            business_id=None,
            branch_id=None
        )
        db.add(super_admin)

    business_admin = db.query(User).filter(User.email == "owner@shahenshah.com").first()
    if not business_admin and business_admin_role:
        business_admin = User(
            name="Shahenshah Owner",
            email="owner@shahenshah.com",
            password=get_password_hash("admin123"),
            is_active=True,
            role_id=business_admin_role.id,
            business_id=default_business.id,
            branch_id=default_branch.id
        )
        db.add(business_admin)

    db.commit()

    # 6. Backfill existing records with default_business.id & default_branch.id if business_id is NULL
    db.query(Category).filter(Category.business_id.is_(None)).update({Category.business_id: default_business.id}, synchronize_session=False)
    db.query(Brand).filter(Brand.business_id.is_(None)).update({Brand.business_id: default_business.id}, synchronize_session=False)
    db.query(Product).filter(Product.business_id.is_(None)).update({Product.business_id: default_business.id}, synchronize_session=False)
    db.query(Customer).filter(Customer.business_id.is_(None)).update({Customer.business_id: default_business.id}, synchronize_session=False)
    db.query(PaymentMethod).filter(PaymentMethod.business_id.is_(None)).update({PaymentMethod.business_id: default_business.id}, synchronize_session=False)
    db.query(Order).filter(Order.business_id.is_(None)).update({Order.business_id: default_business.id, Order.branch_id: default_branch.id}, synchronize_session=False)
    db.query(User).filter(User.email != "admin@gmail.com", User.business_id.is_(None)).update({User.business_id: default_business.id, User.branch_id: default_branch.id}, synchronize_session=False)
    
    db.commit()
    print("Database seeded and migrated successfully for Multi-Tenancy & Multi-Branch Architecture!")

if __name__ == "__main__":
    from app.db.database import SessionLocal, engine
    from app.db.base import Base
    from app.models.business import Business
    from app.models.branch import Branch, BranchVariantStock
    from app.models.product import Category, Brand, Product, ProductVariant
    from app.models.user import User, Role, Permission
    from app.models.order import Order, OrderItem, OrderPayment
    from app.models.customer import Customer
    from app.models.payment_method import PaymentMethod
    
    Base.metadata.create_all(bind=engine)
    run_safe_alters(engine)
    db = SessionLocal()
    init_db(db)
    db.close()
