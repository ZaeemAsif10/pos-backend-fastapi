from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.branch import Branch
from app.schemas.branch import BranchCreate, BranchUpdate

def get_branch(db: Session, branch_id: int):
    return db.query(Branch).filter(Branch.id == branch_id).first()

def get_branches_by_business(db: Session, business_id: int, skip: int = 0, limit: int = 100):
    return db.query(Branch).filter(Branch.business_id == business_id).order_by(Branch.created_at.desc()).offset(skip).limit(limit).all()

def create_branch(db: Session, branch_in: BranchCreate, business_id: int):
    db_branch = Branch(
        business_id=business_id,
        name=branch_in.name,
        code=branch_in.code,
        address=branch_in.address,
        phone=branch_in.phone,
        is_main_branch=branch_in.is_main_branch or False,
        is_active=branch_in.is_active if branch_in.is_active is not None else True
    )
    db.add(db_branch)
    db.commit()
    db.refresh(db_branch)
    return db_branch

def update_branch(db: Session, branch_id: int, branch_in: BranchUpdate):
    db_branch = get_branch(db, branch_id)
    if not db_branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    update_data = branch_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_branch, field, value)

    db.commit()
    db.refresh(db_branch)
    return db_branch
