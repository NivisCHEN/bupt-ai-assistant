"""Async spider for crawling BUPT campus websites."""

from __future__ import annotations

import asyncio
import hashlib
import random
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from src.crawler.base import DataSource


class BUPTSpider:
    """Asynchronous spider that crawls a single BUPT data source."""

    def __init__(
        self,
        source: DataSource,
        concurrent_limit: int = 5,
        retry_max: int = 3,
        respect_robots: bool = True,
        cookies: dict | None = None,
    ) -> None:
        self.source = source
        self.concurrent_limit = concurrent_limit
        self.retry_max = retry_max
        self.respect_robots = respect_robots
        self.cookies = cookies or {}

        self._semaphore = asyncio.Semaphore(concurrent_limit)
        self._robots_cache: dict[str, RobotFileParser] = {}
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def crawl(self) -> list[dict]:
        """Fetch the list page, extract article links, then fetch each detail page.

        Returns:
            A list of parsed document dicts.
        """
        documents: list[dict] = []
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers={"User-Agent": "BUPTAIAssistant/1.0"},
            cookies=self.cookies,
        ) as client:
            self._client = client

            logger.info("Crawling source: {} ({})", self.source.name, self.source.base_url)

            list_html = await self.fetch_page(self.source.base_url)
            if not list_html:
                logger.warning("Failed to fetch list page for {}", self.source.name)
                return documents

            urls = self.parse_list_page(list_html)
            logger.info("Found {} article URLs from {}", len(urls), self.source.name)

            tasks = [self._fetch_and_parse(url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.error("Error fetching article: {}", result)
                elif result is not None:
                    documents.append(result)

            self._client = None

        logger.info(
            "Crawl complete for {}: {} documents collected",
            self.source.name,
            len(documents),
        )
        return documents

    async def fetch_page(self, url: str) -> str:
        """Fetch a page with retry logic and optional robots.txt checking.

        Args:
            url: The URL to fetch.

        Returns:
            The HTML content as a string, or empty string on failure.
        """
        if self.respect_robots and not await self.check_robots(url):
            logger.info("Blocked by robots.txt: {}", url)
            return ""

        last_error: Optional[Exception] = None
        for attempt in range(1, self.retry_max + 1):
            try:
                # Rate-limit: sleep outside semaphore to avoid wasting slots
                await asyncio.sleep(0.5)
                async with self._semaphore:
                    if self._client is None:
                        logger.error("HTTP client not initialised")
                        return ""
                    response = await self._client.get(url)
                    response.raise_for_status()
                    return response.text
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_error = exc
                if not self._should_retry(attempt, exc):
                    break
                wait = self._backoff_delay(attempt)
                logger.warning(
                    "Retry {}/{} for {} after {:.1f}s — {}",
                    attempt,
                    self.retry_max,
                    url,
                    wait,
                    exc,
                )
                await asyncio.sleep(wait)

        logger.error("All retries exhausted for {}: {}", url, last_error)
        return ""

    def parse_list_page(self, html: str) -> list[str]:
        """Extract article URLs from a list/index page.

        Args:
            html: Raw HTML of the list page.

        Returns:
            Absolute URLs of individual articles.
        """
        soup = BeautifulSoup(html, "html.parser")
        selector = self.source.selectors.get("list", "a")
        links: list[str] = []

        for tag in soup.select(selector):
            href = tag.get("href")
            if href:
                absolute_url = urljoin(self.source.base_url, str(href))
                links.append(absolute_url)

        return links

    def parse_detail_page(self, html: str, url: str) -> dict:
        """Parse structured data from an article detail page.

        Args:
            html: Raw HTML of the detail page.
            url: The URL the page was fetched from.

        Returns:
            A dict with keys: id, title, content, author, published_at,
            updated_at, source_url, category, attachments.
        """
        soup = BeautifulSoup(html, "html.parser")
        selectors = self.source.selectors

        title = self._select_text(soup, selectors.get("title", "h1"))
        content = self._select_text(soup, selectors.get("content", "body"))
        author = self._select_text(soup, selectors.get("author", ""))
        date_str = self._select_text(soup, selectors.get("date", ""))

        published_at = self._parse_date(date_str) if date_str else None

        # Extract attachment links (PDFs, docs, etc.)
        attachments: list[dict] = []
        for link_tag in soup.select("a[href]"):
            href = str(link_tag.get("href", ""))
            if any(href.lower().endswith(ext) for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")):
                attachments.append({
                    "name": link_tag.get_text(strip=True) or href.split("/")[-1],
                    "url": urljoin(url, href),
                })

        doc_id = hashlib.sha256(url.encode()).hexdigest()[:16]

        return {
            "id": doc_id,
            "title": title,
            "content": content,
            "author": author or None,
            "published_at": published_at,
            "updated_at": datetime.now(),
            "source_url": url,
            "category": self.source.category,
            "attachments": attachments,
        }

    async def check_robots(self, url: str) -> bool:
        """Check whether *url* is allowed by the site's robots.txt.

        Args:
            url: The URL to check.

        Returns:
            True if crawling is allowed (or if robots.txt cannot be fetched).
        """
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        if robots_url not in self._robots_cache:
            rp = RobotFileParser()
            try:
                if self._client is not None:
                    resp = await self._client.get(robots_url, timeout=10.0)
                    rp.parse(resp.text.splitlines())
                else:
                    # If no client, allow by default
                    return True
            except Exception as exc:
                logger.debug("Could not fetch robots.txt from {}: {}", robots_url, exc)
                return True
            self._robots_cache[robots_url] = rp

        rp = self._robots_cache[robots_url]
        return rp.can_fetch("BUPTAIAssistant", url)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _should_retry(self, attempt: int, error: Exception) -> bool:
        """Decide whether to retry based on the attempt count and error type.

        Uses exponential backoff with jitter. Returns False when max retries
        have been reached or the error is non-retryable (e.g. 404).
        """
        if attempt >= self.retry_max:
            return False

        if isinstance(error, httpx.HTTPStatusError):
            # Do not retry client errors other than 429 (rate-limited).
            status = error.response.status_code
            if 400 <= status < 500 and status != 429:
                return False

        return True

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        """Compute exponential backoff with jitter."""
        base = min(2 ** attempt, 30)
        jitter = random.uniform(0, base * 0.5)
        return base + jitter

    async def _fetch_and_parse(self, url: str) -> Optional[dict]:
        """Fetch a detail page and parse it."""
        html = await self.fetch_page(url)
        if not html:
            return None
        return self.parse_detail_page(html, url)

    @staticmethod
    def _select_text(soup: BeautifulSoup, selector: str) -> str:
        """Run a CSS selector and return the stripped text of the first match."""
        if not selector:
            return ""
        tag = soup.select_one(selector)
        return tag.get_text(strip=True) if tag else ""

    @staticmethod
    def _parse_date(date_str: str) -> Optional[datetime]:
        """Try common Chinese / ISO date formats."""
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y年%m月%d日",
            "%Y/%m/%d",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        logger.debug("Unparseable date string: {}", date_str)
        return None
