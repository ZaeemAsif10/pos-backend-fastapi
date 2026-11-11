from typing import Generic, TypeVar, List, Optional, Tuple, Any
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int
    total_pages: int

    class Config:
        from_attributes = True


async def paginate_query(
    db: AsyncSession,
    base_select,
    page: int = 1,
    size: int = 10,
    count_override=None,
) -> Tuple[List[Any], int, int, int]:
    """
    Executes a paginated SQLAlchemy query.
    Defaults: page=1, size=10.
    Returns: (items, total, page, total_pages)
    """
    if page < 1:
        page = 1
    if size < 1:
        size = 10
    if size > 100:
        size = 100

    # Calculate total count
    if count_override is not None:
        total_res = await db.execute(count_override)
        total = total_res.scalar_one_or_none() or 0
    else:
        count_stmt = select(func.count()).select_from(base_select.order_by(None).subquery())
        total_res = await db.execute(count_stmt)
        total = total_res.scalar_one_or_none() or 0

    # Fetch paginated items
    offset = (page - 1) * size
    paginated_stmt = base_select.offset(offset).limit(size)
    items_res = await db.execute(paginated_stmt)
    items = list(items_res.scalars().all())

    total_pages = (total + size - 1) // size if total > 0 else 1
    return items, total, page, total_pages
