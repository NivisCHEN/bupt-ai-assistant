from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Embedding service using SentenceTransformer models (default: bge-small-zh-v1.5)."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        device: str = "cpu",
        dimension: int = 512,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.dimension = dimension
        self._model: Optional[object] = None

    def _load_model(self) -> None:
        """Lazily load the SentenceTransformer model."""
        if self._model is not None:
            return

        # Silence verbose output from transformers / huggingface_hub before
        # importing anything that would read these env vars on first use.
        import os

        os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        try:
            from transformers.utils import logging as hf_logging

            hf_logging.set_verbosity_error()
        except Exception:  # pragma: no cover - best-effort silencing
            pass

        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model %s on %s ...", self.model_name, self.device)
        self._model = SentenceTransformer(self.model_name, device=self.device)

        # Prefer the new API (``get_embedding_dimension``); fall back to the
        # deprecated one for older sentence-transformers versions.
        get_dim = getattr(
            self._model,
            "get_embedding_dimension",
            self._model.get_sentence_embedding_dimension,
        )
        actual_dim = get_dim()
        if actual_dim and actual_dim != self.dimension:
            logger.warning(
                "Configured dim=%d but model produces dim=%d, auto-correcting",
                self.dimension, actual_dim,
            )
            self.dimension = actual_dim
        logger.info("Embedding model loaded (dim=%d).", self.dimension)

    def encode(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        """Encode a list of texts into normalized embeddings.

        Args:
            texts: List of strings to encode.
            batch_size: Batch size for encoding.

        Returns:
            np.ndarray of shape (len(texts), dimension) with L2-normalized vectors.
        """
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        self._load_model()
        embeddings: np.ndarray = self._model.encode(  # type: ignore[union-attr]
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return embeddings.astype(np.float32)

    def encode_query(self, query: str) -> np.ndarray:
        """Encode a single query with the BGE-M3 retrieval prefix.

        Args:
            query: The query string.

        Returns:
            np.ndarray of shape (1, dimension) with the L2-normalized query vector.
        """
        if not query:
            return np.empty((0, self.dimension), dtype=np.float32)

        prefixed = f"为这个句子生成表示以用于检索相关文章：{query}"
        return self.encode([prefixed])
