"""Tiered memory store inspired by MemGPT/OpenClaw patterns.

Manages short-term, long-term, and episodic memory with per-user FAISS
indices for fast vector retrieval.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional
from uuid import uuid4

import numpy as np

from src.models import MemoryEntry, MemoryType
from src.retriever.faiss_store import FAISSStore

logger = logging.getLogger(__name__)


class MemoryStore:
    """Central store managing all memory tiers with per-user FAISS indices."""

    def __init__(self, embedding_service, faiss_dimension: int = 1024) -> None:
        """Initialise the memory store.

        Args:
            embedding_service: Service capable of encoding text into vectors.
            faiss_dimension: Dimensionality of the embedding vectors.
        """
        self.embedding_service = embedding_service
        self.faiss_dimension = faiss_dimension

        # Structured storage: user_id -> list of MemoryEntry
        self._memories: dict[str, list[MemoryEntry]] = defaultdict(list)

        # Per-user FAISS stores for vector retrieval
        self.user_faiss_stores: dict[str, FAISSStore] = {}

    # ------------------------------------------------------------------
    # Save helpers
    # ------------------------------------------------------------------

    def save_short_term(
        self,
        user_id: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> MemoryEntry:
        """Save a short-term memory entry.

        Args:
            user_id: Owner of the memory.
            content: Raw text content to remember.
            metadata: Optional extra metadata.

        Returns:
            The newly created MemoryEntry.
        """
        entry = MemoryEntry(
            id=str(uuid4()),
            type=MemoryType.SHORT_TERM,
            content=content,
            summary=content[:120],
            timestamp=datetime.utcnow(),
            importance_score=0.5,
            user_id=user_id,
            metadata=metadata or {},
        )
        self._memories[user_id].append(entry)
        logger.debug("Saved short-term memory %s for user %s", entry.id, user_id)
        return entry

    def save_long_term(
        self,
        user_id: str,
        content: str,
        importance: float,
        source_ref: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> MemoryEntry:
        """Save a long-term memory entry with an embedding vector.

        Args:
            user_id: Owner of the memory.
            content: Text content.
            importance: Importance score in [0, 1].
            source_ref: Optional reference to original source.
            metadata: Optional extra metadata.

        Returns:
            The newly created MemoryEntry.
        """
        vector = self.embedding_service.encode([content])[0].tolist()
        entry = MemoryEntry(
            id=str(uuid4()),
            type=MemoryType.LONG_TERM,
            content=content,
            summary=content[:120],
            timestamp=datetime.utcnow(),
            importance_score=max(0.0, min(1.0, importance)),
            source_ref=source_ref,
            vector=vector,
            user_id=user_id,
            metadata=metadata or {},
        )
        self._memories[user_id].append(entry)
        self._build_user_index(user_id)
        logger.debug("Saved long-term memory %s for user %s", entry.id, user_id)
        return entry

    def save_episodic(
        self,
        user_id: str,
        content: str,
        event_type: str,
        metadata: Optional[dict] = None,
    ) -> MemoryEntry:
        """Save an episodic memory entry for task events.

        Args:
            user_id: Owner of the memory.
            content: Description of the event.
            event_type: Category such as 'repair_ticket' or 'appointment'.
            metadata: Optional extra metadata.

        Returns:
            The newly created MemoryEntry.
        """
        meta = metadata.copy() if metadata else {}
        meta["event_type"] = event_type
        vector = self.embedding_service.encode([content])[0].tolist()
        entry = MemoryEntry(
            id=str(uuid4()),
            type=MemoryType.EPISODIC,
            content=content,
            summary=content[:120],
            timestamp=datetime.utcnow(),
            importance_score=0.8,
            vector=vector,
            user_id=user_id,
            metadata=meta,
        )
        self._memories[user_id].append(entry)
        self._build_user_index(user_id)
        logger.debug("Saved episodic memory %s for user %s", entry.id, user_id)
        return entry

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_recent_history(
        self, user_id: str, limit: int = 10
    ) -> list[MemoryEntry]:
        """Return the most recent short-term entries for *user_id*.

        Args:
            user_id: Target user.
            limit: Maximum number of entries to return.

        Returns:
            List of MemoryEntry sorted newest-first.
        """
        short_term = [
            m
            for m in self._memories.get(user_id, [])
            if m.type == MemoryType.SHORT_TERM
        ]
        short_term.sort(key=lambda m: m.timestamp, reverse=True)
        return short_term[:limit]

    def search_memory(
        self,
        user_id: str,
        query_vector: list[float],
        top_k: int = 5,
        memory_types: Optional[list[MemoryType]] = None,
    ) -> list[MemoryEntry]:
        """Search a user's FAISS index for relevant memories.

        Results are ranked by ``importance_score * recency_weight`` where
        recency is based on an exponential decay over hours since creation.

        Args:
            user_id: Target user.
            query_vector: Query embedding.
            top_k: Maximum results.
            memory_types: Optional filter on memory type.

        Returns:
            Sorted list of matching MemoryEntry objects.
        """
        faiss_store = self.user_faiss_stores.get(user_id)
        if faiss_store is None or faiss_store.size == 0:
            return []

        qv = np.array(query_vector, dtype=np.float32)
        distances, indices = faiss_store.search(qv, top_k=top_k * 3)

        # Collect entries that have vectors (they correspond to FAISS rows)
        vectored = [
            m for m in self._memories.get(user_id, []) if m.vector is not None
        ]

        now = datetime.utcnow()
        results: list[tuple[float, MemoryEntry]] = []
        for idx in indices[0]:
            if idx < 0 or idx >= len(vectored):
                continue
            entry = vectored[int(idx)]
            if memory_types and entry.type not in memory_types:
                continue
            hours_old = max((now - entry.timestamp).total_seconds() / 3600, 0.01)
            recency = np.exp(-0.01 * hours_old)
            score = entry.importance_score * recency
            results.append((score, entry))

        results.sort(key=lambda t: t[0], reverse=True)
        return [entry for _, entry in results[:top_k]]

    def get_all_memories(
        self, user_id: str, memory_type: Optional[MemoryType] = None
    ) -> list[MemoryEntry]:
        """Return all memories for a user, optionally filtered by type.

        Args:
            user_id: Target user.
            memory_type: Optional type filter.

        Returns:
            List of MemoryEntry.
        """
        memories = self._memories.get(user_id, [])
        if memory_type is not None:
            memories = [m for m in memories if m.type == memory_type]
        return list(memories)

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def delete_memory(self, user_id: str, memory_id: str) -> bool:
        """Delete a specific memory by id.

        Args:
            user_id: Owner of the memory.
            memory_id: ID of the entry to remove.

        Returns:
            True if an entry was deleted, False otherwise.
        """
        entries = self._memories.get(user_id, [])
        for i, entry in enumerate(entries):
            if entry.id == memory_id:
                entries.pop(i)
                self._build_user_index(user_id)
                logger.debug("Deleted memory %s for user %s", memory_id, user_id)
                return True
        return False

    def update_importance(
        self, user_id: str, memory_id: str, delta: float
    ) -> MemoryEntry:
        """Adjust the importance score of a memory.

        The resulting score is clamped to [0, 1].

        Args:
            user_id: Owner of the memory.
            memory_id: ID of the entry to update.
            delta: Value to add (can be negative).

        Returns:
            The updated MemoryEntry.

        Raises:
            ValueError: If the memory is not found.
        """
        for entry in self._memories.get(user_id, []):
            if entry.id == memory_id:
                new_score = max(0.0, min(1.0, entry.importance_score + delta))
                entry.importance_score = new_score
                return entry
        raise ValueError(f"Memory {memory_id} not found for user {user_id}")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_user_index(self, user_id: str) -> None:
        """Rebuild the FAISS index for a user from all vectored memories.

        Args:
            user_id: Target user whose index should be rebuilt.
        """
        vectored = [
            m for m in self._memories.get(user_id, []) if m.vector is not None
        ]
        store = FAISSStore(dimension=self.faiss_dimension)
        if vectored:
            matrix = np.array(
                [m.vector for m in vectored], dtype=np.float32
            )
            store.build_index(matrix, use_ivf=False)
        else:
            store.build_index(np.empty((0, self.faiss_dimension), dtype=np.float32))
        self.user_faiss_stores[user_id] = store
        logger.debug(
            "Rebuilt FAISS index for user %s (%d vectors)", user_id, len(vectored)
        )
