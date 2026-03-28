"""Tiered memory store with SQLite persistence.

Manages short-term, long-term, and episodic memory with per-user FAISS
indices for fast vector retrieval.  All memory entries are persisted to
a SQLite database so that data survives process restarts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

import aiosqlite
import numpy as np

from src.models import MemoryEntry, MemoryType
from src.retriever.faiss_store import FAISSStore

logger = logging.getLogger(__name__)

# Default database path — can be overridden via constructor argument.
_DEFAULT_DB_PATH = os.getenv("MEMORY_DB_PATH", "data/memories.db")

# SQL executed once at startup to guarantee the schema exists.
_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    summary TEXT,
    importance_score REAL,
    vector BLOB,
    metadata TEXT,
    timestamp TEXT,
    source_ref TEXT
);
CREATE INDEX IF NOT EXISTS idx_memories_user_id
    ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_user_type
    ON memories(user_id, type);
"""


def _serialize_vector(vector: list[float] | None) -> bytes | None:
    if vector is None:
        return None
    return np.array(vector, dtype=np.float32).tobytes()


def _deserialize_vector(blob: bytes | None) -> list[float] | None:
    if blob is None:
        return None
    return np.frombuffer(blob, dtype=np.float32).tolist()


def _row_to_entry(row: aiosqlite.Row) -> MemoryEntry:
    """Convert a database row into a MemoryEntry."""
    return MemoryEntry(
        id=row[0],
        user_id=row[1],
        type=MemoryType(row[2]),
        content=row[3],
        summary=row[4] or "",
        importance_score=row[5] or 0.0,
        vector=_deserialize_vector(row[6]),
        metadata=json.loads(row[7]) if row[7] else {},
        timestamp=datetime.fromisoformat(row[8]) if row[8] else datetime.utcnow(),
        source_ref=row[9],
    )


class MemoryStore:
    """Central store managing all memory tiers with SQLite + per-user FAISS."""

    def __init__(
        self,
        embedding_service,
        faiss_dimension: int = 1024,
        db_path: str | None = None,
    ) -> None:
        self.embedding_service = embedding_service
        self.faiss_dimension = faiss_dimension
        self.db_path = db_path or _DEFAULT_DB_PATH

        # Per-user FAISS stores for vector retrieval
        self.user_faiss_stores: dict[str, FAISSStore] = {}

        # Explicit FAISS-row -> memory-id mapping per user
        self._index_id_map: dict[str, list[str]] = {}

        # In-memory cache for fast reads (populated from DB on init)
        self._memories: dict[str, list[MemoryEntry]] = {}

        # FAISS index persistence directory
        self._index_dir = os.getenv("FAISS_INDEX_DIR", "data/indices")

        # Persistent DB connection (opened in initialize, closed in close)
        self._db: aiosqlite.Connection | None = None

        # Serialise all writes to avoid SQLite "database is locked" errors
        self._write_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Open the database, create schema, and load existing data."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        # WAL mode allows concurrent reads while writes are in progress
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.executescript(_SCHEMA_SQL)
        await self._db.commit()

        await self._load_all_from_db()
        self._rebuild_all_indices()
        logger.info(
            "MemoryStore initialised (db=%s, users=%d)",
            self.db_path,
            len(self._memories),
        )

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None
            logger.info("MemoryStore database connection closed")

    async def _load_all_from_db(self) -> None:
        """Populate the in-memory cache from the database."""
        assert self._db is not None
        self._memories.clear()
        cursor = await self._db.execute(
            "SELECT id, user_id, type, content, summary, importance_score, "
            "vector, metadata, timestamp, source_ref FROM memories "
            "ORDER BY timestamp ASC"
        )
        rows = await cursor.fetchall()
        for row in rows:
            entry = _row_to_entry(row)
            self._memories.setdefault(entry.user_id, []).append(entry)

    def _rebuild_all_indices(self) -> None:
        """Rebuild FAISS indices for every user currently in cache."""
        for user_id in list(self._memories.keys()):
            self._build_user_index(user_id)

    # ------------------------------------------------------------------
    # DB helpers — all writes serialised via _write_lock
    # ------------------------------------------------------------------

    async def _insert_entry(self, entry: MemoryEntry) -> None:
        assert self._db is not None
        async with self._write_lock:
            await self._db.execute(
                "INSERT INTO memories "
                "(id, user_id, type, content, summary, importance_score, "
                "vector, metadata, timestamp, source_ref) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.id,
                    entry.user_id,
                    entry.type.value,
                    entry.content,
                    entry.summary,
                    entry.importance_score,
                    _serialize_vector(entry.vector),
                    json.dumps(entry.metadata, ensure_ascii=False),
                    entry.timestamp.isoformat(),
                    entry.source_ref,
                ),
            )
            await self._db.commit()

    async def _delete_entry_db(self, memory_id: str) -> None:
        assert self._db is not None
        async with self._write_lock:
            await self._db.execute(
                "DELETE FROM memories WHERE id = ?", (memory_id,)
            )
            await self._db.commit()

    async def _update_importance_db(
        self, memory_id: str, new_score: float
    ) -> None:
        assert self._db is not None
        async with self._write_lock:
            await self._db.execute(
                "UPDATE memories SET importance_score = ? WHERE id = ?",
                (new_score, memory_id),
            )
            await self._db.commit()

    # ------------------------------------------------------------------
    # Save helpers
    # ------------------------------------------------------------------

    async def save_short_term(
        self,
        user_id: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> MemoryEntry:
        """Save a short-term memory entry (persisted to SQLite)."""
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
        self._memories.setdefault(user_id, []).append(entry)
        await self._insert_entry(entry)
        logger.debug("Saved short-term memory %s for user %s", entry.id, user_id)
        return entry

    async def save_long_term(
        self,
        user_id: str,
        content: str,
        importance: float,
        source_ref: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> MemoryEntry:
        """Save a long-term memory entry with an embedding vector."""
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
        self._memories.setdefault(user_id, []).append(entry)
        await self._insert_entry(entry)
        self._build_user_index(user_id)
        self._persist_user_index(user_id)
        logger.debug("Saved long-term memory %s for user %s", entry.id, user_id)
        return entry

    async def save_episodic(
        self,
        user_id: str,
        content: str,
        event_type: str,
        metadata: Optional[dict] = None,
    ) -> MemoryEntry:
        """Save an episodic memory entry for task events."""
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
        self._memories.setdefault(user_id, []).append(entry)
        await self._insert_entry(entry)
        self._build_user_index(user_id)
        self._persist_user_index(user_id)
        logger.debug("Saved episodic memory %s for user %s", entry.id, user_id)
        return entry

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_recent_history(
        self, user_id: str, limit: int = 10
    ) -> list[MemoryEntry]:
        """Return the most recent short-term entries for *user_id*."""
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

        Uses the explicit index-ID mapping to guarantee correct alignment
        between FAISS row indices and memory entries.
        """
        faiss_store = self.user_faiss_stores.get(user_id)
        if faiss_store is None or faiss_store.size == 0:
            return []

        qv = np.array(query_vector, dtype=np.float32)
        distances, indices = faiss_store.search(qv, top_k=top_k * 3)

        id_map = self._index_id_map.get(user_id, [])
        memory_by_id: dict[str, MemoryEntry] = {
            m.id: m for m in self._memories.get(user_id, [])
        }

        now = datetime.utcnow()
        results: list[tuple[float, MemoryEntry]] = []
        for idx in indices[0]:
            if idx < 0 or idx >= len(id_map):
                continue
            memory_id = id_map[int(idx)]
            entry = memory_by_id.get(memory_id)
            if entry is None:
                continue
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
        """Return all memories for a user, optionally filtered by type."""
        memories = self._memories.get(user_id, [])
        if memory_type is not None:
            memories = [m for m in memories if m.type == memory_type]
        return list(memories)

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    async def delete_memory(self, user_id: str, memory_id: str) -> bool:
        """Delete a specific memory by id (from both cache and database)."""
        entries = self._memories.get(user_id, [])
        for i, entry in enumerate(entries):
            if entry.id == memory_id:
                entries.pop(i)
                await self._delete_entry_db(memory_id)
                self._build_user_index(user_id)
                self._persist_user_index(user_id)
                logger.debug("Deleted memory %s for user %s", memory_id, user_id)
                return True
        return False

    async def update_importance(
        self, user_id: str, memory_id: str, delta: float
    ) -> MemoryEntry:
        """Adjust the importance score of a memory (persisted)."""
        for entry in self._memories.get(user_id, []):
            if entry.id == memory_id:
                new_score = max(0.0, min(1.0, entry.importance_score + delta))
                entry.importance_score = new_score
                await self._update_importance_db(memory_id, new_score)
                return entry
        raise ValueError(f"Memory {memory_id} not found for user {user_id}")

    # ------------------------------------------------------------------
    # Internal — FAISS index management
    # ------------------------------------------------------------------

    def _build_user_index(self, user_id: str) -> None:
        """Rebuild the FAISS index for a user with explicit ID mapping."""
        vectored = [
            m for m in self._memories.get(user_id, []) if m.vector is not None
        ]
        store = FAISSStore(dimension=self.faiss_dimension)
        self._index_id_map[user_id] = [m.id for m in vectored]
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

    def _persist_user_index(self, user_id: str) -> None:
        """Save a user's FAISS index to disk."""
        store = self.user_faiss_stores.get(user_id)
        if store is None or store.size == 0:
            return
        path = os.path.join(self._index_dir, f"user_{user_id}.index")
        try:
            store.save_index(path)
        except Exception:
            logger.warning(
                "Failed to persist FAISS index for user %s", user_id, exc_info=True
            )

    def _load_user_index(self, user_id: str) -> bool:
        """Attempt to load a user's FAISS index from disk."""
        path = os.path.join(self._index_dir, f"user_{user_id}.index")
        if not os.path.exists(path):
            return False
        try:
            store = FAISSStore(dimension=self.faiss_dimension)
            store.load_index(path)
            self.user_faiss_stores[user_id] = store
            return True
        except Exception:
            logger.warning(
                "Failed to load FAISS index for user %s", user_id, exc_info=True
            )
            return False
