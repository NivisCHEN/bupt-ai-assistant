"""Text processing utilities for chunking, cleaning, and metadata extraction.

Provides Chinese-aware text splitting (via *jieba*), HTML sanitisation, and
lightweight metadata extraction from HTML documents.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

import jieba
from bs4 import BeautifulSoup


# --------------------------------------------------------------------- #
# Text chunking
# --------------------------------------------------------------------- #

def chunk_text(
    text: str,
    max_length: int = 512,
    overlap: int = 64,
) -> list[str]:
    """Split *text* into overlapping chunks using jieba tokenisation.

    The function tokenises the input with *jieba*, then greedily packs
    tokens into chunks whose total character length does not exceed
    *max_length*.  Consecutive chunks share *overlap* characters worth of
    trailing / leading tokens so that context is not lost at boundaries.

    Args:
        text: The input text (Chinese, English, or mixed).
        max_length: Maximum character length of each chunk.
        overlap: Number of overlapping characters between adjacent chunks.

    Returns:
        A list of text chunks.
    """
    if not text or not text.strip():
        return []

    tokens: list[str] = list(jieba.cut(text))
    if not tokens:
        return []

    chunks: list[str] = []
    current_tokens: list[str] = []
    current_length: int = 0

    for token in tokens:
        token_len = len(token)

        if current_length + token_len > max_length and current_tokens:
            chunks.append("".join(current_tokens))

            # Build the overlap window from the tail of current_tokens.
            overlap_tokens: list[str] = []
            overlap_length = 0
            for t in reversed(current_tokens):
                if overlap_length + len(t) > overlap:
                    break
                overlap_tokens.insert(0, t)
                overlap_length += len(t)

            current_tokens = overlap_tokens
            current_length = overlap_length

        current_tokens.append(token)
        current_length += token_len

    # Flush remaining tokens.
    if current_tokens:
        chunks.append("".join(current_tokens))

    return chunks


# --------------------------------------------------------------------- #
# HTML cleaning
# --------------------------------------------------------------------- #

def clean_html(html_content: str) -> str:
    """Strip HTML tags and normalise whitespace.

    Args:
        html_content: Raw HTML string.

    Returns:
        Plain text extracted from the HTML with collapsed whitespace.
    """
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, "html.parser")

    # Remove script and style elements entirely.
    for element in soup(["script", "style", "noscript"]):
        element.decompose()

    text = soup.get_text(separator=" ")
    # Collapse multiple whitespace characters into a single space.
    text = re.sub(r"\s+", " ", text).strip()
    return text


# --------------------------------------------------------------------- #
# Metadata extraction
# --------------------------------------------------------------------- #

def extract_metadata(html_content: str) -> dict[str, Any]:
    """Extract common metadata fields from an HTML document.

    Looks for ``<title>``, ``<meta>`` tags (author, description,
    keywords, publish date), and Open Graph properties.

    Args:
        html_content: Raw HTML string.

    Returns:
        A dict with keys ``title``, ``author``, ``description``,
        ``keywords``, ``publish_date``, and ``og`` (Open Graph fields).
    """
    if not html_content:
        return {}

    soup = BeautifulSoup(html_content, "html.parser")

    title: str = ""
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        title = title_tag.string.strip()

    def _meta_content(name: str) -> Optional[str]:
        tag = soup.find("meta", attrs={"name": re.compile(name, re.IGNORECASE)})
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
        return None

    author = _meta_content("author")
    description = _meta_content("description")
    keywords = _meta_content("keywords")

    # Try common date meta names.
    publish_date: Optional[str] = None
    for date_name in ("publish_date", "publishdate", "date", "article:published_time"):
        candidate = _meta_content(date_name)
        if candidate:
            publish_date = candidate
            break
    # Also check <meta property="article:published_time"> (OG style).
    if publish_date is None:
        og_date_tag = soup.find(
            "meta", attrs={"property": "article:published_time"}
        )
        if og_date_tag and og_date_tag.get("content"):
            publish_date = str(og_date_tag["content"]).strip()

    # Open Graph metadata.
    og: dict[str, str] = {}
    for og_tag in soup.find_all("meta", attrs={"property": re.compile(r"^og:")}):
        prop = str(og_tag.get("property", ""))
        content = str(og_tag.get("content", "")).strip()
        if prop and content:
            og[prop] = content

    return {
        "title": title,
        "author": author,
        "description": description,
        "keywords": keywords,
        "publish_date": publish_date,
        "og": og,
    }
