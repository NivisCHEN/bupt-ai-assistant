"""Memory compression module inspired by MemGPT/OpenClaw patterns.

Groups similar memories, merges them into concise summaries via LLM, and
archives low-importance entries to keep the active memory set lean.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import numpy as np

from src.models import MemoryEntry, MemoryType

logger = logging.getLogger(__name__)


class MemoryCompressor:
    """Compresses and curates memory entries using LLM summarisation."""

    def __init__(
        self,
        llm_client,
        embedding_service,
        importance_threshold: float = 0.3,
        similarity_threshold: float = 0.85,
    ) -> None:
        """Initialise the compressor.

        Args:
            llm_client: LLM client with a ``generate(prompt) -> str`` method.
            embedding_service: Service for computing text embeddings.
            importance_threshold: Memories below this score may be archived.
            similarity_threshold: Cosine similarity above which memories are
                considered duplicates and eligible for merging.
        """
        self.llm_client = llm_client
        self.embedding_service = embedding_service
        self.importance_threshold = importance_threshold
        self.similarity_threshold = similarity_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def compress_memories(
        self, memories: list[MemoryEntry]
    ) -> list[MemoryEntry]:
        """Group similar memories and merge each group into a summary.

        The LLM generates a concise summary for each group.  The merged
        entry retains the **highest** importance score and the **earliest**
        timestamp from the group.

        Args:
            memories: Flat list of MemoryEntry objects.

        Returns:
            A (potentially shorter) list of MemoryEntry objects after merging.
        """
        if len(memories) <= 1:
            return list(memories)

        groups = self._group_similar(memories)
        compressed: list[MemoryEntry] = []

        # Limit LLM calls to avoid exhausting API quota
        max_groups = 20
        if len(groups) > max_groups:
            logger.warning(
                "Too many groups (%d), only compressing first %d",
                len(groups), max_groups,
            )
            # Keep excess groups as-is (flatten their entries into compressed)
            for g in groups[max_groups:]:
                compressed.extend(g)
            groups = groups[:max_groups]

        for group in groups:
            if len(group) == 1:
                compressed.append(group[0])
                continue

            # Build a prompt for the LLM to summarise the group
            contents = "\n---\n".join(m.content for m in group)
            prompt = (
                "请将以下多条相关记忆合并为一条简洁的摘要，保留关键信息：\n\n"
                f"{contents}\n\n摘要："
            )
            try:
                summary = await self.llm_client.generate(prompt)
            except Exception:
                logger.warning("LLM summarisation failed; keeping first entry")
                summary = group[0].content

            best_importance = max(m.importance_score for m in group)
            earliest_timestamp = min(m.timestamp for m in group)

            # Re-embed the summary
            vector = self.embedding_service.encode([summary])[0].tolist()

            merged = MemoryEntry(
                id=str(uuid4()),
                type=group[0].type,
                content=summary,
                summary=summary[:120],
                timestamp=earliest_timestamp,
                importance_score=best_importance,
                vector=vector,
                user_id=group[0].user_id,
                metadata={"merged_from": [m.id for m in group]},
            )
            compressed.append(merged)

        logger.info(
            "Compressed %d memories into %d", len(memories), len(compressed)
        )
        return compressed

    def score_importance(
        self, memory: MemoryEntry, all_memories: list[MemoryEntry]
    ) -> float:
        """Automatically score a memory's importance.

        Scoring factors:
        - ``reference_count`` (from metadata): +0.1 per reference.
        - **Recency**: exponential decay based on hours since creation.
        - ``pinned`` flag in metadata: forces score to 1.0.
        - **Episodic** type receives a +0.2 boost.

        Args:
            memory: The entry to score.
            all_memories: The full set of memories (unused currently but
                available for relative scoring in future).

        Returns:
            A float score clamped to [0.0, 1.0].
        """
        # Pinned memories always get maximum importance
        if memory.metadata.get("pinned") is True:
            return 1.0

        score = 0.0

        # Reference count bonus
        ref_count = memory.metadata.get("reference_count", 0)
        score += 0.1 * ref_count

        # Recency via exponential decay
        now = datetime.now(tz=timezone.utc)
        hours_old = max((now - memory.timestamp).total_seconds() / 3600, 0.01)
        recency = float(np.exp(-0.005 * hours_old))
        score += recency * 0.5

        # Episodic boost
        if memory.type == MemoryType.EPISODIC:
            score += 0.2

        return max(0.0, min(1.0, score))

    def archive_low_importance(
        self,
        memories: list[MemoryEntry],
        threshold: Optional[float] = None,
    ) -> tuple[list[MemoryEntry], list[MemoryEntry]]:
        """Split memories into retained and archived based on importance.

        Args:
            memories: Full list of memories to evaluate.
            threshold: Importance threshold; defaults to
                ``self.importance_threshold``.

        Returns:
            A tuple ``(retained, archived)``.
        """
        if threshold is None:
            threshold = self.importance_threshold

        retained: list[MemoryEntry] = []
        archived: list[MemoryEntry] = []

        for mem in memories:
            if mem.importance_score < threshold:
                archived.append(mem)
            else:
                retained.append(mem)

        logger.info(
            "Archival split: %d retained, %d archived (threshold=%.2f)",
            len(retained),
            len(archived),
            threshold,
        )
        return retained, archived

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_similarity(
        self, vec_a: list[float], vec_b: list[float]
    ) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            vec_a: First vector.
            vec_b: Second vector.

        Returns:
            Cosine similarity as a float in [-1, 1].
        """
        a = np.array(vec_a, dtype=np.float64)
        b = np.array(vec_b, dtype=np.float64)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _group_similar(
        self, memories: list[MemoryEntry]
    ) -> list[list[MemoryEntry]]:
        """Group memories by pairwise cosine similarity.

        Memories without vectors are placed into individual singleton groups.
        A greedy approach is used: iterate through memories and assign each
        to the first group whose representative has similarity above the
        threshold.

        Args:
            memories: Memories to group.

        Returns:
            List of groups (each group is a list of MemoryEntry).
        """
        # Ensure all memories have vectors; encode those that lack one
        for mem in memories:
            if mem.vector is None:
                vec = self.embedding_service.encode([mem.content])[0].tolist()
                mem.vector = vec

        groups: list[list[MemoryEntry]] = []

        for mem in memories:
            placed = False
            for group in groups:
                representative = group[0]
                sim = self._compute_similarity(
                    representative.vector, mem.vector  # type: ignore[arg-type]
                )
                if sim >= self.similarity_threshold:
                    group.append(mem)
                    placed = True
                    break
            if not placed:
                groups.append([mem])

        return groups
