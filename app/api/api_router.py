from fastapi import APIRouter
from app.api.v1.endpoints import auth, categories, brands, products, orders, customers, reports, users, purchases, payment_methods, businesses, branches, roles

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(businesses.router, prefix="/businesses", tags=["Businesses"])
api_router.include_router(branches.router, prefix="/branches", tags=["Branches"])
api_router.include_router(roles.router, prefix="/roles", tags=["Roles & Permissions"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(categories.router, prefix="/categories", tags=["Categories"])
api_router.include_router(brands.router, prefix="/brands", tags=["Brands"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(orders.router, prefix="/orders", tags=["Orders (Sell)"])
api_router.include_router(purchases.router, prefix="/purchases", tags=["Purchases"])
api_router.include_router(customers.router, prefix="/customers", tags=["Customers"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(payment_methods.router, prefix="/payment-methods", tags=["Payment Methods"])
