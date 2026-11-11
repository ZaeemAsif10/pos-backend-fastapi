from typing import Optional, List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.models import User
from app.modules.auth.router import get_current_user
from app.modules.team.services import TeamService
from app.modules.products.schemas import (
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse,
    BrandCreate,
    BrandUpdate,
    BrandResponse,
    ProductCreate,
    ProductUpdate,
    ProductDetailResponse,
    ProductListResponse,
    BranchStockResponse,
)
from app.modules.products.services import (
    CategoryService,
    BrandService,
    ProductService,
)

router = APIRouter(prefix="/tenant", tags=["Tenant Products & Catalogue"])


# ==========================================
# CATEGORIES ENDPOINTS
# ==========================================
@router.get(
    "/categories",
    response_model=List[CategoryResponse],
    summary="List Product Categories",
)
async def list_categories(
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns all product categories with product counts."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_category_view_permission(current_user, tenant, db)
    return await CategoryService.list_categories(db, tenant.id)


@router.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Category",
)
async def create_category(
    payload: CategoryCreate,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new product category."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_category_create_permission(current_user, tenant, db)
    return await CategoryService.create_category(db, tenant.id, payload)


@router.put(
    "/categories/{category_id}",
    response_model=CategoryResponse,
    summary="Update Category",
)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update category details or parent hierarchy."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_category_edit_permission(current_user, tenant, db)
    return await CategoryService.update_category(db, tenant.id, category_id, payload)


@router.delete(
    "/categories/{category_id}",
    summary="Delete Category",
)
async def delete_category(
    category_id: int,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a category (blocked if products are linked)."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_category_delete_permission(current_user, tenant, db)
    return await CategoryService.delete_category(db, tenant.id, category_id)


# ==========================================
# BRANDS ENDPOINTS
# ==========================================
@router.get(
    "/brands",
    response_model=List[BrandResponse],
    summary="List Product Brands / Manufacturers",
)
async def list_brands(
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns all brands/manufacturers with product counts."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_brand_view_permission(current_user, tenant, db)
    return await BrandService.list_brands(db, tenant.id)


@router.post(
    "/brands",
    response_model=BrandResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Brand",
)
async def create_brand(
    payload: BrandCreate,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new brand / principal manufacturer."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_brand_create_permission(current_user, tenant, db)
    return await BrandService.create_brand(db, tenant.id, payload)


@router.put(
    "/brands/{brand_id}",
    response_model=BrandResponse,
    summary="Update Brand",
)
async def update_brand(
    brand_id: int,
    payload: BrandUpdate,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update brand information."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_brand_edit_permission(current_user, tenant, db)
    return await BrandService.update_brand(db, tenant.id, brand_id, payload)


@router.delete(
    "/brands/{brand_id}",
    summary="Delete Brand",
)
async def delete_brand(
    brand_id: int,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a brand."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_brand_delete_permission(current_user, tenant, db)
    return await BrandService.delete_brand(db, tenant.id, brand_id)


# ==========================================
# PRODUCTS MASTER ENDPOINTS
# ==========================================
@router.get(
    "/products",
    response_model=ProductListResponse,
    summary="List Products Catalogue with Multi-Branch Inventory",
)
async def list_products(
    search: Optional[str] = Query(None, description="Search by Name, SKU, or Barcode"),
    category_id: Optional[int] = Query(None, description="Filter by Category ID"),
    brand_id: Optional[int] = Query(None, description="Filter by Brand ID"),
    stock_status: Optional[str] = Query(None, description="Filter: in_stock, low_stock, out_of_stock"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page (default 10)"),
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns products catalogue with overall stats, filters, and stock sum."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_product_view_permission(current_user, tenant, db)
    return await ProductService.list_products(
        db=db,
        tenant_id=tenant.id,
        search=search,
        category_id=category_id,
        brand_id=brand_id,
        stock_status=stock_status,
        is_active=is_active,
        page=page,
        size=size,
    )


@router.post(
    "/products",
    response_model=ProductDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create New Product",
)
async def create_product(
    payload: ProductCreate,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new product with UOM conversions and auto-initialize branch stocks."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_product_create_permission(current_user, tenant, db)
    return await ProductService.create_product(db, tenant.id, payload)


@router.get(
    "/products/{product_id}",
    response_model=ProductDetailResponse,
    summary="Get Product 360 Details",
)
async def get_product(
    product_id: int,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch product details with multi-branch stock balances and UOM conversions."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_product_view_permission(current_user, tenant, db)
    return await ProductService.get_product_detail(db, tenant.id, product_id)


@router.put(
    "/products/{product_id}",
    response_model=ProductDetailResponse,
    summary="Update Product",
)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update product information, pricing, or conversions."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_product_edit_permission(current_user, tenant, db)
    return await ProductService.update_product(db, tenant.id, product_id, payload)


@router.delete(
    "/products/{product_id}",
    summary="Delete Product",
)
async def delete_product(
    product_id: int,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a product from catalogue."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_product_delete_permission(current_user, tenant, db)
    return await ProductService.delete_product(db, tenant.id, product_id)


@router.put(
    "/products/{product_id}/branches/{branch_id}/stock",
    response_model=BranchStockResponse,
    summary="Adjust Branch Physical Stock",
)
async def update_branch_stock(
    product_id: int,
    branch_id: int,
    quantity: float = Query(..., ge=0, description="New physical inventory count"),
    reorder_point: Optional[int] = Query(None, ge=0, description="Optional branch reorder threshold"),
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Directly adjust physical stock at a specific shop or warehouse."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_product_edit_permission(current_user, tenant, db)
    return await ProductService.update_branch_stock(
        db, tenant.id, product_id, branch_id, quantity, reorder_point
    )
