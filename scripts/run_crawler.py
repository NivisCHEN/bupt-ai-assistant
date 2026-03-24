#!/usr/bin/env python3
"""Manual crawler trigger for BUPT campus data sources.

Usage:
    python -m scripts.run_crawler                    # Crawl all sources
    python -m scripts.run_crawler --source 教务通知   # Crawl a specific source
    python -m scripts.run_crawler --list             # List available sources
    python -m scripts.run_crawler --output data/raw  # Custom output directory
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

from src.crawler.base import BUPT_DATA_SOURCES, DataSource
from src.crawler.spider import BUPTSpider


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw"


def list_sources() -> None:
    """Print all available data sources."""
    print(f"{'Name':<20} {'Category':<12} {'Interval':<12} {'Auth':<6} URL")
    print("-" * 90)
    for src in BUPT_DATA_SOURCES:
        print(
            f"{src.name:<20} {src.category:<12} {src.crawl_interval_minutes:>5}min"
            f"      {'yes' if src.requires_auth else 'no':<6} {src.base_url}"
        )


def find_source(name: str) -> DataSource | None:
    """Find a data source by name (exact or substring match)."""
    for src in BUPT_DATA_SOURCES:
        if src.name == name:
            return src
    for src in BUPT_DATA_SOURCES:
        if name in src.name:
            return src
    return None


async def crawl_source(source: DataSource, output_dir: Path) -> int:
    """Crawl a single source and save results. Returns document count."""
    logger.info("Crawling: {} ({})", source.name, source.base_url)
    spider = BUPTSpider(source=source)
    docs = await spider.crawl()

    if docs:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{source.category}_{source.name}.json"
        out_path.write_text(
            json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("Saved {} documents to {}", len(docs), out_path)
    else:
        logger.warning("No documents returned from {}", source.name)

    return len(docs)


async def main(args: argparse.Namespace) -> None:
    if args.list:
        list_sources()
        return

    output_dir = Path(args.output)
    sources: list[DataSource] = []

    if args.source:
        matched = find_source(args.source)
        if not matched:
            logger.error("Source '{}' not found. Use --list to see available sources.", args.source)
            sys.exit(1)
        sources = [matched]
    else:
        sources = [s for s in BUPT_DATA_SOURCES if not s.requires_auth]
        logger.info("Crawling all {} public sources", len(sources))

    t0 = time.perf_counter()
    total_docs = 0

    for source in sources:
        try:
            count = await crawl_source(source, output_dir)
            total_docs += count
        except Exception as exc:
            logger.error("Failed to crawl {}: {}", source.name, exc)

    elapsed = time.perf_counter() - t0
    print(f"\nCrawl complete: {total_docs} documents from {len(sources)} sources in {elapsed:.1f}s")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manually trigger BUPT crawlers.")
    parser.add_argument("--source", type=str, help="Name of a specific source to crawl.")
    parser.add_argument("--list", action="store_true", help="List available data sources.")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT_DIR), help="Output directory for raw data.")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
