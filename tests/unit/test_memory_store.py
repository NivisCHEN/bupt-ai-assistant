"""Tests for the MemoryStore (SQLite-backed)."""

import os
import tempfile
from unittest.mock import MagicMock

import numpy as np
import pytest
import pytest_asyncio

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


@pytest_asyncio.fixture()
async def memory_store(mock_embedding_service, tmp_path):
    db_path = str(tmp_path / "test_memories.db")
    store = MemoryStore(
        embedding_service=mock_embedding_service,
        faiss_dimension=64,
        db_path=db_path,
    )
    await store.initialize()
    yield store
    await store.close()


class TestSaveShortTerm:

    @pytest.mark.asyncio
    async def test_save_and_retrieve(self, memory_store):
        entry = await memory_store.save_short_term("user1", "你好，图书馆几点关门？")
        assert entry.type == MemoryType.SHORT_TERM
        assert entry.user_id == "user1"
        assert entry.content == "你好，图书馆几点关门？"
        assert entry.importance_score == 0.5

    @pytest.mark.asyncio
    async def test_metadata(self, memory_store):
        entry = await memory_store.save_short_term(
            "user1", "content", metadata={"source": "chat"}
        )
        assert entry.metadata["source"] == "chat"


class TestSaveLongTerm:

    @pytest.mark.asyncio
    async def test_save_creates_vector(self, memory_store, mock_embedding_service):
        entry = await memory_store.save_long_term("user1", "重要知识点", importance=0.9)
        assert entry.type == MemoryType.LONG_TERM
        assert entry.vector is not None
        assert len(entry.vector) == 64
        mock_embedding_service.encode.assert_called()

    @pytest.mark.asyncio
    async def test_importance_clamped(self, memory_store):
        entry = await memory_store.save_long_term("user1", "test", importance=1.5)
        assert entry.importance_score == 1.0

        entry2 = await memory_store.save_long_term("user1", "test", importance=-0.5)
        assert entry2.importance_score == 0.0

    @pytest.mark.asyncio
    async def test_source_ref(self, memory_store):
        entry = await memory_store.save_long_term(
            "user1", "test", importance=0.7, source_ref="https://bupt.edu.cn"
        )
        assert entry.source_ref == "https://bupt.edu.cn"


class TestSaveEpisodic:

    @pytest.mark.asyncio
    async def test_save_episodic(self, memory_store, mock_embedding_service):
        entry = await memory_store.save_episodic(
            "user1", "报修了空调", event_type="repair_ticket"
        )
        assert entry.type == MemoryType.EPISODIC
        assert entry.metadata["event_type"] == "repair_ticket"
        assert entry.importance_score == 0.8
        assert entry.vector is not None
        mock_embedding_service.encode.assert_called()

    @pytest.mark.asyncio
    async def test_episodic_metadata_preserved(self, memory_store):
        entry = await memory_store.save_episodic(
            "user1",
            "预约了会议室",
            event_type="booking",
            metadata={"room": "A301"},
        )
        assert entry.metadata["event_type"] == "booking"
        assert entry.metadata["room"] == "A301"


class TestGetRecentHistory:

    @pytest.mark.asyncio
    async def test_returns_short_term_only(self, memory_store):
        await memory_store.save_short_term("user1", "msg1")
        await memory_store.save_short_term("user1", "msg2")
        await memory_store.save_long_term("user1", "long term", importance=0.8)

        history = memory_store.get_recent_history("user1")
        assert all(e.type == MemoryType.SHORT_TERM for e in history)
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_limit(self, memory_store):
        for i in range(15):
            await memory_store.save_short_term("user1", f"msg-{i}")

        history = memory_store.get_recent_history("user1", limit=5)
        assert len(history) == 5

    @pytest.mark.asyncio
    async def test_sorted_newest_first(self, memory_store):
        await memory_store.save_short_term("user1", "older")
        await memory_store.save_short_term("user1", "newer")
        history = memory_store.get_recent_history("user1")
        assert history[0].timestamp >= history[-1].timestamp

    @pytest.mark.asyncio
    async def test_empty_user(self, memory_store):
        history = memory_store.get_recent_history("nonexistent")
        assert history == []


class TestDeleteMemory:

    @pytest.mark.asyncio
    async def test_delete_existing(self, memory_store):
        entry = await memory_store.save_short_term("user1", "to delete")
        result = await memory_store.delete_memory("user1", entry.id)
        assert result is True
        assert memory_store.get_all_memories("user1") == []

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, memory_store):
        result = await memory_store.delete_memory("user1", "fake-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_wrong_user(self, memory_store):
        entry = await memory_store.save_short_term("user1", "data")
        result = await memory_store.delete_memory("user2", entry.id)
        assert result is False


class TestUpdateImportance:

    @pytest.mark.asyncio
    async def test_increase_importance(self, memory_store):
        entry = await memory_store.save_short_term("user1", "content")
        updated = await memory_store.update_importance("user1", entry.id, delta=0.3)
        assert updated.importance_score == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_clamp_to_one(self, memory_store):
        entry = await memory_store.save_short_term("user1", "content")
        updated = await memory_store.update_importance("user1", entry.id, delta=0.9)
        assert updated.importance_score == 1.0

    @pytest.mark.asyncio
    async def test_clamp_to_zero(self, memory_store):
        entry = await memory_store.save_short_term("user1", "content")
        updated = await memory_store.update_importance("user1", entry.id, delta=-1.0)
        assert updated.importance_score == 0.0

    @pytest.mark.asyncio
    async def test_nonexistent_raises(self, memory_store):
        with pytest.raises(ValueError):
            await memory_store.update_importance("user1", "fake-id", delta=0.1)


class TestSQLitePersistence:
    """Verify data survives across MemoryStore instances."""

    @pytest.mark.asyncio
    async def test_data_persists_across_restart(self, mock_embedding_service, tmp_path):
        db_path = str(tmp_path / "persist_test.db")

        # First instance: write data
        store1 = MemoryStore(
            embedding_service=mock_embedding_service,
            faiss_dimension=64,
            db_path=db_path,
        )
        await store1.initialize()
        await store1.save_short_term("user1", "persisted message")
        await store1.save_long_term("user1", "important fact", importance=0.9)

        await store1.close()

        # Second instance: read data back
        store2 = MemoryStore(
            embedding_service=mock_embedding_service,
            faiss_dimension=64,
            db_path=db_path,
        )
        await store2.initialize()

        all_memories = store2.get_all_memories("user1")
        await store2.close()
        assert len(all_memories) == 2
        contents = {m.content for m in all_memories}
        assert "persisted message" in contents
        assert "important fact" in contents

    @pytest.mark.asyncio
    async def test_delete_persists(self, mock_embedding_service, tmp_path):
        db_path = str(tmp_path / "delete_persist.db")

        store1 = MemoryStore(
            embedding_service=mock_embedding_service,
            faiss_dimension=64,
            db_path=db_path,
        )
        await store1.initialize()
        entry = await store1.save_short_term("user1", "to be deleted")
        await store1.delete_memory("user1", entry.id)
        await store1.close()

        store2 = MemoryStore(
            embedding_service=mock_embedding_service,
            faiss_dimension=64,
            db_path=db_path,
        )
        await store2.initialize()
        result = store2.get_all_memories("user1")
        await store2.close()
        assert result == []


class TestFAISSIndexAlignment:
    """Verify that FAISS index rows are correctly mapped to memory IDs."""

    @pytest.mark.asyncio
    async def test_index_id_map_maintained(self, memory_store):
        await memory_store.save_long_term("user1", "fact A", importance=0.7)
        await memory_store.save_long_term("user1", "fact B", importance=0.8)
        await memory_store.save_short_term("user1", "short term msg")
        await memory_store.save_long_term("user1", "fact C", importance=0.6)

        id_map = memory_store._index_id_map.get("user1", [])
        assert len(id_map) == 3  # Only vectored memories

        vectored = [
            m for m in memory_store.get_all_memories("user1")
            if m.vector is not None
        ]
        assert [m.id for m in vectored] == id_map

    @pytest.mark.asyncio
    async def test_search_returns_correct_entries(self, memory_store):
        await memory_store.save_short_term("user1", "ignored short term")
        entry_a = await memory_store.save_long_term("user1", "fact A", importance=0.9)
        entry_b = await memory_store.save_long_term("user1", "fact B", importance=0.8)

        # Use entry_a's vector as query to find it
        results = memory_store.search_memory("user1", entry_a.vector, top_k=2)
        result_ids = {r.id for r in results}
        assert entry_a.id in result_ids or entry_b.id in result_ids
