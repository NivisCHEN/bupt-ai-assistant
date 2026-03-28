"""Memory manager orchestrating the full memory lifecycle.

Coordinates the MemoryStore and MemoryCompressor to provide a high-level
API for recording conversations, promoting memories, extracting user
profiles, running maintenance, and retrieving contextually relevant memories.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from src.models import MemoryEntry, MemoryType
from src.memory.store import MemoryStore
from src.memory.compressor import MemoryCompressor

logger = logging.getLogger(__name__)


class MemoryManager:
    """Orchestrates the full memory lifecycle across tiers."""

    def __init__(
        self,
        store: MemoryStore,
        compressor: MemoryCompressor,
        embedding_service,
    ) -> None:
        self.store = store
        self.compressor = compressor
        self.embedding_service = embedding_service

    # ------------------------------------------------------------------
    # Conversation recording
    # ------------------------------------------------------------------

    async def record_conversation(

        self, user_id: str, query: str, response: str
    ) -> None:
        """Record a conversation turn as short-term memory."""
        content = f"User: {query}\nAssistant: {response}"
        await self.store.save_short_term(
            user_id=user_id,
            content=content,
            metadata={"query": query, "response": response},
        )
        logger.debug("Recorded conversation for user %s", user_id)

    # ------------------------------------------------------------------
    # Promotion
    # ------------------------------------------------------------------

    async def promote_to_long_term(
        self, user_id: str, memory_id: str
    ) -> MemoryEntry:
        """Promote a short-term memory to long-term storage."""
        memories = self.store.get_all_memories(user_id, MemoryType.SHORT_TERM)
        target: Optional[MemoryEntry] = None
        for mem in memories:
            if mem.id == memory_id:
                target = mem
                break

        if target is None:
            raise ValueError(
                f"Short-term memory {memory_id} not found for user {user_id}"
            )

        long_term_entry = await self.store.save_long_term(
            user_id=user_id,
            content=target.content,
            importance=max(target.importance_score, 0.6),
            source_ref=f"promoted_from:{target.id}",
            metadata={**target.metadata, "promoted_from": target.id},
        )

        await self.store.delete_memory(user_id, memory_id)
        logger.info(
            "Promoted memory %s -> %s for user %s",
            memory_id,
            long_term_entry.id,
            user_id,
        )
        return long_term_entry

    # ------------------------------------------------------------------
    # Profile extraction
    # ------------------------------------------------------------------

    async def extract_user_profile(
        self, user_id: str, history: list[MemoryEntry]
    ) -> dict:
        """Extract user preferences and patterns from conversation history."""
        if not history:
            return {"preferences": {}, "frequent_topics": [], "summary": ""}

        history_text = "\n\n".join(
            f"[{entry.timestamp.isoformat()}] {entry.content}"
            for entry in sorted(history, key=lambda e: e.timestamp)
        )

        prompt = (
            "根据以下用户的对话历史，提取用户偏好、经常讨论的话题和用户画像摘要。\n"
            "请以JSON格式返回，包含以下字段：\n"
            '- "preferences": 用户偏好（dict）\n'
            '- "frequent_topics": 用户经常讨论的话题（list）\n'
            '- "summary": 用户画像摘要（string）\n\n'
            f"对话历史：\n{history_text}\n\n"
            "请严格返回JSON，不要包含其他文字。"
        )

        try:
            raw = await self.compressor.llm_client.generate(prompt)
            import json
            raw = (
                raw.strip()
                .removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )
            profile = json.loads(raw)
            return {
                "preferences": profile.get("preferences", {}),
                "frequent_topics": profile.get("frequent_topics", []),
                "summary": profile.get("summary", ""),
            }
        except Exception:
            logger.warning(
                "Failed to extract user profile for %s; returning empty profile",
                user_id,
            )
            return {"preferences": {}, "frequent_topics": [], "summary": ""}

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    async def run_maintenance(self, user_id: str) -> dict:
        """Run a full maintenance cycle on a user's memory."""
        all_memories = self.store.get_all_memories(user_id)
        total_before = len(all_memories)

        if total_before == 0:
            return {
                "total_before": 0,
                "scored": 0,
                "archived": 0,
                "compressed": 0,
                "total_after": 0,
            }

        # Step 1: Score importance for every memory
        for mem in all_memories:
            new_score = self.compressor.score_importance(mem, all_memories)
            try:
                await self.store.update_importance(
                    user_id, mem.id, new_score - mem.importance_score
                )
            except ValueError:
                pass
        scored = len(all_memories)

        # Step 2: Archive low-importance memories
        refreshed = self.store.get_all_memories(user_id)
        retained, archived = self.compressor.archive_low_importance(refreshed)

        for mem in archived:
            await self.store.delete_memory(user_id, mem.id)

        # Step 3: Compress similar memories among the retained set
        compressed = await self.compressor.compress_memories(retained)
        compressed_count = len(retained) - len(compressed)

        current_ids = {m.id for m in self.store.get_all_memories(user_id)}
        retained_ids = {m.id for m in retained}
        for mid in retained_ids:
            if mid in current_ids:
                await self.store.delete_memory(user_id, mid)

        # Insert compressed entries back
        for mem in compressed:
            if mem.type == MemoryType.SHORT_TERM:
                await self.store.save_short_term(
                    user_id, mem.content, metadata=mem.metadata
                )
            elif mem.type == MemoryType.LONG_TERM:
                await self.store.save_long_term(
                    user_id,
                    mem.content,
                    importance=mem.importance_score,
                    source_ref=mem.source_ref,
                    metadata=mem.metadata,
                )
            elif mem.type == MemoryType.EPISODIC:
                event_type = mem.metadata.get("event_type", "unknown")
                await self.store.save_episodic(
                    user_id, mem.content, event_type, metadata=mem.metadata
                )

        # Step 4: Rebuild FAISS index
        self.store._build_user_index(user_id)

        total_after = len(self.store.get_all_memories(user_id))

        stats = {
            "total_before": total_before,
            "scored": scored,
            "archived": len(archived),
            "compressed": max(compressed_count, 0),
            "total_after": total_after,
        }
        logger.info("Maintenance complete for user %s: %s", user_id, stats)
        return stats

    # ------------------------------------------------------------------
    # Context retrieval
    # ------------------------------------------------------------------

    def retrieve_context(
        self, user_id: str, query: str, top_k: int = 5
    ) -> list[MemoryEntry]:
        """Retrieve contextually relevant memories using hierarchical search."""
        results: list[MemoryEntry] = []

        # 1. Recent short-term memories
        short_term = self.store.get_recent_history(user_id, limit=top_k)
        results.extend(short_term)

        # 2 & 3. Vector-based retrieval for long-term and episodic
        query_vector = self.embedding_service.encode_query(query)
        if query_vector.size > 0:
            qv = query_vector[0].tolist() if query_vector.ndim > 1 else query_vector.tolist()

            long_term_results = self.store.search_memory(
                user_id, qv, top_k=top_k,
                memory_types=[MemoryType.LONG_TERM],
            )
            results.extend(long_term_results)

            episodic_results = self.store.search_memory(
                user_id, qv, top_k=top_k,
                memory_types=[MemoryType.EPISODIC],
            )
            results.extend(episodic_results)

        # Deduplicate by id first
        seen_ids: set[str] = set()
        unique: list[MemoryEntry] = []
        for mem in results:
            if mem.id not in seen_ids:
                seen_ids.add(mem.id)
                unique.append(mem)

        deduplicated = self._deduplicate_by_similarity(unique)

        deduplicated.sort(
            key=lambda m: (m.importance_score, m.timestamp),
            reverse=True,
        )
        return deduplicated[:top_k]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _deduplicate_by_similarity(
        self, memories: list[MemoryEntry], threshold: float = 0.9
    ) -> list[MemoryEntry]:
        """Remove near-duplicate memories based on content similarity."""
        if len(memories) <= 1:
            return list(memories)

        for mem in memories:
            if mem.vector is None:
                try:
                    vec = self.embedding_service.encode([mem.content])[0].tolist()
                    mem.vector = vec
                except Exception:
                    pass

        kept: list[MemoryEntry] = []
        for mem in memories:
            is_duplicate = False
            if mem.vector is not None:
                for existing in kept:
                    if existing.vector is not None:
                        sim = self.compressor._compute_similarity(
                            mem.vector, existing.vector
                        )
                        if sim >= threshold:
                            is_duplicate = True
                            break
            if not is_duplicate:
                kept.append(mem)

        return kept
