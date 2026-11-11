from typing import Optional, List
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.modules.auth.router import get_current_user
from app.modules.auth.models import User
from app.modules.team.services import TeamService
from app.modules.attachments.schemas import AttachmentResponse, AttachmentCreate
from app.modules.attachments.services import AttachmentService

router = APIRouter(prefix="/tenant/attachments", tags=["Attachments (Polymorphic)"])


@router.post(
    "/upload",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and link file/image to polymorphic attachments table",
)
async def upload_attachment(
    file: UploadFile = File(...),
    attachable_type: str = Form(..., description="Target model name e.g. Product, Customer, SalesInvoice"),
    attachable_id: int = Form(..., description="Target entity ID"),
    is_primary: bool = Form(True, description="Whether this is the primary asset (e.g. product main photo)"),
    title: Optional[str] = Form(None),
    tenant_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Uploads file to disk and stores record in the attachments table via polymorphic relation."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    subfolder = attachable_type.lower() + "s"
    saved_meta = await AttachmentService.save_uploaded_file(
        file,
        tenant_id=tenant.id,
        subfolder=subfolder,
        prefix=f"{attachable_type.lower()}_{attachable_id}",
    )

    payload = AttachmentCreate(
        attachable_type=attachable_type,
        attachable_id=attachable_id,
        file_name=saved_meta["file_name"],
        file_path=saved_meta["file_path"],
        file_type=saved_meta["file_type"],
        file_size=saved_meta["file_size"],
        is_primary=is_primary,
        title=title or file.filename,
    )

    return await AttachmentService.create_attachment(db, tenant.id, payload)


@router.get(
    "",
    response_model=List[AttachmentResponse],
    summary="List polymorphic attachments for an entity",
)
async def list_attachments(
    attachable_type: Optional[str] = Query(None, description="e.g. Product, Customer"),
    attachable_id: Optional[int] = Query(None, description="ID of entity"),
    tenant_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    return await AttachmentService.list_attachments(
        db, tenant.id, attachable_type=attachable_type, attachable_id=attachable_id
    )


@router.delete(
    "/{attachment_id}",
    summary="Delete an attachment record and file",
)
async def delete_attachment(
    attachment_id: int,
    tenant_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    return await AttachmentService.delete_attachment(db, tenant.id, attachment_id)
