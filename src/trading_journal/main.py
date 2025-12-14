"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trading_journal.api.routes import (
    analytics,
    calendar,
    dashboard,
    executions,
    greeks,
    performance,
    positions,
    rolls,
    splits,
    trades,
)
from trading_journal.config import get_settings
from trading_journal.core.database import close_db, init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    await init_db()
    yield
    # Shutdown
    await close_db()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(executions.router, prefix="/api/v1")
app.include_router(trades.router, prefix="/api/v1")
app.include_router(positions.router, prefix="/api/v1")
app.include_router(greeks.router, prefix="/api/v1")
app.include_router(rolls.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(performance.router, prefix="/api/v1")
app.include_router(calendar.router, prefix="/api/v1")
app.include_router(splits.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}
