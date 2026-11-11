import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import UploadFile, HTTPException, status
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.attachments.models import Attachment
from app.modules.attachments.schemas import AttachmentCreate, AttachmentResponse
from app.modules.products.models import Product

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)


class AttachmentService:
    @staticmethod
    async def save_uploaded_file(
        file: UploadFile,
        tenant_id: int,
        subfolder: str = "general",
        prefix: Optional[str] = None,
    ) -> dict:
        """Save an uploaded file to the multi-tenant directory:
        uploads/tenants/tenant_{tenant_id}/{subfolder}/{unique_name}
        """
        tenant_subpath = os.path.join("tenants", f"tenant_{tenant_id}", subfolder)
        target_dir = os.path.join(UPLOAD_DIR, tenant_subpath)
        os.makedirs(target_dir, exist_ok=True)

        # Generate unique filename while retaining original extension
        ext = os.path.splitext(file.filename or "")[1].lower()
        if not ext:
            ext = ".png" if "image" in (file.content_type or "") else ".bin"

        prefix_part = f"{prefix}_" if prefix else ""
        short_hash = uuid.uuid4().hex[:8]
        raw_name = os.path.splitext(os.path.basename(file.filename or "file"))[0]
        clean_base = "".join(c for c in raw_name if c.isalnum() or c in "-_")
        unique_name = f"{prefix_part}{clean_base}_{short_hash}{ext}"

        file_path = os.path.join(target_dir, unique_name)
        content = await file.read()
        file_size = len(content)

        with open(file_path, "wb") as out_file:
            out_file.write(content)

        # Relative URL served by FastAPI StaticFiles
        relative_url = f"/uploads/{tenant_subpath}/{unique_name}"

        return {
            "file_name": file.filename or unique_name,
            "file_path": relative_url,
            "file_type": file.content_type,
            "file_size": file_size,
        }

    @staticmethod
    async def create_attachment(
        db: AsyncSession,
        tenant_id: int,
        payload: AttachmentCreate,
    ) -> AttachmentResponse:
        """Create a polymorphic attachment record in the attachments table."""
        # If this is set as primary, unset any existing primary attachments for this entity
        if payload.is_primary:
            existing_primaries = (
                await db.execute(
                    select(Attachment).where(
                        Attachment.tenant_id == tenant_id,
                        Attachment.attachable_type == payload.attachable_type,
                        Attachment.attachable_id == payload.attachable_id,
                        Attachment.is_primary == True,
                    )
                )
            ).scalars().all()
            for p in existing_primaries:
                p.is_primary = False

        att = Attachment(
            tenant_id=tenant_id,
            attachable_type=payload.attachable_type,
            attachable_id=payload.attachable_id,
            file_name=payload.file_name,
            file_path=payload.file_path,
            file_type=payload.file_type,
            file_size=payload.file_size,
            is_primary=payload.is_primary,
            title=payload.title,
            description=payload.description,
        )
        db.add(att)
        await db.flush()

        # If attached to a Product and is primary, keep Product.image_url synchronized
        if payload.attachable_type == "Product":
            prod = (
                await db.execute(
                    select(Product).where(
                        Product.tenant_id == tenant_id,
                        Product.id == payload.attachable_id,
                    )
                )
            ).scalar_one_or_none()
            if prod:
                prod.image_url = payload.file_path

        await db.commit()
        await db.refresh(att)
        return AttachmentResponse.model_validate(att)

    @staticmethod
    async def list_attachments(
        db: AsyncSession,
        tenant_id: int,
        attachable_type: Optional[str] = None,
        attachable_id: Optional[int] = None,
    ) -> List[AttachmentResponse]:
        """List polymorphic attachments filtered by entity type and ID."""
        stmt = select(Attachment).where(Attachment.tenant_id == tenant_id)
        if attachable_type:
            stmt = stmt.where(Attachment.attachable_type == attachable_type)
        if attachable_id:
            stmt = stmt.where(Attachment.attachable_id == attachable_id)
        stmt = stmt.order_by(Attachment.is_primary.desc(), Attachment.created_at.desc())
        res = await db.execute(stmt)
        items = res.scalars().all()
        return [AttachmentResponse.model_validate(it) for it in items]

    @staticmethod
    async def delete_attachment(db: AsyncSession, tenant_id: int, attachment_id: int):
        att = (
            await db.execute(
                select(Attachment).where(
                    Attachment.tenant_id == tenant_id,
                    Attachment.id == attachment_id,
                )
            )
        ).scalar_one_or_none()
        if not att:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

        # Delete physical file if exists
        try:
            rel = att.file_path.lstrip("/")
            local_full = os.path.abspath(os.path.join(UPLOAD_DIR, "..", rel))
            if os.path.exists(local_full):
                os.remove(local_full)
        except Exception:
            pass

        await db.delete(att)
        await db.commit()
        return {"message": "Attachment deleted successfully"}
