from typing import Optional
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Table, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.base import Base

# Association table for Many-to-Many relationship between Role and Permission
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id"), primary_key=True),
)

class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True, nullable=False)
    module = Column(String(50), nullable=True) # e.g. 'Sales', 'Inventory', 'Reports', 'Settings'
    description = Column(String(255))
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True) # NULL for system roles, ID for custom business roles
    name = Column(String(50), index=True, nullable=False)
    description = Column(String(255))
    is_system_role = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    permissions = relationship("Permission", secondary=role_permissions)
    users = relationship("User", back_populates="role")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True) # NULL for Super Admin
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True) # NULL for Business Admin
    name = Column(String(100), index=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    role_id = Column(Integer, ForeignKey("roles.id"))
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    role = relationship("Role", back_populates="users")
    business = relationship("Business")
    branch = relationship("Branch")

    @property
    def business_name(self) -> Optional[str]:
        return self.business.name if self.business else None

    @property
    def branch_name(self) -> Optional[str]:
        return self.branch.name if self.branch else None

