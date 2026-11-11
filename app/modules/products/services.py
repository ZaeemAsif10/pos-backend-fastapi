from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy import select, func, or_, and_, update, delete
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.products.models import (
    Category,
    Brand,
    Product,
    ProductUOMConversion,
    BranchStock,
)
from app.modules.branches.models import Branch
from app.modules.products.schemas import (
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse,
    BrandCreate,
    BrandUpdate,
    BrandResponse,
    ProductCreate,
    ProductUpdate,
    ProductListItem,
    ProductDetailResponse,
    ProductListResponse,
    ProductStats,
    ProductUOMConversionResponse,
    BranchStockResponse,
)


class CategoryService:
    @staticmethod
    async def list_categories(db: AsyncSession, tenant_id: int) -> List[CategoryResponse]:
        stmt = (
            select(
                Category,
                func.count(Product.id).label("product_count"),
            )
            .outerjoin(Product, Product.category_id == Category.id)
            .where(Category.tenant_id == tenant_id)
            .group_by(Category.id)
            .order_by(Category.name.asc())
        )
        res = await db.execute(stmt)
        results = []
        for cat, count in res.all():
            resp = CategoryResponse.model_validate(cat)
            resp.product_count = count
            results.append(resp)
        return results

    @staticmethod
    async def get_category(db: AsyncSession, tenant_id: int, category_id: int) -> Category:
        stmt = select(Category).where(Category.tenant_id == tenant_id, Category.id == category_id)
        res = await db.execute(stmt)
        cat = res.scalar_one_or_none()
        if not cat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category with ID {category_id} was not found.",
            )
        return cat

    @staticmethod
    async def create_category(db: AsyncSession, tenant_id: int, payload: CategoryCreate) -> CategoryResponse:
        # Check duplicate name or code
        dup_stmt = select(Category).where(
            Category.tenant_id == tenant_id,
            or_(
                func.lower(Category.name) == payload.name.strip().lower(),
                func.lower(Category.code) == payload.code.strip().lower(),
            ),
        )
        dup_res = await db.execute(dup_stmt)
        existing = dup_res.scalar_one_or_none()
        if existing:
            if existing.code.lower() == payload.code.strip().lower():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Category code '{payload.code.strip()}' already exists. Please use a unique code.",
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Category named '{payload.name.strip()}' already exists.",
            )

        cat = Category(
            tenant_id=tenant_id,
            parent_id=payload.parent_id,
            name=payload.name.strip(),
            code=payload.code.strip().upper(),
            description=payload.description.strip() if payload.description else None,
            is_active=payload.is_active,
        )
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        resp = CategoryResponse.model_validate(cat)
        resp.product_count = 0
        return resp

    @staticmethod
    async def update_category(
        db: AsyncSession, tenant_id: int, category_id: int, payload: CategoryUpdate
    ) -> CategoryResponse:
        cat = await CategoryService.get_category(db, tenant_id, category_id)

        if payload.name and payload.name.strip().lower() != cat.name.lower():
            dup = await db.execute(
                select(Category).where(
                    Category.tenant_id == tenant_id,
                    Category.id != category_id,
                    func.lower(Category.name) == payload.name.strip().lower(),
                )
            )
            if dup.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category name already in use.")
            cat.name = payload.name.strip()

        if payload.code and payload.code.strip().upper() != cat.code:
            dup = await db.execute(
                select(Category).where(
                    Category.tenant_id == tenant_id,
                    Category.id != category_id,
                    func.lower(Category.code) == payload.code.strip().lower(),
                )
            )
            if dup.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category code already in use.")
            cat.code = payload.code.strip().upper()

        if payload.parent_id is not None:
            if payload.parent_id == category_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category cannot be its own parent.")
            cat.parent_id = payload.parent_id
        if payload.description is not None:
            cat.description = payload.description.strip() if payload.description else None
        if payload.is_active is not None:
            cat.is_active = payload.is_active

        cat.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(cat)

        p_count = (
            await db.execute(select(func.count(Product.id)).where(Product.category_id == cat.id))
        ).scalar() or 0
        resp = CategoryResponse.model_validate(cat)
        resp.product_count = p_count
        return resp

    @staticmethod
    async def delete_category(db: AsyncSession, tenant_id: int, category_id: int) -> dict:
        cat = await CategoryService.get_category(db, tenant_id, category_id)
        # Check if products exist in category
        prod_count = (
            await db.execute(select(func.count(Product.id)).where(Product.category_id == category_id))
        ).scalar() or 0
        if prod_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete category '{cat.name}' because {prod_count} product(s) are assigned to it.",
            )
        await db.delete(cat)
        await db.commit()
        return {"message": f"Category '{cat.name}' was successfully deleted."}


class BrandService:
    @staticmethod
    async def list_brands(db: AsyncSession, tenant_id: int) -> List[BrandResponse]:
        stmt = (
            select(
                Brand,
                func.count(Product.id).label("product_count"),
            )
            .outerjoin(Product, Product.brand_id == Brand.id)
            .where(Brand.tenant_id == tenant_id)
            .group_by(Brand.id)
            .order_by(Brand.name.asc())
        )
        res = await db.execute(stmt)
        results = []
        for b, count in res.all():
            resp = BrandResponse.model_validate(b)
            resp.product_count = count
            results.append(resp)
        return results

    @staticmethod
    async def get_brand(db: AsyncSession, tenant_id: int, brand_id: int) -> Brand:
        stmt = select(Brand).where(Brand.tenant_id == tenant_id, Brand.id == brand_id)
        res = await db.execute(stmt)
        brand = res.scalar_one_or_none()
        if not brand:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Brand with ID {brand_id} was not found.",
            )
        return brand

    @staticmethod
    async def create_brand(db: AsyncSession, tenant_id: int, payload: BrandCreate) -> BrandResponse:
        dup_stmt = select(Brand).where(
            Brand.tenant_id == tenant_id,
            or_(
                func.lower(Brand.name) == payload.name.strip().lower(),
                func.lower(Brand.code) == payload.code.strip().lower(),
            ),
        )
        dup_res = await db.execute(dup_stmt)
        existing = dup_res.scalar_one_or_none()
        if existing:
            if existing.code.lower() == payload.code.strip().lower():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Brand code '{payload.code.strip()}' already exists.",
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Brand named '{payload.name.strip()}' already exists.",
            )

        brand = Brand(
            tenant_id=tenant_id,
            name=payload.name.strip(),
            code=payload.code.strip().upper(),
            origin=payload.origin.strip() if payload.origin else "Pakistan",
            description=payload.description.strip() if payload.description else None,
            is_active=payload.is_active,
        )
        db.add(brand)
        await db.commit()
        await db.refresh(brand)
        resp = BrandResponse.model_validate(brand)
        resp.product_count = 0
        return resp

    @staticmethod
    async def update_brand(
        db: AsyncSession, tenant_id: int, brand_id: int, payload: BrandUpdate
    ) -> BrandResponse:
        brand = await BrandService.get_brand(db, tenant_id, brand_id)

        if payload.name and payload.name.strip().lower() != brand.name.lower():
            dup = await db.execute(
                select(Brand).where(
                    Brand.tenant_id == tenant_id,
                    Brand.id != brand_id,
                    func.lower(Brand.name) == payload.name.strip().lower(),
                )
            )
            if dup.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Brand name already in use.")
            brand.name = payload.name.strip()

        if payload.code and payload.code.strip().upper() != brand.code:
            dup = await db.execute(
                select(Brand).where(
                    Brand.tenant_id == tenant_id,
                    Brand.id != brand_id,
                    func.lower(Brand.code) == payload.code.strip().lower(),
                )
            )
            if dup.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Brand code already in use.")
            brand.code = payload.code.strip().upper()

        if payload.origin is not None:
            brand.origin = payload.origin.strip() if payload.origin else None
        if payload.description is not None:
            brand.description = payload.description.strip() if payload.description else None
        if payload.is_active is not None:
            brand.is_active = payload.is_active

        brand.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(brand)

        p_count = (
            await db.execute(select(func.count(Product.id)).where(Product.brand_id == brand.id))
        ).scalar() or 0
        resp = BrandResponse.model_validate(brand)
        resp.product_count = p_count
        return resp

    @staticmethod
    async def delete_brand(db: AsyncSession, tenant_id: int, brand_id: int) -> dict:
        brand = await BrandService.get_brand(db, tenant_id, brand_id)
        # Unlink products or alert
        await db.execute(
            update(Product)
            .where(Product.brand_id == brand_id)
            .values(brand_id=None)
        )
        await db.delete(brand)
        await db.commit()
        return {"message": f"Brand '{brand.name}' was successfully deleted."}


class ProductService:
    @staticmethod
    async def list_products(
        db: AsyncSession,
        tenant_id: int,
        search: Optional[str] = None,
        category_id: Optional[int] = None,
        brand_id: Optional[int] = None,
        stock_status: Optional[str] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        size: int = 50,
    ) -> ProductListResponse:
        """
        List products with multi-branch stock sum, filters, and inventory stats.
        """
        base_query = (
            select(
                Product,
                Category.name.label("category_name"),
                Brand.name.label("brand_name"),
                func.coalesce(func.sum(BranchStock.quantity), 0.0).label("total_stock"),
            )
            .join(Category, Product.category_id == Category.id)
            .outerjoin(Brand, Product.brand_id == Brand.id)
            .outerjoin(BranchStock, BranchStock.product_id == Product.id)
            .where(Product.tenant_id == tenant_id)
            .group_by(Product.id, Category.name, Brand.name)
        )

        if search:
            s = f"%{search.strip()}%"
            base_query = base_query.where(
                or_(
                    Product.name.ilike(s),
                    Product.sku.ilike(s),
                    Product.barcode.ilike(s),
                )
            )

        if category_id:
            base_query = base_query.where(Product.category_id == category_id)

        if brand_id:
            base_query = base_query.where(Product.brand_id == brand_id)

        if is_active is not None:
            base_query = base_query.where(Product.is_active.is_(is_active))

        # Stock status filtering using HAVING
        if stock_status == "out_of_stock":
            base_query = base_query.having(func.coalesce(func.sum(BranchStock.quantity), 0.0) <= 0)
        elif stock_status == "low_stock":
            base_query = base_query.having(
                and_(
                    func.coalesce(func.sum(BranchStock.quantity), 0.0) > 0,
                    func.coalesce(func.sum(BranchStock.quantity), 0.0) <= Product.reorder_level,
                )
            )
        elif stock_status == "in_stock":
            base_query = base_query.having(
                func.coalesce(func.sum(BranchStock.quantity), 0.0) > Product.reorder_level
            )

        # Count total
        count_subquery = base_query.subquery()
        total_stmt = select(func.count()).select_from(count_subquery)
        total_res = await db.execute(total_stmt)
        total = total_res.scalar() or 0

        # Execute pagination
        paginated_query = (
            base_query.order_by(Product.name.asc())
            .offset((page - 1) * size)
            .limit(size)
        )
        res = await db.execute(paginated_query)
        rows = res.all()

        items = []
        for prod, cat_name, b_name, stock in rows:
            tot_stock = float(stock)
            if tot_stock <= 0:
                s_status = "out_of_stock"
            elif tot_stock <= prod.reorder_level:
                s_status = "low_stock"
            else:
                s_status = "in_stock"

            item = ProductListItem(
                id=prod.id,
                name=prod.name,
                sku=prod.sku,
                barcode=prod.barcode,
                category_id=prod.category_id,
                category_name=cat_name,
                brand_id=prod.brand_id,
                brand_name=b_name,
                base_unit=prod.base_unit,
                cost_price=float(prod.cost_price),
                retail_price=float(prod.retail_price),
                wholesale_price=float(prod.wholesale_price),
                tax_rate=float(prod.tax_rate),
                is_fbr_third_schedule=prod.is_fbr_third_schedule,
                has_batches=prod.has_batches,
                reorder_level=prod.reorder_level,
                image_url=prod.image_url,
                is_active=prod.is_active,
                total_stock=tot_stock,
                stock_status=s_status,
                created_at=prod.created_at,
            )
            items.append(item)

        # Calculate high-level stats for the whole tenant
        stats_query = (
            select(
                Product.id,
                Product.cost_price,
                Product.reorder_level,
                func.coalesce(func.sum(BranchStock.quantity), 0.0).label("stock"),
            )
            .outerjoin(BranchStock, BranchStock.product_id == Product.id)
            .where(Product.tenant_id == tenant_id, Product.is_active.is_(True))
            .group_by(Product.id)
        )
        stats_res = await db.execute(stats_query)
        stats_rows = stats_res.all()

        tot_val = 0.0
        low_count = 0
        out_count = 0
        for pid, cost, reorder, st in stats_rows:
            s_val = float(st)
            tot_val += s_val * float(cost)
            if s_val <= 0:
                out_count += 1
            elif s_val <= reorder:
                low_count += 1

        stats = ProductStats(
            total_products=len(stats_rows),
            total_inventory_value=round(tot_val, 2),
            low_stock_count=low_count,
            out_of_stock_count=out_count,
        )

        return ProductListResponse(
            items=items,
            total=total,
            page=page,
            size=size,
            stats=stats,
        )

    @staticmethod
    async def get_product_detail(db: AsyncSession, tenant_id: int, product_id: int) -> ProductDetailResponse:
        """
        Get product 360 details including stock breakdown across all shops/godowns and UOM conversions.
        """
        stmt = (
            select(Product)
            .options(
                joinedload(Product.category),
                joinedload(Product.brand),
                selectinload(Product.uom_conversions),
                selectinload(Product.branch_stocks).joinedload(BranchStock.branch),
            )
            .where(Product.tenant_id == tenant_id, Product.id == product_id)
        )
        res = await db.execute(stmt)
        prod = res.scalar_one_or_none()
        if not prod:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID {product_id} was not found in catalogue.",
            )

        # Compute branch stocks response
        b_stocks: List[BranchStockResponse] = []
        total_stock = 0.0
        for bs in prod.branch_stocks:
            qty = float(bs.quantity)
            total_stock += qty
            b_stocks.append(
                BranchStockResponse(
                    id=bs.id,
                    branch_id=bs.branch_id,
                    branch_name=bs.branch.name if bs.branch else f"Branch #{bs.branch_id}",
                    branch_code=bs.branch.code if bs.branch else "",
                    branch_type=bs.branch.type.value if hasattr(bs.branch.type, "value") else str(bs.branch.type),
                    quantity=qty,
                    reserved_quantity=float(bs.reserved_quantity),
                    reorder_point=bs.reorder_point,
                    updated_at=bs.updated_at,
                )
            )

        # Sort branch stocks by name
        b_stocks.sort(key=lambda x: x.branch_name)

        if total_stock <= 0:
            stock_status = "out_of_stock"
        elif total_stock <= prod.reorder_level:
            stock_status = "low_stock"
        else:
            stock_status = "in_stock"

        uom_conversions = [
            ProductUOMConversionResponse.model_validate(c) for c in prod.uom_conversions
        ]

        return ProductDetailResponse(
            id=prod.id,
            tenant_id=prod.tenant_id,
            name=prod.name,
            sku=prod.sku,
            barcode=prod.barcode,
            category_id=prod.category_id,
            category_name=prod.category.name if prod.category else "",
            brand_id=prod.brand_id,
            brand_name=prod.brand.name if prod.brand else None,
            base_unit=prod.base_unit,
            cost_price=float(prod.cost_price),
            retail_price=float(prod.retail_price),
            wholesale_price=float(prod.wholesale_price),
            min_price=float(prod.min_price) if prod.min_price is not None else None,
            tax_rate=float(prod.tax_rate),
            is_fbr_third_schedule=prod.is_fbr_third_schedule,
            has_batches=prod.has_batches,
            reorder_level=prod.reorder_level,
            image_url=prod.image_url,
            description=prod.description,
            is_active=prod.is_active,
            total_stock=total_stock,
            stock_status=stock_status,
            uom_conversions=uom_conversions,
            branch_stocks=b_stocks,
            created_at=prod.created_at,
            updated_at=prod.updated_at,
        )

    @staticmethod
    async def create_product(db: AsyncSession, tenant_id: int, payload: ProductCreate) -> ProductDetailResponse:
        """
        Create a new product with UOM conversions and auto-initialize branch stock balances.
        """
        # 1. Validate Category belongs to tenant
        cat = await db.get(Category, payload.category_id)
        if not cat or cat.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Category with ID {payload.category_id} is invalid or does not belong to your business.",
            )

        # 2. Validate Brand if specified
        if payload.brand_id:
            brand = await db.get(Brand, payload.brand_id)
            if not brand or brand.tenant_id != tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Brand with ID {payload.brand_id} is invalid.",
                )

        # 3. Check SKU uniqueness
        sku_clean = payload.sku.strip().upper()
        sku_dup = await db.execute(
            select(Product).where(Product.tenant_id == tenant_id, Product.sku == sku_clean)
        )
        if sku_dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Product with SKU '{sku_clean}' already exists. Please choose a distinct SKU.",
            )

        # 4. Check Barcode uniqueness if provided
        barcode_clean = payload.barcode.strip() if payload.barcode else None
        if barcode_clean:
            bc_dup = await db.execute(
                select(Product).where(Product.tenant_id == tenant_id, Product.barcode == barcode_clean)
            )
            if bc_dup.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Product with barcode '{barcode_clean}' already exists.",
                )

        now = datetime.now(timezone.utc)
        prod = Product(
            tenant_id=tenant_id,
            name=payload.name.strip(),
            sku=sku_clean,
            barcode=barcode_clean,
            category_id=payload.category_id,
            brand_id=payload.brand_id,
            base_unit=payload.base_unit.strip() if payload.base_unit else "Piece",
            cost_price=payload.cost_price,
            retail_price=payload.retail_price,
            wholesale_price=payload.wholesale_price,
            min_price=payload.min_price,
            tax_rate=payload.tax_rate,
            is_fbr_third_schedule=payload.is_fbr_third_schedule,
            has_batches=payload.has_batches,
            reorder_level=payload.reorder_level,
            image_url=payload.image_url.strip() if payload.image_url else None,
            description=payload.description.strip() if payload.description else None,
            is_active=payload.is_active,
            created_at=now,
            updated_at=now,
        )
        db.add(prod)
        await db.flush()

        # 5. Add UOM conversions
        if payload.uom_conversions:
            for conv in payload.uom_conversions:
                c_obj = ProductUOMConversion(
                    tenant_id=tenant_id,
                    product_id=prod.id,
                    unit_name=conv.unit_name.strip(),
                    conversion_factor=conv.conversion_factor,
                    carton_barcode=conv.carton_barcode.strip() if conv.carton_barcode else None,
                    carton_wholesale_price=conv.carton_wholesale_price,
                    carton_retail_price=conv.carton_retail_price,
                    created_at=now,
                )
                db.add(c_obj)

        # 6. Auto-initialize BranchStock across all tenant branches
        branches_res = await db.execute(
            select(Branch).where(Branch.tenant_id == tenant_id)
        )
        branches = branches_res.scalars().all()

        initial_stock_map = {item.branch_id: item.quantity for item in payload.initial_stocks}
        reorder_point_map = {item.branch_id: item.reorder_point for item in payload.initial_stocks}

        for br in branches:
            init_qty = initial_stock_map.get(br.id, 0.0)
            rp = reorder_point_map.get(br.id, payload.reorder_level)
            b_stock = BranchStock(
                tenant_id=tenant_id,
                product_id=prod.id,
                branch_id=br.id,
                quantity=init_qty,
                reserved_quantity=0.0,
                reorder_point=rp,
                updated_at=now,
            )
            db.add(b_stock)

        await db.commit()
        return await ProductService.get_product_detail(db, tenant_id, prod.id)

    @staticmethod
    async def update_product(
        db: AsyncSession, tenant_id: int, product_id: int, payload: ProductUpdate
    ) -> ProductDetailResponse:
        """
        Update product specifications and UOM conversions.
        """
        prod_stmt = select(Product).where(Product.tenant_id == tenant_id, Product.id == product_id)
        prod_res = await db.execute(prod_stmt)
        prod = prod_res.scalar_one_or_none()
        if not prod:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID {product_id} was not found.",
            )

        if payload.sku and payload.sku.strip().upper() != prod.sku:
            clean_sku = payload.sku.strip().upper()
            dup = await db.execute(
                select(Product).where(
                    Product.tenant_id == tenant_id,
                    Product.id != product_id,
                    Product.sku == clean_sku,
                )
            )
            if dup.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"SKU '{clean_sku}' is already in use.")
            prod.sku = clean_sku

        if payload.barcode is not None and payload.barcode.strip() != (prod.barcode or ""):
            clean_bc = payload.barcode.strip() if payload.barcode.strip() else None
            if clean_bc:
                dup = await db.execute(
                    select(Product).where(
                        Product.tenant_id == tenant_id,
                        Product.id != product_id,
                        Product.barcode == clean_bc,
                    )
                )
                if dup.scalar_one_or_none():
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Barcode '{clean_bc}' is already in use.")
            prod.barcode = clean_bc

        if payload.category_id is not None:
            cat = await db.get(Category, payload.category_id)
            if not cat or cat.tenant_id != tenant_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Category ID.")
            prod.category_id = payload.category_id

        if payload.brand_id is not None:
            if payload.brand_id == 0:
                prod.brand_id = None
            else:
                brand = await db.get(Brand, payload.brand_id)
                if not brand or brand.tenant_id != tenant_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Brand ID.")
                prod.brand_id = payload.brand_id

        if payload.name is not None:
            prod.name = payload.name.strip()
        if payload.base_unit is not None:
            prod.base_unit = payload.base_unit.strip()
        if payload.cost_price is not None:
            prod.cost_price = payload.cost_price
        if payload.retail_price is not None:
            prod.retail_price = payload.retail_price
        if payload.wholesale_price is not None:
            prod.wholesale_price = payload.wholesale_price
        if payload.min_price is not None:
            prod.min_price = payload.min_price
        if payload.tax_rate is not None:
            prod.tax_rate = payload.tax_rate
        if payload.is_fbr_third_schedule is not None:
            prod.is_fbr_third_schedule = payload.is_fbr_third_schedule
        if payload.has_batches is not None:
            prod.has_batches = payload.has_batches
        if payload.reorder_level is not None:
            prod.reorder_level = payload.reorder_level
        if payload.image_url is not None:
            prod.image_url = payload.image_url.strip() if payload.image_url else None
        if payload.description is not None:
            prod.description = payload.description.strip() if payload.description else None
        if payload.is_active is not None:
            prod.is_active = payload.is_active

        # Update UOM conversions if provided
        if payload.uom_conversions is not None:
            await db.execute(
                delete(ProductUOMConversion).where(
                    ProductUOMConversion.tenant_id == tenant_id,
                    ProductUOMConversion.product_id == product_id,
                )
            )
            now = datetime.now(timezone.utc)
            for conv in payload.uom_conversions:
                c_obj = ProductUOMConversion(
                    tenant_id=tenant_id,
                    product_id=prod.id,
                    unit_name=conv.unit_name.strip(),
                    conversion_factor=conv.conversion_factor,
                    carton_barcode=conv.carton_barcode.strip() if conv.carton_barcode else None,
                    carton_wholesale_price=conv.carton_wholesale_price,
                    carton_retail_price=conv.carton_retail_price,
                    created_at=now,
                )
                db.add(c_obj)

        prod.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return await ProductService.get_product_detail(db, tenant_id, product_id)

    @staticmethod
    async def delete_product(db: AsyncSession, tenant_id: int, product_id: int) -> dict:
        prod_stmt = select(Product).where(Product.tenant_id == tenant_id, Product.id == product_id)
        prod_res = await db.execute(prod_stmt)
        prod = prod_res.scalar_one_or_none()
        if not prod:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID {product_id} was not found.",
            )

        name = prod.name
        await db.delete(prod)
        await db.commit()
        return {"message": f"Product '{name}' was permanently removed from catalogue."}

    @staticmethod
    async def update_branch_stock(
        db: AsyncSession,
        tenant_id: int,
        product_id: int,
        branch_id: int,
        quantity: float,
        reorder_point: Optional[int] = None,
    ) -> BranchStockResponse:
        """
        Set or adjust physical inventory quantity for a specific branch or godown.
        """
        # Ensure branch belongs to tenant
        branch = await db.get(Branch, branch_id)
        if not branch or branch.tenant_id != tenant_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Branch ID.")

        stmt = select(BranchStock).where(
            BranchStock.tenant_id == tenant_id,
            BranchStock.product_id == product_id,
            BranchStock.branch_id == branch_id,
        )
        res = await db.execute(stmt)
        b_stock = res.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if not b_stock:
            b_stock = BranchStock(
                tenant_id=tenant_id,
                product_id=product_id,
                branch_id=branch_id,
                quantity=quantity,
                reserved_quantity=0.0,
                reorder_point=reorder_point,
                updated_at=now,
            )
            db.add(b_stock)
        else:
            b_stock.quantity = quantity
            if reorder_point is not None:
                b_stock.reorder_point = reorder_point
            b_stock.updated_at = now

        await db.commit()
        await db.refresh(b_stock)

        return BranchStockResponse(
            id=b_stock.id,
            branch_id=branch.id,
            branch_name=branch.name,
            branch_code=branch.code,
            branch_type=branch.type.value if hasattr(branch.type, "value") else str(branch.type),
            quantity=float(b_stock.quantity),
            reserved_quantity=float(b_stock.reserved_quantity),
            reorder_point=b_stock.reorder_point,
            updated_at=b_stock.updated_at,
        )
