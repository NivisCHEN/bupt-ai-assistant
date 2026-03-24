"""Tests for the SimpleReranker."""

from datetime import datetime, timezone, timedelta

import pytest

from src.retriever.reranker import SimpleReranker


@pytest.fixture()
def reranker():
    return SimpleReranker(top_k=3)


def _candidate(id_: str, content: str, score: float, timestamp=None):
    """Helper to create a candidate dict."""
    meta = {}
    if timestamp is not None:
        meta["timestamp"] = timestamp
    return {"id": id_, "content": content, "score": score, "metadata": meta}


class TestRerank:

    def test_basic_reranking(self, reranker):
        candidates = [
            _candidate("a", "library hours info", 0.9),
            _candidate("b", "cafeteria menu", 0.5),
            _candidate("c", "library location map", 0.7),
        ]
        results = reranker.rerank("library hours", candidates)
        assert len(results) <= 3
        # Top result should be relevant to the query
        assert results[0]["id"] in ("a", "c")

    def test_respects_top_k(self, reranker):
        candidates = [_candidate(str(i), f"content {i}", 0.5) for i in range(10)]
        results = reranker.rerank("content", candidates)
        assert len(results) == 3

    def test_empty_candidates(self, reranker):
        assert reranker.rerank("any query", []) == []

    def test_empty_query_returns_top_k(self, reranker):
        candidates = [_candidate(str(i), f"text {i}", float(i)) for i in range(5)]
        results = reranker.rerank("", candidates)
        assert len(results) == 3

    def test_time_decay_favors_recent(self, reranker):
        now = datetime.now(timezone.utc)
        old_ts = (now - timedelta(days=365)).isoformat()
        new_ts = now.isoformat()

        candidates = [
            _candidate("old", "library hours", 0.8, timestamp=old_ts),
            _candidate("new", "library hours", 0.8, timestamp=new_ts),
        ]
        results = reranker.rerank("library hours", candidates)
        # The newer document should rank higher
        assert results[0]["id"] == "new"

    def test_keyword_overlap_boost(self, reranker):
        candidates = [
            _candidate("match", "北邮图书馆开放时间", 0.5),
            _candidate("nomatch", "完全不相关的内容", 0.5),
        ]
        results = reranker.rerank("图书馆", candidates)
        assert results[0]["id"] == "match"

    def test_no_timestamp_gives_neutral_recency(self, reranker):
        candidates = [
            _candidate("a", "content about query", 0.9),
        ]
        results = reranker.rerank("query", candidates)
        # Should not crash and should return a result
        assert len(results) == 1
        assert results[0]["score"] > 0

    def test_unix_timestamp(self, reranker):
        import time
        now_ts = time.time()
        candidates = [
            _candidate("a", "library", 0.8, timestamp=now_ts),
        ]
        results = reranker.rerank("library", candidates)
        assert len(results) == 1

    def test_scores_are_updated(self, reranker):
        candidates = [
            _candidate("a", "test content", 0.9),
        ]
        results = reranker.rerank("test", candidates)
        # The score should be the combined score, not the original
        assert results[0]["score"] != 0.9
