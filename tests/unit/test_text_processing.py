"""Tests for text processing utilities: chunking, HTML cleaning, metadata extraction."""

import pytest

from src.utils.text_processing import chunk_text, clean_html, extract_metadata


# ------------------------------------------------------------------ #
# chunk_text
# ------------------------------------------------------------------ #

class TestChunkText:

    def test_chinese_text_chunked(self):
        text = "北京邮电大学是一所以信息科技为特色的全国重点大学。" * 30
        chunks = chunk_text(text, max_length=100, overlap=20)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 120  # allow slight overflow due to token boundaries

    def test_overlap_between_chunks(self):
        text = "北京邮电大学位于北京市海淀区西土城路十号。" * 20
        chunks = chunk_text(text, max_length=60, overlap=15)
        if len(chunks) >= 2:
            # The end of chunk[i] should share characters with the start of chunk[i+1]
            tail = chunks[0][-15:]
            assert tail in chunks[1] or chunks[1].startswith(tail[:5])

    def test_empty_input(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_none_like_empty(self):
        # Edge case: whitespace-only
        assert chunk_text("\n\t  ") == []

    def test_very_short_text(self):
        text = "你好"
        chunks = chunk_text(text, max_length=512)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_single_chunk_no_split(self):
        text = "这是一段简短的测试文本"
        chunks = chunk_text(text, max_length=512)
        assert len(chunks) == 1

    def test_english_text(self):
        text = "Beijing University of Posts and Telecommunications. " * 20
        chunks = chunk_text(text, max_length=100, overlap=20)
        assert len(chunks) >= 1


# ------------------------------------------------------------------ #
# clean_html
# ------------------------------------------------------------------ #

class TestCleanHTML:

    def test_removes_script_tags(self):
        html = "<html><body><script>alert('xss')</script><p>Hello</p></body></html>"
        text = clean_html(html)
        assert "alert" not in text
        assert "Hello" in text

    def test_removes_style_tags(self):
        html = "<html><head><style>body{color:red}</style></head><body><p>Content</p></body></html>"
        text = clean_html(html)
        assert "color:red" not in text
        assert "Content" in text

    def test_preserves_text_content(self):
        html = "<div><h1>标题</h1><p>北邮是一所好大学</p></div>"
        text = clean_html(html)
        assert "标题" in text
        assert "北邮是一所好大学" in text

    def test_collapses_whitespace(self):
        html = "<p>  lots   of   spaces  </p>"
        text = clean_html(html)
        assert "  " not in text

    def test_empty_input(self):
        assert clean_html("") == ""

    def test_removes_noscript(self):
        html = "<noscript>No JS</noscript><p>Visible</p>"
        text = clean_html(html)
        assert "No JS" not in text
        assert "Visible" in text


# ------------------------------------------------------------------ #
# extract_metadata
# ------------------------------------------------------------------ #

class TestExtractMetadata:

    def test_extracts_title(self):
        html = "<html><head><title>北邮新闻</title></head><body></body></html>"
        meta = extract_metadata(html)
        assert meta["title"] == "北邮新闻"

    def test_extracts_author(self):
        html = '<html><head><meta name="author" content="张三"></head><body></body></html>'
        meta = extract_metadata(html)
        assert meta["author"] == "张三"

    def test_extracts_publish_date(self):
        html = '<html><head><meta name="date" content="2025-01-15"></head><body></body></html>'
        meta = extract_metadata(html)
        assert meta["publish_date"] == "2025-01-15"

    def test_extracts_description(self):
        html = '<html><head><meta name="description" content="校园动态"></head><body></body></html>'
        meta = extract_metadata(html)
        assert meta["description"] == "校园动态"

    def test_extracts_keywords(self):
        html = '<html><head><meta name="keywords" content="北邮,新闻,校园"></head><body></body></html>'
        meta = extract_metadata(html)
        assert meta["keywords"] == "北邮,新闻,校园"

    def test_extracts_og_properties(self):
        html = (
            '<html><head>'
            '<meta property="og:title" content="OG Title">'
            '<meta property="og:description" content="OG Desc">'
            '</head><body></body></html>'
        )
        meta = extract_metadata(html)
        assert "og:title" in meta["og"]
        assert meta["og"]["og:title"] == "OG Title"

    def test_empty_input(self):
        assert extract_metadata("") == {}

    def test_missing_fields_return_none(self):
        html = "<html><head><title>Only Title</title></head><body></body></html>"
        meta = extract_metadata(html)
        assert meta["title"] == "Only Title"
        assert meta["author"] is None
        assert meta["publish_date"] is None
