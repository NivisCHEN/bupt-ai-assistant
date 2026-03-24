"""Document processing pipeline: clean, deduplicate, chunk, embed, and index."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from loguru import logger

from src.models import DocumentChunk
from src.retriever.faiss_store import FAISSStore
from src.utils.text_processing import chunk_text, clean_html


class DocumentProcessor:
    """Transforms raw crawled documents into embedded, indexed chunks."""

    def __init__(self, embedding_service) -> None:
        self.embedding_service = embedding_service

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def process_documents(self, raw_docs: list[dict]) -> list[DocumentChunk]:
        """Run the full processing pipeline on a batch of raw documents.

        Pipeline: clean HTML -> extract text -> deduplicate -> chunk ->
        generate embeddings.

        Args:
            raw_docs: List of dicts as returned by ``BUPTSpider.parse_detail_page``.

        Returns:
            A list of ``DocumentChunk`` objects with vectors populated.
        """
        if not raw_docs:
            return []

        logger.info("Processing {} raw documents", len(raw_docs))

        # 1. Clean HTML content
        for doc in raw_docs:
            doc["content"] = clean_html(doc.get("content", ""))

        # 2. Deduplicate
        docs = self.deduplicate(raw_docs)
        logger.info("{} documents after deduplication", len(docs))

        if not docs:
            return []

        # 3. Chunk
        chunks: list[DocumentChunk] = []
        for doc in docs:
            text_chunks = chunk_text(doc["content"])
            if not text_chunks:
                # If chunking yields nothing, keep the full content as one chunk
                text_chunks = [doc["content"]] if doc["content"].strip() else []

            for idx, text in enumerate(text_chunks):
                chunk_id = f"{doc['id']}_chunk_{idx}"
                chunks.append(
                    DocumentChunk(
                        id=chunk_id,
                        content=text,
                        title=doc.get("title", ""),
                        source_url=doc.get("source_url", ""),
                        published_at=doc.get("published_at"),
                        updated_at=doc.get("updated_at"),
                        author=doc.get("author"),
                        category=doc.get("category", ""),
                        metadata={
                            "chunk_index": idx,
                            "total_chunks": len(text_chunks),
                            "parent_id": doc["id"],
                            "attachments": doc.get("attachments", []),
                        },
                    )
                )

        logger.info("Created {} chunks from {} documents", len(chunks), len(docs))

        # 4. Generate embeddings
        if chunks:
            texts = [c.content for c in chunks]
            vectors = self.embedding_service.encode(texts)
            for chunk, vector in zip(chunks, vectors):
                chunk.vector = vector.tolist()

        logger.info("Embedding generation complete for {} chunks", len(chunks))
        return chunks

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def deduplicate(
        self,
        docs: list[dict],
        existing_ids: Optional[set] = None,
    ) -> list[dict]:
        """Remove duplicate documents using content hashing.

        Args:
            docs: List of document dicts (must contain ``content`` and ``id``).
            existing_ids: Optional set of previously-seen document IDs to
                skip.

        Returns:
            De-duplicated list of document dicts.
        """
        if existing_ids is None:
            existing_ids = set()

        seen_hashes: set[str] = set()
        unique: list[dict] = []

        for doc in docs:
            doc_id = doc.get("id", "")
            if doc_id in existing_ids:
                continue

            content_hash = hashlib.sha256(
                doc.get("content", "").encode()
            ).hexdigest()

            if content_hash in seen_hashes:
                continue

            seen_hashes.add(content_hash)
            existing_ids.add(doc_id)
            unique.append(doc)

        return unique

    # ------------------------------------------------------------------
    # Knowledge-base construction
    # ------------------------------------------------------------------

    def build_knowledge_base(
        self,
        chunks: list[DocumentChunk],
    ) -> tuple[FAISSStore, list[dict]]:
        """Build a FAISS index and accompanying metadata mapping.

        Args:
            chunks: List of ``DocumentChunk`` objects with vectors set.

        Returns:
            A tuple of (``FAISSStore`` instance, metadata list) where each
            metadata entry corresponds to the vector at the same index.
        """
        if not chunks:
            store = FAISSStore()
            return store, []

        dimension = len(chunks[0].vector) if chunks[0].vector else 1024
        store = FAISSStore(dimension=dimension)

        vectors = np.array(
            [c.vector for c in chunks if c.vector], dtype=np.float32
        )
        metadata: list[dict] = []

        for chunk in chunks:
            if chunk.vector is None:
                continue
            metadata.append({
                "id": chunk.id,
                "title": chunk.title,
                "content": chunk.content,
                "source_url": chunk.source_url,
                "published_at": chunk.published_at.isoformat() if chunk.published_at else None,
                "updated_at": chunk.updated_at.isoformat() if chunk.updated_at else None,
                "author": chunk.author,
                "category": chunk.category,
                "metadata": chunk.metadata,
            })

        if vectors.size > 0:
            store.build_index(vectors)
            logger.info(
                "Knowledge base built: {} vectors, dimension={}",
                store.size,
                dimension,
            )

        return store, metadata

    # ------------------------------------------------------------------
    # Metadata persistence
    # ------------------------------------------------------------------

    @staticmethod
    def save_metadata(metadata: list[dict], path: str) -> None:
        """Save metadata to a JSON file for id -> content/metadata lookup.

        Args:
            metadata: The metadata list produced by ``build_knowledge_base``.
            path: Filesystem path for the output JSON file.
        """
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(metadata, fh, ensure_ascii=False, indent=2)
        logger.info("Metadata saved to {} ({} entries)", path, len(metadata))
