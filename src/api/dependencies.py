"""FastAPI dependency injection functions for the BUPT Campus AI Assistant.

Provides singleton-based dependency factories so that service instances are
created once and reused across request handlers.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException, Header
from loguru import logger

from config.settings import settings as app_settings
from src.dialogue.manager import DialogueManager
from src.dialogue.prompt_builder import PromptBuilder
from src.dialogue.router import IntentRouter
from src.embedding.service import EmbeddingService
from src.llm.client import LLMClient
from src.memory.compressor import MemoryCompressor
from src.memory.manager import MemoryManager
from src.memory.store import MemoryStore
from src.retriever.faiss_store import FAISSStore
from src.retriever.hybrid_retriever import HybridRetriever

# ---------------------------------------------------------------------------
# Singleton registry
# ---------------------------------------------------------------------------

_instances: dict[str, Any] = {}

# ---------------------------------------------------------------------------
# Admin key authentication
# ---------------------------------------------------------------------------

_ADMIN_KEY = os.getenv("ADMIN_API_KEY", "")


async def require_admin_key(
    x_admin_key: str = Header(..., description="Admin API key"),
) -> str:
    """FastAPI dependency that validates the ``X-Admin-Key`` header."""
    if not _ADMIN_KEY or x_admin_key != _ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    return x_admin_key


# ---------------------------------------------------------------------------
# Dependency providers
# ---------------------------------------------------------------------------


async def get_embedding_service() -> EmbeddingService:
    """Return the embedding service singleton."""
    if "embedding_service" not in _instances:
        _instances["embedding_service"] = EmbeddingService(
            model_name=app_settings.embedding.model_name,
            device=app_settings.embedding.device,
            dimension=app_settings.embedding.dimension,
        )
        logger.info("EmbeddingService initialised")
    return _instances["embedding_service"]


async def get_llm_client() -> LLMClient:
    """Return the LLM client singleton."""
    if "llm_client" not in _instances:
        _instances["llm_client"] = LLMClient(
            api_key=app_settings.llm.api_key,
            base_url=app_settings.llm.base_url,
            model=app_settings.llm.model_name,
        )
        logger.info("LLMClient initialised")
    return _instances["llm_client"]


async def get_memory_store() -> MemoryStore:
    """Return the memory store singleton."""
    if "memory_store" not in _instances:
        embedding_service = await get_embedding_service()
        store = MemoryStore(
            embedding_service=embedding_service,
            faiss_dimension=app_settings.embedding.dimension,
        )
        await store.initialize()
        _instances["memory_store"] = store
        logger.info("MemoryStore initialised (SQLite-backed)")
    return _instances["memory_store"]


async def get_memory_manager() -> MemoryManager:
    """Return the memory manager singleton."""
    if "memory_manager" not in _instances:
        store = await get_memory_store()
        llm_client = await get_llm_client()
        embedding_service = await get_embedding_service()
        compressor = MemoryCompressor(
            llm_client=llm_client,
            embedding_service=embedding_service,
        )
        _instances["memory_manager"] = MemoryManager(
            store=store,
            compressor=compressor,
            embedding_service=embedding_service,
        )
        logger.info("MemoryManager initialised")
    return _instances["memory_manager"]


async def get_dialogue_manager() -> DialogueManager:
    """Return the dialogue manager singleton."""
    if "dialogue_manager" not in _instances:
        llm_client = await get_llm_client()
        embedding_service = await get_embedding_service()
        memory_manager = await get_memory_manager()
        memory_store = await get_memory_store()

        router = IntentRouter(llm_client=llm_client)
        prompt_builder = PromptBuilder()

        school_faiss_store = FAISSStore(dimension=app_settings.embedding.dimension)
        retriever = HybridRetriever(
            faiss_store=school_faiss_store,
            embedding_service=embedding_service,
        )

        _instances["dialogue_manager"] = DialogueManager(
            router=router,
            retriever=retriever,
            memory_manager=memory_manager,
            llm_client=llm_client,
            embedding_service=embedding_service,
            prompt_builder=prompt_builder,
        )
        logger.info("DialogueManager initialised")
    return _instances["dialogue_manager"]


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------


async def init_all() -> None:
    """Initialise all services. Called once during application startup."""
    logger.info("Initialising all services...")
    await get_embedding_service()
    await get_llm_client()
    await get_memory_store()
    await get_memory_manager()
    await get_dialogue_manager()
    logger.info("All services initialised successfully")


async def shutdown_all() -> None:
    """Clean up all service instances. Called during application shutdown."""
    logger.info("Shutting down all services...")
    store: MemoryStore | None = _instances.get("memory_store")
    if store is not None:
        await store.close()
    _instances.clear()
    logger.info("All services shut down")
