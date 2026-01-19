"""
WeBoostX 2.0 - FastAPI Application Entry Point
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api.v1 import api_router, page_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    print(f"[STARTUP] Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"[ENV] Environment: {settings.ENVIRONMENT}")
    print(f"[DEBUG] Debug mode: {settings.DEBUG}")
    
    # Initialize scheduler if enabled
    if settings.SCHEDULER_ENABLED:
        from app.tasks.scheduler import start_scheduler
        start_scheduler()
        print("[SCHEDULER] Scheduler started")
    
    yield
    
    # Shutdown
    if settings.SCHEDULER_ENABLED:
        from app.tasks.scheduler import stop_scheduler
        stop_scheduler()
        print("[SCHEDULER] Scheduler stopped")
    
    print(f"[SHUTDOWN] Shutting down {settings.APP_NAME}")


def create_app() -> FastAPI:
    """Create FastAPI application"""
    
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Multi-Platform Ad Management System",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API routers
    app.include_router(api_router)
    
    # Include page routes (HTML pages)
    app.include_router(page_router)
    
    # Mount static files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    
    return app


# Create app instance
app = create_app()

