from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.database import get_db
from app.models.user import Role, Permission, User
from app.schemas.user import RoleResponse, RoleCreate, PermissionResponse
from app.api.deps import get_current_active_user

router = APIRouter()

class RolePermissionUpdate(BaseModel):
    name: str
    description: Optional[str] = None
    permission_ids: List[int] = []

@router.get("/", response_model=List[RoleResponse])
def read_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve roles available to current user.
    - Super Admin sees system level roles (business_id == None).
    - Business users see standard operational roles (Business Admin, Branch Manager, Cashier) and their own business custom roles.
    """
    if current_user.role and current_user.role.name == "Super Admin":
        return db.query(Role).filter(Role.business_id == None).all()
    
    business_id = current_user.business_id
    default_business_roles = ["Business Admin", "Branch Manager", "Cashier"]
    
    query = db.query(Role).filter(
        ((Role.name.in_(default_business_roles)) & (Role.business_id == None)) |
        (Role.business_id == business_id)
    )
    return query.all()

@router.get("/permissions", response_model=List[PermissionResponse])
def read_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve list of system permissions. Super Admin permissions are hidden from business users.
    """
    permissions = db.query(Permission).all()
    if not permissions:
        # Seed basic permissions if empty
        default_perms = [
            {"name": "Manage Businesses", "module": "SuperAdmin", "description": "Full access to business tenants"},
            {"name": "Manage Branches", "module": "Branches", "description": "Create and edit location branches"},
            {"name": "Manage Users", "module": "Users", "description": "Manage staff and user accounts"},
            {"name": "Manage Products", "module": "Products", "description": "Manage inventory stock and prices"},
            {"name": "Manage Sales & POS", "module": "Sales", "description": "Process orders and access POS terminal"},
            {"name": "Manage Purchases", "module": "Purchases", "description": "Supplier purchase entries"},
            {"name": "View Reports", "module": "Reports", "description": "View sales and profit reports"},
            {"name": "Manage Settings", "module": "Settings", "description": "Access system and payment settings"},
        ]
        for p in default_perms:
            db_perm = Permission(name=p["name"], module=p["module"], description=p["description"])
            db.add(db_perm)
        db.commit()
        permissions = db.query(Permission).all()

    if current_user.role and current_user.role.name != "Super Admin":
        permissions = [p for p in permissions if p.module != "SuperAdmin"]
        
    return permissions

@router.post("/", response_model=RoleResponse)
def create_role(
    role_in: RolePermissionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Create a custom role for current business.
    """
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    
    db_role = Role(
        name=role_in.name,
        description=role_in.description,
        business_id=business_id,
        is_system_role=False
    )
    
    if role_in.permission_ids:
        perms = db.query(Permission).filter(Permission.id.in_(role_in.permission_ids)).all()
        db_role.permissions = perms

    db.add(db_role)
    db.commit()
    db.refresh(db_role)
    return db_role

@router.put("/{role_id}", response_model=RoleResponse)
def update_role(
    role_id: int,
    role_in: RolePermissionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    query = db.query(Role).filter(Role.id == role_id)
    if current_user.role and current_user.role.name != "Super Admin":
        query = query.filter((Role.business_id == None) | (Role.business_id == current_user.business_id))
        
    role = query.first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
        
    role.name = role_in.name
    role.description = role_in.description
    
    if role_in.permission_ids is not None:
        perms = db.query(Permission).filter(Permission.id.in_(role_in.permission_ids)).all()
        role.permissions = perms
        
    db.commit()
    db.refresh(role)
    return role

@router.delete("/{role_id}")
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    query = db.query(Role).filter(Role.id == role_id)
    if current_user.role and current_user.role.name != "Super Admin":
        query = query.filter(Role.business_id == current_user.business_id)
        
    role = query.first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found or cannot be deleted")
        
    if role.is_system_role:
        raise HTTPException(status_code=400, detail="System default roles cannot be deleted")
        
    db.delete(role)
    db.commit()
    return {"message": "Role deleted successfully"}
