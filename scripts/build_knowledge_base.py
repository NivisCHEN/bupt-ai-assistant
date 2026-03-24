#!/usr/bin/env python3
"""Build the BUPT campus knowledge base (offline initialisation).

Pipeline:
    load raw documents -> clean -> chunk -> embed -> build FAISS index -> save

Maps to the "知识库初始化 离线" section in the system UML.

Usage:
    python -m scripts.build_knowledge_base --source file
    python -m scripts.build_knowledge_base --source crawl --batch-size 64
    python -m scripts.build_knowledge_base --source both --output-dir data/indices
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path so ``src`` is importable.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.crawler.base import BUPT_DATA_SOURCES
from src.crawler.spider import BUPTSpider
from src.embedding.service import EmbeddingService
from src.retriever.faiss_store import FAISSStore
from src.utils.text_processing import chunk_text, clean_html

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("build_knowledge_base")

RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "indices"


# ---------------------------------------------------------------------- #
# Document loading
# ---------------------------------------------------------------------- #

def load_documents_from_files(raw_dir: Path) -> list[dict[str, Any]]:
    """Load raw documents from *raw_dir*.

    Supports ``.json``, ``.txt``, and ``.html`` files.
    """
    documents: list[dict[str, Any]] = []

    if not raw_dir.exists():
        logger.warning("Raw data directory does not exist: %s", raw_dir)
        return documents

    for path in sorted(raw_dir.iterdir()):
        if path.suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    documents.extend(data)
                elif isinstance(data, dict):
                    documents.append(data)
                logger.info("Loaded %s (%d docs so far)", path.name, len(documents))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                logger.warning("Skipping %s: %s", path.name, exc)

        elif path.suffix == ".txt":
            text = path.read_text(encoding="utf-8").strip()
            if text:
                documents.append({
                    "id": path.stem,
                    "title": path.stem,
                    "content": text,
                    "category": "unknown",
                    "source_url": "",
                    "published_at": None,
                })
                logger.info("Loaded %s", path.name)

        elif path.suffix in (".html", ".htm"):
            html = path.read_text(encoding="utf-8")
            cleaned = clean_html(html)
            if cleaned:
                documents.append({
                    "id": path.stem,
                    "title": path.stem,
                    "content": cleaned,
                    "category": "unknown",
                    "source_url": "",
                    "published_at": None,
                })
                logger.info("Loaded %s", path.name)

    return documents


async def load_documents_from_crawlers() -> list[dict[str, Any]]:
    """Run all configured crawlers and collect documents."""
    documents: list[dict[str, Any]] = []

    for source in BUPT_DATA_SOURCES:
        if source.requires_auth:
            logger.info("Skipping authenticated source: %s", source.name)
            continue

        spider = BUPTSpider(source=source)
        try:
            docs = await spider.crawl()
            documents.extend(docs)
            logger.info("Crawled %s: %d documents", source.name, len(docs))
        except Exception as exc:
            logger.error("Crawler failed for %s: %s", source.name, exc)

    return documents


# ---------------------------------------------------------------------- #
# Processing pipeline
# ---------------------------------------------------------------------- #

def clean_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Basic cleaning: strip whitespace, drop empty content."""
    cleaned: list[dict[str, Any]] = []
    for doc in documents:
        content = doc.get("content", "")
        if isinstance(content, str):
            content = content.strip()
        if not content:
            continue
        doc["content"] = content
        cleaned.append(doc)
    return cleaned


def chunk_documents(
    documents: list[dict[str, Any]],
    max_length: int = 512,
    overlap: int = 64,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Chunk documents and produce parallel lists of texts and metadata.

    Returns:
        (chunks, metadata) — a list of text chunks and a list of metadata
        dicts (one per chunk) carrying the parent document's info.
    """
    all_chunks: list[str] = []
    all_metadata: list[dict[str, Any]] = []

    for doc in documents:
        text_chunks = chunk_text(doc["content"], max_length=max_length, overlap=overlap)
        for idx, chunk in enumerate(text_chunks):
            all_chunks.append(chunk)
            all_metadata.append({
                "doc_id": doc.get("id", ""),
                "title": doc.get("title", ""),
                "category": doc.get("category", ""),
                "source_url": doc.get("source_url", ""),
                "published_at": str(doc.get("published_at", "")),
                "chunk_index": idx,
                "total_chunks": len(text_chunks),
            })

    return all_chunks, all_metadata


def build_and_save_index(
    chunks: list[str],
    metadata: list[dict[str, Any]],
    output_dir: Path,
    batch_size: int = 32,
) -> None:
    """Embed chunks, build FAISS index, and persist to disk."""
    index_path = str(output_dir / "school.index")
    metadata_path = str(output_dir / "school_metadata.json")

    output_dir.mkdir(parents=True, exist_ok=True)

    if not chunks:
        logger.warning("No chunks to index. Writing empty index.")
        store = FAISSStore(dimension=1024)
        import numpy as np
        store.build_index(np.empty((0, 1024), dtype=np.float32))
        store.save_index(index_path)
        Path(metadata_path).write_text("[]", encoding="utf-8")
        return

    logger.info("Initialising embedding service …")
    embedder = EmbeddingService()

    logger.info("Encoding %d chunks (batch_size=%d) …", len(chunks), batch_size)
    t0 = time.perf_counter()
    vectors = embedder.encode(chunks, batch_size=batch_size)
    elapsed = time.perf_counter() - t0
    logger.info(
        "Encoding complete: %d vectors in %.1fs (%.0f chunks/s)",
        vectors.shape[0],
        elapsed,
        vectors.shape[0] / elapsed if elapsed > 0 else 0,
    )

    logger.info("Building FAISS index …")
    store = FAISSStore(dimension=vectors.shape[1])
    store.build_index(vectors)
    store.save_index(index_path)

    logger.info("Saving metadata to %s …", metadata_path)
    Path(metadata_path).write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------- #
# Main
# ---------------------------------------------------------------------- #

async def main(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    documents: list[dict[str, Any]] = []

    # --- Load ---
    if args.source in ("file", "both"):
        logger.info("Loading documents from files in %s …", RAW_DATA_DIR)
        file_docs = load_documents_from_files(RAW_DATA_DIR)
        logger.info("Loaded %d documents from files.", len(file_docs))
        documents.extend(file_docs)

    if args.source in ("crawl", "both"):
        logger.info("Running crawlers …")
        crawl_docs = await load_documents_from_crawlers()
        logger.info("Loaded %d documents from crawlers.", len(crawl_docs))
        documents.extend(crawl_docs)

    if not documents:
        logger.warning("No documents loaded. Nothing to index.")
        return

    # --- Clean ---
    logger.info("Cleaning %d documents …", len(documents))
    documents = clean_documents(documents)
    logger.info("After cleaning: %d documents.", len(documents))

    # --- Chunk ---
    logger.info("Chunking documents …")
    chunks, metadata = chunk_documents(documents)
    logger.info("Generated %d chunks from %d documents.", len(chunks), len(documents))

    # --- Embed & Index ---
    build_and_save_index(chunks, metadata, output_dir, batch_size=args.batch_size)

    # --- Stats ---
    print("\n" + "=" * 60)
    print("Knowledge-base build complete")
    print("=" * 60)
    print(f"  Documents loaded:  {len(documents)}")
    print(f"  Chunks generated:  {len(chunks)}")
    print(f"  Index saved to:    {output_dir / 'school.index'}")
    print(f"  Metadata saved to: {output_dir / 'school_metadata.json'}")
    print(f"  Timestamp:         {datetime.now().isoformat()}")
    print("=" * 60)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the BUPT campus knowledge base.",
    )
    parser.add_argument(
        "--source",
        choices=["file", "crawl", "both"],
        default="file",
        help="Where to load documents from (default: file).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for the output index and metadata files.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for embedding encoding (default: 32).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
