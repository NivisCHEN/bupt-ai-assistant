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
    """Orchestrates the full memory lifecycle across tiers.

    Acts as the primary facade that higher-level dialogue or API layers
    should interact with for all memory-related operations.
    """

    def __init__(
        self,
        store: MemoryStore,
        compressor: MemoryCompressor,
        embedding_service,
    ) -> None:
        """Initialise the memory manager.

        Args:
            store: The tiered MemoryStore instance.
            compressor: The MemoryCompressor for merging and archival.
            embedding_service: Service capable of encoding text into vectors
                (must expose ``encode(texts) -> np.ndarray`` and
                ``encode_query(query) -> np.ndarray``).
        """
        self.store = store
        self.compressor = compressor
        self.embedding_service = embedding_service

    # ------------------------------------------------------------------
    # Conversation recording
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Async wrappers (called by DialogueManager)
    # ------------------------------------------------------------------

    async def get_recent_history(
        self, user_id: str, limit: int = 10
    ) -> list[dict]:
        """Return recent conversation history formatted for prompt building.

        Args:
            user_id: Target user.
            limit: Maximum number of entries.

        Returns:
            List of dicts with ``role`` and ``content`` keys.
        """
        entries = self.store.get_recent_history(user_id, limit=limit)
        history: list[dict] = []
        for entry in entries:
            query = entry.metadata.get("query", "")
            response = entry.metadata.get("response", "")
            if query:
                history.append({"role": "user", "content": query})
            if response:
                history.append({"role": "assistant", "content": response})
        return history

    async def save_to_short_term(
        self, user_id: str, query: str, response: str
    ) -> None:
        """Save a conversation exchange to short-term memory.

        Thin async wrapper around :meth:`record_conversation`.
        """
        self.record_conversation(user_id, query, response)

    async def search_memories(
        self, user_id: str, query_vector, top_k: int = 5
    ) -> list[dict]:
        """Search user memories by vector similarity.

        Args:
            user_id: Target user.
            query_vector: The query embedding (numpy array or list).
            top_k: Maximum results.

        Returns:
            List of dicts with memory content and metadata.
        """
        if hasattr(query_vector, "tolist"):
            qv = query_vector[0].tolist() if query_vector.ndim > 1 else query_vector.tolist()
        else:
            qv = query_vector
        results = self.store.search_memory(user_id, qv, top_k=top_k)
        return [
            {
                "id": m.id,
                "content": m.content,
                "type": m.type.value,
                "importance": m.importance_score,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in results
        ]

    # ------------------------------------------------------------------
    # Conversation recording
    # ------------------------------------------------------------------

    def record_conversation(
        self, user_id: str, query: str, response: str
    ) -> None:
        """Record a conversation turn as short-term memory.

        Both the user query and the assistant response are stored as a
        single combined entry so that the full context is preserved.

        Args:
            user_id: The user who initiated the conversation.
            query: The user's query text.
            response: The assistant's response text.
        """
        content = f"User: {query}\nAssistant: {response}"
        self.store.save_short_term(
            user_id=user_id,
            content=content,
            metadata={"query": query, "response": response},
        )
        logger.debug("Recorded conversation for user %s", user_id)

    # ------------------------------------------------------------------
    # Promotion
    # ------------------------------------------------------------------

    def promote_to_long_term(
        self, user_id: str, memory_id: str
    ) -> MemoryEntry:
        """Promote a short-term memory to long-term storage.

        The memory is re-saved as a long-term entry with an embedding
        vector, and the original short-term entry is removed.

        Args:
            user_id: Owner of the memory.
            memory_id: ID of the short-term entry to promote.

        Returns:
            The newly created long-term MemoryEntry.

        Raises:
            ValueError: If the memory is not found or is not short-term.
        """
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

        # Create a long-term entry preserving the original content
        long_term_entry = self.store.save_long_term(
            user_id=user_id,
            content=target.content,
            importance=max(target.importance_score, 0.6),
            source_ref=f"promoted_from:{target.id}",
            metadata={**target.metadata, "promoted_from": target.id},
        )

        # Remove the original short-term entry
        self.store.delete_memory(user_id, memory_id)
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
        """Extract user preferences and patterns from conversation history.

        Uses the LLM (via the compressor's llm_client) to analyse the
        conversation history and produce a structured profile.

        Args:
            user_id: The target user.
            history: List of MemoryEntry objects representing past
                conversations.

        Returns:
            A dict with keys ``preferences``, ``frequent_topics``, and
            ``summary``.
        """
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
        """Run a full maintenance cycle on a user's memory.

        Steps:
        1. Score importance for all memories.
        2. Archive low-importance entries.
        3. Compress similar memories via LLM summarisation.
        4. Rebuild the FAISS index.

        Args:
            user_id: Target user.

        Returns:
            A stats dict with keys: ``total_before``, ``scored``,
            ``archived``, ``compressed``, ``total_after``.
        """
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
                self.store.update_importance(
                    user_id, mem.id, new_score - mem.importance_score
                )
            except ValueError:
                pass
        scored = len(all_memories)

        # Step 2: Archive low-importance memories
        refreshed = self.store.get_all_memories(user_id)
        retained, archived = self.compressor.archive_low_importance(refreshed)

        # Remove archived entries from the store
        for mem in archived:
            self.store.delete_memory(user_id, mem.id)

        # Step 3: Compress similar memories among the retained set
        compressed = await self.compressor.compress_memories(retained)
        compressed_count = len(retained) - len(compressed)

        # Replace retained memories with compressed versions in the store
        # Remove the old retained entries and insert the compressed ones
        current_ids = {m.id for m in self.store.get_all_memories(user_id)}
        retained_ids = {m.id for m in retained}
        # Only remove entries that were part of the retained set (they may
        # have been merged into new compressed entries)
        for mid in retained_ids:
            if mid in current_ids:
                self.store.delete_memory(user_id, mid)

        # Insert compressed entries back
        for mem in compressed:
            if mem.type == MemoryType.SHORT_TERM:
                self.store.save_short_term(
                    user_id, mem.content, metadata=mem.metadata
                )
            elif mem.type == MemoryType.LONG_TERM:
                self.store.save_long_term(
                    user_id,
                    mem.content,
                    importance=mem.importance_score,
                    source_ref=mem.source_ref,
                    metadata=mem.metadata,
                )
            elif mem.type == MemoryType.EPISODIC:
                event_type = mem.metadata.get("event_type", "unknown")
                self.store.save_episodic(
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
        """Retrieve contextually relevant memories using hierarchical search.

        Retrieval priority:
        1. Recent short-term memories (conversation history).
        2. High-importance long-term memories via vector search.
        3. Episodic memories (task events) via vector search.

        Results are merged and deduplicated by content similarity.

        Args:
            user_id: Target user.
            query: The current user query.
            top_k: Maximum number of memories to return.

        Returns:
            A deduplicated list of the most relevant MemoryEntry objects,
            up to *top_k* items.
        """
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

        # Deduplicate by content similarity (remove near-duplicates)
        deduplicated = self._deduplicate_by_similarity(unique)

        # Sort by importance descending, then by recency
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
        """Remove near-duplicate memories based on content similarity.

        Uses embedding vectors when available; falls back to keeping all
        entries if vectors are missing.

        Args:
            memories: List of candidate memories.
            threshold: Cosine similarity above which an entry is considered
                a duplicate and dropped.

        Returns:
            Deduplicated list of memories.
        """
        if len(memories) <= 1:
            return list(memories)

        # Ensure all entries have vectors for comparison
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
