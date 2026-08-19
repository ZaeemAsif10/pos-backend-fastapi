from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.branch import BranchCreate, BranchResponse, BranchUpdate
from app.crud import crud_branch
from app.api.deps import get_current_active_user
from app.models.user import User
from app.models.branch import Branch

router = APIRouter()

@router.get("/", response_model=List[BranchResponse])
def read_branches(
    business_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve branches/locations for current user's business.
    """
    if current_user.role and current_user.role.name == "Super Admin":
        if business_id is not None:
            return crud_branch.get_branches_by_business(db, business_id=business_id)
        return db.query(Branch).filter(Branch.business_id == None).order_by(Branch.created_at.desc()).all()
    
    target_business_id = current_user.business_id or 1
    return crud_branch.get_branches_by_business(db, business_id=target_business_id)

@router.post("/", response_model=BranchResponse)
def create_branch(
    branch_in: BranchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Create a new branch/location under the current user's business.
    """
    business_id = current_user.business_id or branch_in.business_id or 1
    return crud_branch.create_branch(db=db, branch_in=branch_in, business_id=business_id)

@router.put("/{branch_id}", response_model=BranchResponse)
def update_branch(
    branch_id: int,
    branch_in: BranchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    return crud_branch.update_branch(db=db, branch_id=branch_id, branch_in=branch_in)
