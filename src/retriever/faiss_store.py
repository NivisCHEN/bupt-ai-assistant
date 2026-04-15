from __future__ import annotations

import logging
from pathlib import Path

import faiss
import numpy as np

logger = logging.getLogger(__name__)


class FAISSStore:
    """Vector store backed by FAISS for similarity search."""

    def __init__(self, dimension: int = 512) -> None:
        self.dimension = dimension
        self._index: faiss.Index | None = None

    # ------------------------------------------------------------------
    # Index construction
    # ------------------------------------------------------------------

    def build_index(
        self,
        vectors: np.ndarray,
        use_ivf: bool = True,
        nlist: int = 100,
    ) -> None:
        """Build a FAISS index from a matrix of vectors.

        Uses IVF (inverted-file) index when *use_ivf* is True **and** the
        number of vectors exceeds 10 000; otherwise falls back to a flat
        (brute-force) index.

        Args:
            vectors: np.ndarray of shape (n, dimension).
            use_ivf: Whether to attempt building an IVF index.
            nlist: Number of Voronoi cells for the IVF index.
        """
        if vectors.size == 0:
            self._index = faiss.IndexFlatIP(self.dimension)
            return

        vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        n = vectors.shape[0]

        if use_ivf and n > 10_000:
            quantizer = faiss.IndexFlatIP(self.dimension)
            actual_nlist = min(nlist, n)
            self._index = faiss.IndexIVFFlat(
                quantizer, self.dimension, actual_nlist, faiss.METRIC_INNER_PRODUCT
            )
            self._index.train(vectors)  # type: ignore[union-attr]
            self._index.add(vectors)  # type: ignore[union-attr]
            self._index.nprobe = min(10, actual_nlist)  # type: ignore[union-attr]
            logger.info("Built IVF index with %d vectors, nlist=%d", n, actual_nlist)
        else:
            self._index = faiss.IndexFlatIP(self.dimension)
            self._index.add(vectors)
            logger.info("Built flat index with %d vectors", n)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_index(self, path: str) -> None:
        """Serialize the FAISS index to disk."""
        if self._index is None:
            raise RuntimeError("No index to save. Build or load an index first.")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, path)
        logger.info("Index saved to %s", path)

    def load_index(self, path: str) -> None:
        """Load a FAISS index from disk."""
        if not Path(path).exists():
            raise FileNotFoundError(f"Index file not found: {path}")
        self._index = faiss.read_index(path)
        logger.info("Index loaded from %s (%d vectors)", path, self._index.ntotal)

    # ------------------------------------------------------------------
    # Search & mutation
    # ------------------------------------------------------------------

    def search(
        self, query_vector: np.ndarray, top_k: int = 10
    ) -> tuple[np.ndarray, np.ndarray]:
        """Search for the nearest neighbours of *query_vector*.

        Args:
            query_vector: np.ndarray of shape (1, dimension) or (dimension,).
            top_k: Number of results to return.

        Returns:
            A tuple of (distances, indices), each of shape (1, top_k).
        """
        if self._index is None or self._index.ntotal == 0:
            return (
                np.empty((1, 0), dtype=np.float32),
                np.empty((1, 0), dtype=np.int64),
            )

        query_vector = np.ascontiguousarray(
            query_vector.reshape(1, -1), dtype=np.float32
        )
        top_k = min(top_k, self._index.ntotal)
        distances, indices = self._index.search(query_vector, top_k)
        return distances, indices

    def add_vectors(self, vectors: np.ndarray) -> None:
        """Add vectors to an existing index.

        If no index exists yet, a flat index is created automatically.
        """
        if vectors.size == 0:
            return

        vectors = np.ascontiguousarray(vectors, dtype=np.float32)

        if self._index is None:
            self._index = faiss.IndexFlatIP(self.dimension)

        self._index.add(vectors)
        logger.info("Added %d vectors (total: %d)", vectors.shape[0], self._index.ntotal)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        """Return the number of vectors currently in the index."""
        if self._index is None:
            return 0
        return self._index.ntotal
