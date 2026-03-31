from __future__ import annotations

import logging
import threading
from typing import Any

import jieba
import numpy as np
from rank_bm25 import BM25Okapi

from src.embedding.service import EmbeddingService
from src.retriever.faiss_store import FAISSStore

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Hybrid retriever combining dense (FAISS) and sparse (BM25) search
    with reciprocal rank fusion for merging results."""

    def __init__(
        self,
        faiss_store: FAISSStore,
        embedding_service: EmbeddingService,
        bm25_weight: float = 0.3,
        dense_weight: float = 0.7,
    ) -> None:
        self.faiss_store = faiss_store
        self.embedding_service = embedding_service
        self.bm25_weight = bm25_weight
        self.dense_weight = dense_weight

        self._lock = threading.Lock()
        self._bm25: BM25Okapi | None = None
        self._tokenized_corpus: list[list[str]] = []
        self._documents: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Index building
    # ------------------------------------------------------------------

    def build_bm25_index(self, documents: list[dict[str, Any]]) -> None:
        """Build BM25 index from a list of document dicts.

        Each document dict is expected to contain at least a ``content`` key.
        Documents are stored internally so that search indices can be mapped
        back to their content and metadata.

        Args:
            documents: List of dicts with ``content`` (str) and optional
                ``id``, ``metadata`` fields.
        """
        with self._lock:
            if not documents:
                self._bm25 = None
                self._tokenized_corpus = []
                self._documents = []
                return

            self._documents = documents
            self._tokenized_corpus = [
                list(jieba.lcut(doc.get("content", ""))) for doc in documents
            ]
            self._bm25 = BM25Okapi(self._tokenized_corpus)
            logger.info("BM25 index built with %d documents", len(documents))

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Retrieve documents using hybrid (dense + sparse) search.

        Args:
            query: The search query string.
            top_k: Number of results to return.

        Returns:
            List of result dicts, each containing ``id``, ``score``,
            ``content``, and ``metadata``.
        """
        if not query or not self._documents:
            return []

        dense_results = self._dense_search(query, top_k)
        sparse_results = self._sparse_search(query, top_k)
        merged = self._merge_results(dense_results, sparse_results, top_k)

        results: list[dict[str, Any]] = []
        for idx, score in merged:
            if 0 <= idx < len(self._documents):
                doc = self._documents[idx]
                results.append(
                    {
                        "id": doc.get("id", idx),
                        "score": float(score),
                        "content": doc.get("content", ""),
                        "metadata": doc.get("metadata", {}),
                    }
                )
        return results

    # ------------------------------------------------------------------
    # Internal search methods
    # ------------------------------------------------------------------

    def _dense_search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        """Perform dense retrieval via FAISS.

        Returns:
            List of (index, score) tuples sorted by descending score.
        """
        if self.faiss_store.size == 0:
            return []

        query_vec = self.embedding_service.encode_query(query)
        if query_vec.size == 0:
            return []

        distances, indices = self.faiss_store.search(query_vec, top_k)
        results: list[tuple[int, float]] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            results.append((int(idx), float(dist)))
        return results

    def _sparse_search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        """Perform sparse retrieval via BM25.

        Returns:
            List of (index, score) tuples sorted by descending score.
        """
        if self._bm25 is None or not self._tokenized_corpus:
            return []

        query_tokens = list(jieba.lcut(query))
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(int(i), float(scores[i])) for i in top_indices if scores[i] > 0]

    # ------------------------------------------------------------------
    # Fusion
    # ------------------------------------------------------------------

    def _merge_results(
        self,
        dense_results: list[tuple[int, float]],
        sparse_results: list[tuple[int, float]],
        top_k: int,
    ) -> list[tuple[int, float]]:
        """Merge dense and sparse results using reciprocal rank fusion (RRF).

        RRF score for document *d*:  sum over rankings of  1 / (k + rank)
        where k = 60 (constant).

        Args:
            dense_results: Results from dense search.
            sparse_results: Results from sparse search.
            top_k: Number of merged results to return.

        Returns:
            List of (index, fused_score) tuples sorted by descending score.
        """
        k = 60  # RRF constant
        fused_scores: dict[int, float] = {}

        for rank, (idx, _score) in enumerate(dense_results):
            fused_scores[idx] = fused_scores.get(idx, 0.0) + self.dense_weight / (k + rank + 1)

        for rank, (idx, _score) in enumerate(sparse_results):
            fused_scores[idx] = fused_scores.get(idx, 0.0) + self.bm25_weight / (k + rank + 1)

        sorted_results = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:top_k]
