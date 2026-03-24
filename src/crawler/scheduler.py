"""Periodic crawl scheduler for BUPT data sources."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from src.crawler.base import BUPT_DATA_SOURCES, DataSource
from src.crawler.processor import DocumentProcessor
from src.crawler.spider import BUPTSpider


class CrawlScheduler:
    """Manages periodic crawl jobs for all configured BUPT data sources."""

    def __init__(self, processor: DocumentProcessor) -> None:
        self.processor = processor
        self._scheduler: Optional[AsyncIOScheduler] = None

    # ------------------------------------------------------------------
    # Job configuration
    # ------------------------------------------------------------------

    def setup_jobs(self) -> None:
        """Create APScheduler interval jobs for each data source.

        Each job runs at the interval specified by the source's
        ``crawl_interval_minutes`` and delegates to ``run_crawl_job``.
        """
        if self._scheduler is None:
            self._scheduler = AsyncIOScheduler()

        for source in BUPT_DATA_SOURCES:
            job_id = f"crawl_{source.category}_{source.name}"
            self._scheduler.add_job(
                self.run_crawl_job,
                trigger="interval",
                minutes=source.crawl_interval_minutes,
                id=job_id,
                name=f"Crawl {source.name}",
                kwargs={"source": source},
                replace_existing=True,
                max_instances=1,
            )
            logger.info(
                "Scheduled job '{}' every {} min",
                job_id,
                source.crawl_interval_minutes,
            )

    # ------------------------------------------------------------------
    # Job execution
    # ------------------------------------------------------------------

    async def run_crawl_job(self, source: DataSource) -> dict:
        """Execute one crawl-and-process cycle for a single data source.

        Args:
            source: The ``DataSource`` to crawl.

        Returns:
            A stats dict with keys: source, documents_fetched,
            chunks_created, started_at, finished_at, error (if any).
        """
        started_at = datetime.now()
        stats: dict = {
            "source": source.name,
            "documents_fetched": 0,
            "chunks_created": 0,
            "started_at": started_at.isoformat(),
            "finished_at": None,
            "error": None,
        }

        try:
            logger.info("Starting crawl job for: {}", source.name)

            spider = BUPTSpider(source)
            raw_docs = await spider.crawl()
            stats["documents_fetched"] = len(raw_docs)

            if raw_docs:
                chunks = self.processor.process_documents(raw_docs)
                stats["chunks_created"] = len(chunks)

                if chunks:
                    store, metadata = self.processor.build_knowledge_base(chunks)
                    logger.info(
                        "Knowledge base updated for {}: {} vectors",
                        source.name,
                        store.size,
                    )

        except Exception as exc:
            stats["error"] = str(exc)
            logger.exception("Crawl job failed for {}: {}", source.name, exc)
        finally:
            finished_at = datetime.now()
            stats["finished_at"] = finished_at.isoformat()
            elapsed = (finished_at - started_at).total_seconds()
            logger.info(
                "Crawl job for {} finished in {:.1f}s — fetched={}, chunks={}",
                source.name,
                elapsed,
                stats["documents_fetched"],
                stats["chunks_created"],
            )

        return stats

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Set up jobs and start the scheduler."""
        self.setup_jobs()
        if self._scheduler is not None:
            self._scheduler.start()
            logger.info("CrawlScheduler started")

    def stop(self) -> None:
        """Shut down the scheduler gracefully."""
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=True)
            logger.info("CrawlScheduler stopped")
            self._scheduler = None
