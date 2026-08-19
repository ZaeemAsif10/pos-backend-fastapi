from fastapi import FastAPI # pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware # pyrefly: ignore [missing-import]
from app.db.database import engine # pyrefly: ignore [missing-import]
from app.db.base import Base # pyrefly: ignore [missing-import]
from app.core.config import settings # pyrefly: ignore [missing-import]

# Import models so SQLAlchemy knows about them before creating tables
from app.models.business import Business # pyrefly: ignore [missing-import]
from app.models.branch import Branch, BranchVariantStock # pyrefly: ignore [missing-import]
from app.models.product import Category, Brand, Product, ProductVariant # pyrefly: ignore [missing-import]
from app.models.user import User, Role, Permission # pyrefly: ignore [missing-import]
from app.models.order import Order, OrderItem, OrderPayment # pyrefly: ignore [missing-import]
from app.models.customer import Customer # pyrefly: ignore [missing-import]
from app.models.payment_method import PaymentMethod # pyrefly: ignore [missing-import]

# Import the API router
from app.api.api_router import api_router # pyrefly: ignore [missing-import]

# Create all tables in the MySQL database
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the main API router
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def read_root():
    return {"message": f"Welcome to {settings.PROJECT_NAME} API!"}

@app.get("/health")
def health_check():
    return {"status": "ok"}
