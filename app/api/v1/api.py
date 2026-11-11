from fastapi import APIRouter
from app.modules.health.router import router as health_router
from app.modules.auth.router import router as auth_router
from app.modules.admin.router import router as admin_router
from app.modules.plans.router import (
    public_router as plans_public_router,
    admin_router as plans_admin_router,
)
from app.modules.team.router import router as team_router
from app.modules.branches.router import router as branches_router
from app.modules.products.router import router as products_router
from app.modules.parties.router import router as parties_router
from app.modules.inventory.router import router as inventory_router
from app.modules.sales.router import router as sales_router
from app.modules.attachments.router import router as attachments_router
from app.modules.accounting.router import router as accounting_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["Health"])
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(plans_public_router)
api_router.include_router(plans_admin_router)
api_router.include_router(team_router)
api_router.include_router(branches_router)
api_router.include_router(products_router)
api_router.include_router(parties_router)
api_router.include_router(inventory_router)
api_router.include_router(sales_router)
api_router.include_router(attachments_router)
api_router.include_router(accounting_router)




