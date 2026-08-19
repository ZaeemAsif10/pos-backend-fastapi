from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.business import Business
from app.models.branch import Branch
from app.models.user import User, Role
from app.schemas.business import BusinessCreate, BusinessUpdate
from app.core.security import get_password_hash

def get_business(db: Session, business_id: int):
    return db.query(Business).filter(Business.id == business_id).first()

def get_businesses(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Business).order_by(Business.created_at.desc()).offset(skip).limit(limit).all()

def create_business(db: Session, business_in: BusinessCreate):
    # 1. Check if email already used for admin user
    existing_user = db.query(User).filter(User.email == business_in.admin_email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Admin email is already registered")

    # 2. Create Business record
    db_business = Business(
        name=business_in.name,
        slug=business_in.slug or business_in.name.lower().replace(" ", "-"),
        phone=business_in.phone,
        email=business_in.email or business_in.admin_email,
        address=business_in.address,
        logo_url=business_in.logo_url,
        currency=business_in.currency or "PKR",
        status=business_in.status or "Active"
    )
    db.add(db_business)
    db.flush()

    # 3. Create Default Main Branch
    main_branch = Branch(
        business_id=db_business.id,
        name="Main Branch",
        code="BR-01",
        address=business_in.address,
        phone=business_in.phone,
        is_main_branch=True,
        is_active=True
    )
    db.add(main_branch)
    db.flush()

    # 4. Get Business Admin Role
    admin_role = db.query(Role).filter(Role.name == "Business Admin").first()
    if not admin_role:
        admin_role = db.query(Role).filter(Role.name == "Super Admin").first()

    # 5. Create Business Admin User
    admin_user = User(
        name=business_in.admin_name or "Business Admin",
        email=business_in.admin_email,
        password=get_password_hash(business_in.admin_password),
        is_active=True,
        role_id=admin_role.id if admin_role else 1,
        business_id=db_business.id,
        branch_id=main_branch.id
    )
    db.add(admin_user)
    db.commit()
    db.refresh(db_business)
    return db_business

def update_business(db: Session, business_id: int, business_in: BusinessUpdate):
    db_business = get_business(db, business_id)
    if not db_business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    update_data = business_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_business, field, value)
        
    db.commit()
    db.refresh(db_business)
    return db_business
