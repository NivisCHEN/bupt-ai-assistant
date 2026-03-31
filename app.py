"""Main FastAPI application for the BUPT Campus AI Assistant."""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager

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
# Background scheduler instance
# ---------------------------------------------------------------------------

_scheduler: BackgroundScheduler | None = None

# ---------------------------------------------------------------------------
# Lifespan context manager
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise all services on startup; clean up on shutdown."""
    global _scheduler

    logger.info("Starting BUPT Campus AI Assistant...")
    await init_all()

    memory_manager = await get_memory_manager()
    embedding_service = await get_embedding_service()
    _scheduler = BackgroundScheduler(
        memory_manager=memory_manager,
        embedding_service=embedding_service,
    )
    _scheduler.start()
    logger.info("Application startup complete")

    yield

    logger.info("Shutting down BUPT Campus AI Assistant...")
    if _scheduler is not None:
        _scheduler.stop()
        _scheduler = None
    await shutdown_all()
    logger.info("Application shutdown complete")


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
    lifespan=lifespan,
)

# Include API routes
app.include_router(router)

# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------

_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Key", "X-User-Token"],
)


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
