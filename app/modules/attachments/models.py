from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import BigInteger, String, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base


class Attachment(Base):
    """Polymorphic attachment model for files and images across any entity in Paperless.
    
    Supports morph relation via attachable_type (e.g. 'Product', 'Customer', 'SalesInvoice')
    and attachable_id (the BigInt ID of the associated record).
    """
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attachable_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    attachable_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    title: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    tenant = relationship("Tenant", backref="attachments")

    __table_args__ = (
        Index("ix_attachments_morph", "tenant_id", "attachable_type", "attachable_id"),
    )
