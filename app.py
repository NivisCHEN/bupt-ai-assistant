"""Main FastAPI application for the BUPT Campus AI Assistant."""

from __future__ import annotations

import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.api.dependencies import (
    get_embedding_service,
    get_memory_manager,
    init_all,
    shutdown_all,
)
from src.api.routes import router
from src.scheduler.background import BackgroundScheduler

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="BUPT Campus AI Assistant",
    description=(
        "北京邮电大学智能校园助理 — 提供校园知识问答、个性化记忆、"
        "任务执行等功能的 AI 对话系统。"
    ),
    version="0.1.0",
)

# Include API routes
app.include_router(router)

# ---------------------------------------------------------------------------
# CORS middleware (allow all origins for development)
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Background scheduler instance (created at module level, started on startup)
# ---------------------------------------------------------------------------

_scheduler: BackgroundScheduler | None = None

# ---------------------------------------------------------------------------
# Lifecycle events
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def on_startup() -> None:
    """Initialise all services and start the background scheduler."""
    global _scheduler

    logger.info("Starting BUPT Campus AI Assistant...")
    await init_all()

    # Wire up the background scheduler
    memory_manager = await get_memory_manager()
    embedding_service = await get_embedding_service()
    _scheduler = BackgroundScheduler(
        memory_manager=memory_manager,
        embedding_service=embedding_service,
    )
    _scheduler.start()
    logger.info("Application startup complete")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Stop the background scheduler and clean up services."""
    global _scheduler

    logger.info("Shutting down BUPT Campus AI Assistant...")
    if _scheduler is not None:
        _scheduler.stop()
        _scheduler = None
    await shutdown_all()
    logger.info("Application shutdown complete")


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every incoming request with method, path, and response duration."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    logger.info(
        "{method} {path} -> {status} ({duration:.1f}ms)",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration=duration_ms,
    )
    return response


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from config.settings import settings as app_settings

    uvicorn.run(
        "app:app",
        host=app_settings.app.host,
        port=app_settings.app.port,
        reload=app_settings.app.debug,
    )
