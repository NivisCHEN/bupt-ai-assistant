"""FastAPI dependency injection functions for the BUPT Campus AI Assistant.

Provides singleton-based dependency factories so that service instances are
created once and reused across request handlers.
"""

from __future__ import annotations

import os
from typing import Any

from loguru import logger

from src.dialogue.manager import DialogueManager
from src.dialogue.prompt_builder import PromptBuilder
from src.dialogue.router import IntentRouter
from src.embedding.service import EmbeddingService
from src.llm.client import LLMClient
from src.memory.compressor import MemoryCompressor
from src.memory.manager import MemoryManager
from src.memory.store import MemoryStore
from src.retriever.hybrid_retriever import HybridRetriever

# ---------------------------------------------------------------------------
# Settings helper
# ---------------------------------------------------------------------------


class Settings:
    """Lightweight application settings sourced from environment variables."""

    def __init__(self) -> None:
        self.llm_api_key: str = os.getenv("LLM_API_KEY", "")
        self.llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
        self.llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")
        self.embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
        self.embedding_device: str = os.getenv("EMBEDDING_DEVICE", "cpu")
        self.embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "1024"))
        self.session_timeout: int = int(os.getenv("SESSION_TIMEOUT", "1800"))


# ---------------------------------------------------------------------------
# Singleton registry
# ---------------------------------------------------------------------------

_instances: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Dependency providers
# ---------------------------------------------------------------------------


async def get_settings() -> Settings:
    """Return the application settings (singleton).

    Returns:
        The shared :class:`Settings` instance.
    """
    if "settings" not in _instances:
        _instances["settings"] = Settings()
    return _instances["settings"]


async def get_embedding_service() -> EmbeddingService:
    """Return the embedding service singleton.

    Returns:
        The shared :class:`EmbeddingService` instance.
    """
    if "embedding_service" not in _instances:
        settings = await get_settings()
        _instances["embedding_service"] = EmbeddingService(
            model_name=settings.embedding_model,
            device=settings.embedding_device,
            dimension=settings.embedding_dimension,
        )
        logger.info("EmbeddingService initialised")
    return _instances["embedding_service"]


async def get_llm_client() -> LLMClient:
    """Return the LLM client singleton.

    Returns:
        The shared :class:`LLMClient` instance.
    """
    if "llm_client" not in _instances:
        settings = await get_settings()
        _instances["llm_client"] = LLMClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
        logger.info("LLMClient initialised")
    return _instances["llm_client"]


async def get_memory_store() -> MemoryStore:
    """Return the memory store singleton.

    Returns:
        The shared :class:`MemoryStore` instance.
    """
    if "memory_store" not in _instances:
        embedding_service = await get_embedding_service()
        settings = await get_settings()
        _instances["memory_store"] = MemoryStore(
            embedding_service=embedding_service,
            faiss_dimension=settings.embedding_dimension,
        )
        logger.info("MemoryStore initialised")
    return _instances["memory_store"]


async def get_memory_manager() -> MemoryManager:
    """Return the memory manager singleton.

    Returns:
        The shared :class:`MemoryManager` instance.
    """
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
    """Return the dialogue manager singleton.

    Wires together all sub-components (router, retriever, memory, LLM,
    prompt builder) into a single :class:`DialogueManager`.

    Returns:
        The shared :class:`DialogueManager` instance.
    """
    if "dialogue_manager" not in _instances:
        llm_client = await get_llm_client()
        embedding_service = await get_embedding_service()
        memory_manager = await get_memory_manager()
        memory_store = await get_memory_store()

        router = IntentRouter(llm_client=llm_client)
        prompt_builder = PromptBuilder()
        retriever = HybridRetriever(
            embedding_service=embedding_service,
            faiss_store=memory_store.user_faiss_stores,
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
    """Initialise all services and load FAISS indices.

    Should be called once during application startup.
    """
    logger.info("Initialising all services...")
    await get_settings()
    await get_embedding_service()
    await get_llm_client()
    await get_memory_store()
    await get_memory_manager()
    await get_dialogue_manager()
    logger.info("All services initialised successfully")


async def shutdown_all() -> None:
    """Clean up all service instances.

    Should be called during application shutdown.
    """
    logger.info("Shutting down all services...")
    _instances.clear()
    logger.info("All services shut down")
