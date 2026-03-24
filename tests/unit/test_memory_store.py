"""Tests for the MemoryStore."""

from unittest.mock import MagicMock

import numpy as np
import pytest

from src.memory.store import MemoryStore
from src.models import MemoryType


@pytest.fixture()
def mock_embedding_service():
    """Return a mock embedding service that produces random 64-d vectors."""
    svc = MagicMock()
    rng = np.random.RandomState(42)

    def fake_encode(texts):
        return rng.randn(len(texts), 64).astype(np.float32)

    svc.encode = MagicMock(side_effect=fake_encode)
    return svc


@pytest.fixture()
def memory_store(mock_embedding_service):
    return MemoryStore(
        embedding_service=mock_embedding_service,
        faiss_dimension=64,
    )


class TestSaveShortTerm:

    def test_save_and_retrieve(self, memory_store):
        entry = memory_store.save_short_term("user1", "你好，图书馆几点关门？")
        assert entry.type == MemoryType.SHORT_TERM
        assert entry.user_id == "user1"
        assert entry.content == "你好，图书馆几点关门？"
        assert entry.importance_score == 0.5

    def test_metadata(self, memory_store):
        entry = memory_store.save_short_term(
            "user1", "content", metadata={"source": "chat"}
        )
        assert entry.metadata["source"] == "chat"


class TestSaveLongTerm:

    def test_save_creates_vector(self, memory_store, mock_embedding_service):
        entry = memory_store.save_long_term("user1", "重要知识点", importance=0.9)
        assert entry.type == MemoryType.LONG_TERM
        assert entry.vector is not None
        assert len(entry.vector) == 64
        mock_embedding_service.encode.assert_called()

    def test_importance_clamped(self, memory_store):
        entry = memory_store.save_long_term("user1", "test", importance=1.5)
        assert entry.importance_score == 1.0

        entry2 = memory_store.save_long_term("user1", "test", importance=-0.5)
        assert entry2.importance_score == 0.0

    def test_source_ref(self, memory_store):
        entry = memory_store.save_long_term(
            "user1", "test", importance=0.7, source_ref="https://bupt.edu.cn"
        )
        assert entry.source_ref == "https://bupt.edu.cn"


class TestSaveEpisodic:

    def test_save_episodic(self, memory_store, mock_embedding_service):
        entry = memory_store.save_episodic(
            "user1", "报修了空调", event_type="repair_ticket"
        )
        assert entry.type == MemoryType.EPISODIC
        assert entry.metadata["event_type"] == "repair_ticket"
        assert entry.importance_score == 0.8
        assert entry.vector is not None
        mock_embedding_service.encode.assert_called()

    def test_episodic_metadata_preserved(self, memory_store):
        entry = memory_store.save_episodic(
            "user1",
            "预约了会议室",
            event_type="booking",
            metadata={"room": "A301"},
        )
        assert entry.metadata["event_type"] == "booking"
        assert entry.metadata["room"] == "A301"


class TestGetRecentHistory:

    def test_returns_short_term_only(self, memory_store):
        memory_store.save_short_term("user1", "msg1")
        memory_store.save_short_term("user1", "msg2")
        memory_store.save_long_term("user1", "long term", importance=0.8)

        history = memory_store.get_recent_history("user1")
        assert all(e.type == MemoryType.SHORT_TERM for e in history)
        assert len(history) == 2

    def test_limit(self, memory_store):
        for i in range(15):
            memory_store.save_short_term("user1", f"msg-{i}")

        history = memory_store.get_recent_history("user1", limit=5)
        assert len(history) == 5

    def test_sorted_newest_first(self, memory_store):
        memory_store.save_short_term("user1", "older")
        memory_store.save_short_term("user1", "newer")
        history = memory_store.get_recent_history("user1")
        assert history[0].timestamp >= history[-1].timestamp

    def test_empty_user(self, memory_store):
        history = memory_store.get_recent_history("nonexistent")
        assert history == []


class TestDeleteMemory:

    def test_delete_existing(self, memory_store):
        entry = memory_store.save_short_term("user1", "to delete")
        result = memory_store.delete_memory("user1", entry.id)
        assert result is True
        assert memory_store.get_all_memories("user1") == []

    def test_delete_nonexistent(self, memory_store):
        result = memory_store.delete_memory("user1", "fake-id")
        assert result is False

    def test_delete_wrong_user(self, memory_store):
        entry = memory_store.save_short_term("user1", "data")
        result = memory_store.delete_memory("user2", entry.id)
        assert result is False


class TestUpdateImportance:

    def test_increase_importance(self, memory_store):
        entry = memory_store.save_short_term("user1", "content")
        updated = memory_store.update_importance("user1", entry.id, delta=0.3)
        assert updated.importance_score == pytest.approx(0.8)

    def test_clamp_to_one(self, memory_store):
        entry = memory_store.save_short_term("user1", "content")
        updated = memory_store.update_importance("user1", entry.id, delta=0.9)
        assert updated.importance_score == 1.0

    def test_clamp_to_zero(self, memory_store):
        entry = memory_store.save_short_term("user1", "content")
        updated = memory_store.update_importance("user1", entry.id, delta=-1.0)
        assert updated.importance_score == 0.0

    def test_nonexistent_raises(self, memory_store):
        with pytest.raises(ValueError):
            memory_store.update_importance("user1", "fake-id", delta=0.1)
