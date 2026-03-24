from __future__ import annotations

import math
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class SimpleReranker:
    """Lightweight reranker that combines retrieval score, keyword overlap,
    and time-recency signals."""

    RETRIEVAL_WEIGHT = 0.4
    KEYWORD_WEIGHT = 0.3
    RECENCY_WEIGHT = 0.3

    def __init__(self, top_k: int = 5) -> None:
        self.top_k = top_k

    def rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Rerank candidate documents and return the top results.

        Scoring formula (per candidate):
            final_score = 0.4 * retrieval_score_norm
                        + 0.3 * keyword_overlap_ratio
                        + 0.3 * recency_score

        Args:
            query: The original query string.
            candidates: List of dicts, each with ``id``, ``content``,
                ``score`` (retrieval score), and ``metadata`` (may contain
                ``timestamp`` as ISO-8601 string or Unix epoch float/int).

        Returns:
            Reranked list of candidate dicts (up to *top_k*), with an
            updated ``score`` field reflecting the combined score.
        """
        if not candidates:
            return []

        if not query:
            return candidates[: self.top_k]

        query_tokens = set(query.lower().split())

        # Normalise retrieval scores to [0, 1]
        max_score = max((c.get("score", 0.0) for c in candidates), default=1.0)
        if max_score == 0:
            max_score = 1.0

        scored: list[tuple[float, dict[str, Any]]] = []
        for candidate in candidates:
            retrieval_norm = candidate.get("score", 0.0) / max_score
            keyword_ratio = self._keyword_overlap(query_tokens, candidate.get("content", ""))
            recency = self._recency_score(candidate.get("metadata", {}))

            final_score = (
                self.RETRIEVAL_WEIGHT * retrieval_norm
                + self.KEYWORD_WEIGHT * keyword_ratio
                + self.RECENCY_WEIGHT * recency
            )
            result = {**candidate, "score": final_score}
            scored.append((final_score, result))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[: self.top_k]]

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _keyword_overlap(query_tokens: set[str], content: str) -> float:
        """Return the fraction of query tokens found in *content*."""
        if not query_tokens or not content:
            return 0.0
        content_lower = content.lower()
        matches = sum(1 for token in query_tokens if token in content_lower)
        return matches / len(query_tokens)

    @staticmethod
    def _recency_score(metadata: dict[str, Any]) -> float:
        """Compute an exponential-decay recency score based on ``timestamp``.

        Returns 1.0 for very recent documents, decaying towards 0 as the
        document ages.  If no timestamp is available, returns 0.5 (neutral).

        Decay formula:  exp(-0.05 * days_old)
        """
        timestamp = metadata.get("timestamp")
        if timestamp is None:
            return 0.5

        try:
            if isinstance(timestamp, str):
                dt = datetime.fromisoformat(timestamp)
            elif isinstance(timestamp, (int, float)):
                dt = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
            else:
                return 0.5

            # Ensure timezone-aware comparison
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            days_old = max((now - dt).total_seconds() / 86400, 0.0)
            return math.exp(-0.05 * days_old)
        except (ValueError, TypeError, OSError):
            return 0.5
