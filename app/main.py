import os
import re
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app.core.config import settings
from app.api.v1.api import api_router

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
)

# Set CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    """Format Pydantic 422 validation errors into a friendly, human-readable message."""
    messages = []
    for err in exc.errors():
        loc_parts = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
        field_name = ".".join(loc_parts).replace("_", " ").title() if loc_parts else "Field"
        msg = err.get("msg", "Invalid value")
        messages.append(f"{field_name}: {msg}")
    friendly_detail = " | ".join(messages) if messages else "Invalid input data. Please check all required fields."
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": friendly_detail, "errors": exc.errors()},
    )


@app.exception_handler(IntegrityError)
async def integrity_exception_handler(_request: Request, exc: IntegrityError):
    """Translate database unique / foreign key constraint violations into clear user-facing errors."""
    raw = str(getattr(exc, "orig", exc))
    match = re.search(r"Key \(([^)]+)\)=\(([^)]+)\) already exists", raw)
    if match:
        cols, vals = match.group(1), match.group(2)
        clean_col = cols.split(",")[-1].strip().replace("_", " ")
        clean_val = vals.split(",")[-1].strip()
        detail = f"A record with {clean_col} '{clean_val}' already exists. Please use a unique value."
        code = status.HTTP_409_CONFLICT
    elif "still referenced" in raw or "foreign key constraint" in raw.lower():
        detail = "Cannot complete this action because this record is linked to other active records."
        code = status.HTTP_400_BAD_REQUEST
    else:
        detail = "Database constraint error: duplicate or invalid linked record."
        code = status.HTTP_400_BAD_REQUEST
    return JSONResponse(status_code=code, content={"detail": detail})


def _cors_headers(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin")
    if origin and ("*" in settings.CORS_ORIGINS or origin in settings.CORS_ORIGINS):
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
        }
    return {}


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    """Return a clean JSON message for database errors."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Database operation error: {str(exc).splitlines()[0][:180]}"},
        headers=_cors_headers(request),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch any unhandled exception and return a structured user-friendly JSON error."""
    err_msg = str(exc).strip() or exc.__class__.__name__
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Server error while processing your request: {err_msg}"},
        headers=_cors_headers(request),
    )


app.include_router(api_router, prefix=settings.API_V1_STR)

# Serve static attachments and uploads
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/")
async def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "docs": f"{settings.API_V1_STR}/docs",
        "health": f"{settings.API_V1_STR}/health",
    }
