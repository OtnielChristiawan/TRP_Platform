"""FastAPI application entry point for Bakery Data Platform V4 Sales Analytics."""
import logging
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import admin, categories, dashboard, data, filters, health, menus, ml, operations, payments, sales
from app.core.config import settings
from app.core.security import Role, require_role
from app.db.duckdb_connection import get_db_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bakery.api")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Sales Analytics REST API for Toko Roti Pagi (TRP) powered by DuckDB & MinIO Gold Parquet.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    logger.info("Initializing Bakery Data Platform Backend...")
    try:
        # Pre-warm DuckDB connection and verify S3 config
        db = get_db_manager()
        logger.info("DuckDB S3 connection pre-warmed successfully.")
    except Exception as e:
        logger.error(f"Warning during startup DuckDB check: {e}")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Exception at {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error occurred while querying analytics data."},
    )


# Mount API V1 Routers
api_prefix = settings.API_V1_PREFIX

# Public health check (No auth required for container probes)
app.include_router(health.router, prefix=api_prefix)

# Serving & Analytics routers (Protected: Requires at least VIEWER role)
viewer_dep = [Depends(require_role(Role.VIEWER))]
app.include_router(data.router, prefix=api_prefix, dependencies=viewer_dep)
app.include_router(filters.router, prefix=api_prefix, dependencies=viewer_dep)
app.include_router(dashboard.router, prefix=api_prefix, dependencies=viewer_dep)
app.include_router(sales.router, prefix=api_prefix, dependencies=viewer_dep)
app.include_router(menus.router, prefix=api_prefix, dependencies=viewer_dep)
app.include_router(categories.router, prefix=api_prefix, dependencies=viewer_dep)
app.include_router(payments.router, prefix=api_prefix, dependencies=viewer_dep)
app.include_router(ml.router, prefix=api_prefix, dependencies=viewer_dep)

# Privileged Operational & Admin Routers (Internally enforce OPERATOR and ADMIN roles)
app.include_router(operations.router, prefix=api_prefix)
app.include_router(admin.router, prefix=api_prefix)


@app.get("/")
def root():
    return {
        "message": "Bakery Data Platform V4 - Sales Analytics API",
        "documentation": "/docs",
        "api_v1": api_prefix,
    }
