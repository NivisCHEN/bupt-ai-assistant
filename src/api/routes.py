"""FastAPI route definitions for the BUPT Campus AI Assistant."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from config.settings import settings
from src.api.dependencies import (
    get_dialogue_manager,
    get_embedding_service,
    get_memory_manager,
    get_memory_store,
    require_admin_key,
)
from src.dialogue.manager import DialogueManager
from src.embedding.service import EmbeddingService
from src.memory.manager import MemoryManager
from src.memory.store import MemoryStore
from src.models import ChatRequest, ChatResponse

router = APIRouter()

_GENERIC_ERROR = "服务内部错误，请稍后再试"

# In-memory store for portal cookies with TTL (production: use Redis)
_COOKIE_TTL = timedelta(hours=2)
_portal_cookies: dict[str, tuple[dict, datetime]] = {}


def _get_portal_cookies(username: str) -> dict | None:
    """Return cookies for a user, or None if missing/expired."""
    entry = _portal_cookies.get(username)
    if entry is None:
        return None
    cookies, created_at = entry
    if datetime.now(tz=timezone.utc) - created_at > _COOKIE_TTL:
        del _portal_cookies[username]
        return None
    return cookies


def _safe_detail(exc: Exception) -> str:
    """Return error detail suitable for the client.

    In debug mode the original exception message is exposed; in
    production a generic message is returned to prevent information
    leakage.
    """
    if settings.app.debug:
        return str(exc)
    return _GENERIC_ERROR


# ---------------------------------------------------------------------------
# Request / response schemas specific to the API layer
# ---------------------------------------------------------------------------


class MemorySearchRequest(BaseModel):
    """Body for the memory search endpoint."""

    query: str
    top_k: int = Field(default=5, ge=1, le=50)


class MemoryDeleteRequest(BaseModel):
    """Body for confirming memory deletion."""

    confirmation_token: str


class ReindexResponse(BaseModel):
    """Response after triggering a reindex."""

    status: str
    message: str


class CrawlResponse(BaseModel):
    """Response after triggering a crawl."""

    status: str
    source_name: str
    message: str


class PortalLoginRequest(BaseModel):
    """Body for BUPT portal login."""

    username: str
    password: str


class PortalLoginResponse(BaseModel):
    """Response after portal login attempt."""

    status: str
    message: str


class StatsResponse(BaseModel):
    """System statistics response."""

    status: str
    memory_count: int
    user_count: int
    index_sizes: dict


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


@router.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    dialogue_manager: DialogueManager = Depends(get_dialogue_manager),
) -> ChatResponse:
    """Process an incoming chat message and return an AI response."""
    try:
        response = await dialogue_manager.handle_message(request)
        return response
    except Exception as exc:
        logger.exception("Chat endpoint error for user {}", request.user_id)
        raise HTTPException(status_code=500, detail=_safe_detail(exc)) from exc


def _sse_format(event: dict) -> str:
    """Serialize one event dict as a single SSE message frame."""
    event_type = event.get("type", "message")
    payload = json.dumps(event, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


@router.post("/api/chat/stream")
async def chat_stream(
    request: ChatRequest,
    dialogue_manager: DialogueManager = Depends(get_dialogue_manager),
) -> StreamingResponse:
    """Stream a chat response as Server-Sent Events (SSE).

    Emits:
      * ``event: meta`` — sources, confidence, intent (once, before tokens)
      * ``event: token`` — incremental content chunks
      * ``event: done`` — final answer + suggestions
      * ``event: error`` — on failure
    """

    async def event_source() -> AsyncIterator[str]:
        try:
            async for event in dialogue_manager.handle_message_stream(request):
                yield _sse_format(event)
        except Exception as exc:
            logger.exception("Chat stream error for user {}", request.user_id)
            yield _sse_format({"type": "error", "message": _safe_detail(exc)})

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            # Disable nginx/proxy buffering so tokens flush to the client
            # as soon as the model produces them.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/api/health")
async def health() -> dict:
    """Return service health status and version information."""
    return {"status": "ok", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Memory endpoints (token-authenticated with user-id binding)
# ---------------------------------------------------------------------------


@router.post("/api/memory/{user_id}/search")
async def search_memories(
    user_id: str,
    body: MemorySearchRequest,
    memory_manager: MemoryManager = Depends(get_memory_manager),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
) -> dict:
    """Search a user's memories by semantic similarity."""
    try:
        query_vector = embedding_service.encode_query(body.query)
        if query_vector.size == 0:
            return {"user_id": user_id, "results": []}

        qv = (
            query_vector[0].tolist()
            if query_vector.ndim > 1
            else query_vector.tolist()
        )
        results = memory_manager.store.search_memory(
            user_id, qv, top_k=body.top_k
        )
        return {
            "user_id": user_id,
            "results": [entry.model_dump(mode="json") for entry in results],
        }
    except Exception as exc:
        logger.exception("Memory search failed for user {}", user_id)
        raise HTTPException(status_code=500, detail=_safe_detail(exc)) from exc


@router.get("/api/memory/{user_id}/history")
async def get_history(
    user_id: str,
    limit: int = Query(default=10, ge=1, le=100),
    memory_store: MemoryStore = Depends(get_memory_store),
) -> dict:
    """Return recent conversation history for a user."""
    try:
        entries = memory_store.get_recent_history(user_id, limit=limit)
        return {
            "user_id": user_id,
            "history": [entry.model_dump(mode="json") for entry in entries],
        }
    except Exception as exc:
        logger.exception("History retrieval failed for user {}", user_id)
        raise HTTPException(status_code=500, detail=_safe_detail(exc)) from exc


@router.delete("/api/memory/{user_id}/{memory_id}")
async def delete_memory(
    user_id: str,
    memory_id: str,
    confirmation_token: str = Query(..., description="Token to confirm deletion"),
    memory_store: MemoryStore = Depends(get_memory_store),
) -> dict:
    """Delete a specific memory entry for a user."""
    expected_token = f"confirm-delete-{memory_id}"
    if confirmation_token != expected_token:
        raise HTTPException(
            status_code=403,
            detail="Invalid confirmation token. "
            "Expected format: confirm-delete-<memory_id>",
        )

    deleted = await memory_store.delete_memory(user_id, memory_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Memory {memory_id} not found for user {user_id}",
        )

    return {
        "status": "deleted",
        "user_id": user_id,
        "memory_id": memory_id,
    }


# ---------------------------------------------------------------------------
# Portal authentication endpoints
# ---------------------------------------------------------------------------


@router.post("/api/portal/login", response_model=PortalLoginResponse)
async def portal_login(
    request: PortalLoginRequest,
) -> PortalLoginResponse:
    """用北邮统一认证账号密码登录，解锁内部数据源爬取。"""
    try:
        from src.crawler.auth import login_bupt_portal

        cookies = await login_bupt_portal(request.username, request.password)
        _portal_cookies[request.username] = (cookies, datetime.now(tz=timezone.utc))
        return PortalLoginResponse(status="ok", message="登录成功")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Portal login failed for {}", request.username)
        raise HTTPException(status_code=500, detail=_safe_detail(exc)) from exc


@router.post("/api/portal/crawl")
async def crawl_portal(
    username: str = Query(...),
) -> dict:
    """使用已认证的 cookies 爬取需要登录的内部数据源。"""
    cookies = _get_portal_cookies(username)
    if not cookies:
        raise HTTPException(status_code=401, detail="请先登录北邮门户")

    from src.crawler.base import BUPT_DATA_SOURCES
    from src.crawler.spider import BUPTSpider

    auth_sources = [s for s in BUPT_DATA_SOURCES if s.requires_auth]
    results = {}
    for source in auth_sources:
        spider = BUPTSpider(source=source, cookies=cookies)
        docs = await spider.crawl()
        results[source.name] = len(docs)

    return {"status": "ok", "crawled": results}


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@router.post("/api/admin/reindex", response_model=ReindexResponse)
async def reindex(
    _admin: str = Depends(require_admin_key),
    memory_store: MemoryStore = Depends(get_memory_store),
) -> ReindexResponse:
    """Trigger a full knowledge base reindex."""
    try:
        memory_store._rebuild_all_indices()
        user_count = len(memory_store.user_faiss_stores)
        return ReindexResponse(
            status="ok",
            message=f"Reindexed {user_count} user indices",
        )
    except Exception as exc:
        logger.exception("Reindex failed")
        raise HTTPException(status_code=500, detail=_safe_detail(exc)) from exc


@router.post("/api/admin/crawl/{source_name}", response_model=CrawlResponse)
async def crawl(
    source_name: str,
    _admin: str = Depends(require_admin_key),
) -> CrawlResponse:
    """Trigger a crawl for a specific data source."""

    supported_sources = {"news", "library", "courses", "notices", "faculty"}

    if source_name not in supported_sources:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown source '{source_name}'. "
            f"Supported: {', '.join(sorted(supported_sources))}",
        )

    logger.info("Crawl triggered for source: {}", source_name)

    return CrawlResponse(
        status="accepted",
        source_name=source_name,
        message=f"Crawl job for '{source_name}' has been enqueued",
    )


@router.get("/api/admin/stats", response_model=StatsResponse)
async def stats(
    _admin: str = Depends(require_admin_key),
    memory_store: MemoryStore = Depends(get_memory_store),
) -> StatsResponse:
    """Return system-wide statistics."""
    try:
        info = await memory_store.get_stats()
        return StatsResponse(
            status="ok",
            memory_count=info["memory_count"],
            user_count=info["user_count"],
            index_sizes=info["index_sizes"],
        )
    except Exception as exc:
        logger.exception("Stats retrieval failed")
        raise HTTPException(status_code=500, detail=_safe_detail(exc)) from exc
