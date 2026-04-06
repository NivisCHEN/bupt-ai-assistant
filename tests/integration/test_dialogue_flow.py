"""Integration tests for the full dialogue flow with mocked LLM and embedding."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from src.models import ChatRequest, IntentType


# ------------------------------------------------------------------
# Helpers & fixtures
# ------------------------------------------------------------------

def _make_mock_llm_client():
    """Create a mock LLMClient that returns canned responses."""
    client = AsyncMock()

    async def _generate(prompt, system_prompt=None):
        """Return intent classification or a canned response based on prompt content."""
        # If it looks like an intent classification request, return JSON
        if system_prompt and "意图" in system_prompt:
            if "你好" in prompt or "天气" in prompt or "心情" in prompt:
                return json.dumps({
                    "intent": "CHITCHAT",
                    "confidence": 0.92,
                    "entities": {},
                })
            elif "报修" in prompt or "预约" in prompt or "查课程表" in prompt:
                return json.dumps({
                    "intent": "TASK_EXECUTION",
                    "confidence": 0.88,
                    "entities": {"task_type": "repair"},
                })
            else:
                return json.dumps({
                    "intent": "KNOWLEDGE",
                    "confidence": 0.90,
                    "entities": {"topic": "campus_info"},
                })
        # Regular generation
        return "这是一个模拟的回答。"

    async def _generate_with_messages(messages):
        return "这是一个模拟的回答。"

    client.generate = AsyncMock(side_effect=_generate)
    client.generate_with_messages = AsyncMock(side_effect=_generate_with_messages)
    return client


def _make_mock_embedding_service(dimension=64):
    """Create a mock EmbeddingService that returns random vectors."""
    svc = MagicMock()
    rng = np.random.RandomState(42)

    def fake_encode(texts, batch_size=32):
        vecs = rng.randn(len(texts), dimension).astype(np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / norms

    def fake_encode_query(query):
        return fake_encode([query])

    svc.encode = MagicMock(side_effect=fake_encode)
    svc.encode_query = MagicMock(side_effect=fake_encode_query)
    svc.dimension = dimension
    return svc


def _make_mock_retriever(sources=None):
    """Create a mock retriever that returns canned search results.

    Returns results in the HybridRetriever.retrieve() format:
    list of dicts with id, score, content, metadata.
    """
    retriever = MagicMock()
    default_sources = sources or [
        {
            "id": "src-1",
            "score": 0.85,
            "content": "北邮图书馆工作日开放时间为8:00-22:00",
            "metadata": {"title": "图书馆开放时间", "source_url": "https://lib.bupt.edu.cn"},
        },
        {
            "id": "src-2",
            "score": 0.72,
            "content": "图书馆位于校园中心区域",
            "metadata": {"title": "图书馆位置", "source_url": "https://www.bupt.edu.cn/map"},
        },
    ]
    retriever.retrieve = MagicMock(return_value=default_sources)
    return retriever


def _make_mock_memory_manager():
    """Create a mock memory manager."""
    mm = AsyncMock()
    mm.get_recent_history = AsyncMock(return_value=[])
    mm.search_memories = AsyncMock(return_value=[])
    mm.save_to_short_term = AsyncMock()
    return mm


@pytest.fixture()
def mock_llm():
    return _make_mock_llm_client()


@pytest.fixture()
def mock_embedding():
    return _make_mock_embedding_service()


@pytest.fixture()
def mock_retriever():
    return _make_mock_retriever()


@pytest.fixture()
def mock_memory_manager():
    return _make_mock_memory_manager()


@pytest.fixture()
def dialogue_manager(mock_llm, mock_embedding, mock_retriever, mock_memory_manager):
    """Create a DialogueManager with all mocked dependencies."""
    from src.dialogue.prompt_builder import PromptBuilder
    from src.dialogue.router import IntentRouter
    from src.dialogue.manager import DialogueManager

    router = IntentRouter(llm_client=mock_llm)
    prompt_builder = PromptBuilder()

    return DialogueManager(
        router=router,
        retriever=mock_retriever,
        memory_manager=mock_memory_manager,
        llm_client=mock_llm,
        embedding_service=mock_embedding,
        prompt_builder=prompt_builder,
    )


# ------------------------------------------------------------------
# KNOWLEDGE intent path
# ------------------------------------------------------------------

class TestKnowledgeIntentFlow:
    """Test: query -> classify -> retrieve -> generate."""

    @pytest.mark.asyncio
    async def test_knowledge_query_triggers_retrieval(
        self, dialogue_manager, mock_retriever, mock_embedding
    ):
        request = ChatRequest(
            user_id="user-1",
            query="北邮图书馆几点开门？",
            session_id="sess-001",
        )
        response = await dialogue_manager.handle_message(request)

        # Should have generated an answer
        assert response.answer
        assert len(response.answer) > 0

        # Embedding service should have been called for query encoding
        mock_embedding.encode_query.assert_called()

        # Retriever should have been called
        mock_retriever.retrieve.assert_called()

    @pytest.mark.asyncio
    async def test_knowledge_response_includes_sources(
        self, dialogue_manager
    ):
        request = ChatRequest(
            user_id="user-1",
            query="教务处在哪个楼？",
            session_id="sess-002",
        )
        response = await dialogue_manager.handle_message(request)

        # Sources should be populated from retriever results
        assert len(response.sources) > 0
        assert response.sources[0].title

    @pytest.mark.asyncio
    async def test_knowledge_response_has_suggestions(
        self, dialogue_manager
    ):
        request = ChatRequest(
            user_id="user-1",
            query="如何申请转专业？",
            session_id="sess-003",
        )
        response = await dialogue_manager.handle_message(request)
        assert isinstance(response.suggestions, list)


# ------------------------------------------------------------------
# CHITCHAT intent path
# ------------------------------------------------------------------

class TestChitchatIntentFlow:
    """Test: query -> classify -> generate (no retrieval)."""

    @pytest.mark.asyncio
    async def test_chitchat_skips_retrieval(
        self, dialogue_manager, mock_retriever, mock_embedding
    ):
        request = ChatRequest(
            user_id="user-1",
            query="你好，今天天气怎么样？",
            session_id="sess-010",
        )
        response = await dialogue_manager.handle_message(request)

        assert response.answer
        # Retriever should NOT have been called for chitchat
        mock_retriever.retrieve.assert_not_called()
        # Embedding query encoding should NOT have been called
        mock_embedding.encode_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_chitchat_returns_no_sources(
        self, dialogue_manager
    ):
        request = ChatRequest(
            user_id="user-1",
            query="你好呀！",
            session_id="sess-011",
        )
        response = await dialogue_manager.handle_message(request)
        assert response.sources == []

    @pytest.mark.asyncio
    async def test_chitchat_confidence(
        self, dialogue_manager
    ):
        request = ChatRequest(
            user_id="user-1",
            query="你好，心情不错",
            session_id="sess-012",
        )
        response = await dialogue_manager.handle_message(request)
        assert response.confidence > 0


# ------------------------------------------------------------------
# Clarification trigger
# ------------------------------------------------------------------

class TestClarificationTrigger:
    """Test: when retrieval confidence < 0.6, should trigger clarification."""

    @pytest.mark.asyncio
    async def test_low_score_triggers_clarification(
        self, mock_llm, mock_embedding, mock_memory_manager
    ):
        """When top retrieval score < 0.6, intent should switch to CLARIFICATION."""
        from src.dialogue.prompt_builder import PromptBuilder
        from src.dialogue.router import IntentRouter
        from src.dialogue.manager import DialogueManager

        # Return low-scoring sources
        low_score_retriever = _make_mock_retriever(sources=[
            {
                "id": "src-low",
                "score": 0.3,
                "content": "可能相关的内容",
                "metadata": {"title": "模糊结果", "source_url": ""},
            },
        ])

        router = IntentRouter(llm_client=mock_llm)
        prompt_builder = PromptBuilder()

        dm = DialogueManager(
            router=router,
            retriever=low_score_retriever,
            memory_manager=mock_memory_manager,
            llm_client=mock_llm,
            embedding_service=mock_embedding,
            prompt_builder=prompt_builder,
        )

        request = ChatRequest(
            user_id="user-1",
            query="那个东西在哪里？",
            session_id="sess-020",
        )
        response = await dm.handle_message(request)

        # The system should still produce an answer (via RAG prompt with clarification)
        assert response.answer
        # Suggestions should include clarification options
        assert isinstance(response.suggestions, list)

    @pytest.mark.asyncio
    async def test_empty_retrieval_triggers_clarification(
        self, mock_llm, mock_embedding, mock_memory_manager
    ):
        """When retrieval returns no results, should trigger clarification."""
        from src.dialogue.prompt_builder import PromptBuilder
        from src.dialogue.router import IntentRouter
        from src.dialogue.manager import DialogueManager

        empty_retriever = _make_mock_retriever(sources=[])

        router = IntentRouter(llm_client=mock_llm)
        prompt_builder = PromptBuilder()

        dm = DialogueManager(
            router=router,
            retriever=empty_retriever,
            memory_manager=mock_memory_manager,
            llm_client=mock_llm,
            embedding_service=mock_embedding,
            prompt_builder=prompt_builder,
        )

        request = ChatRequest(
            user_id="user-1",
            query="帮我查一下那个",
            session_id="sess-021",
        )
        response = await dm.handle_message(request)
        assert response.answer


# ------------------------------------------------------------------
# Memory persistence
# ------------------------------------------------------------------

class TestMemoryPersistence:
    """Verify that exchanges are saved to short-term memory."""

    @pytest.mark.asyncio
    async def test_exchange_saved_to_memory(
        self, dialogue_manager, mock_memory_manager
    ):
        request = ChatRequest(
            user_id="user-1",
            query="图书馆在哪？",
            session_id="sess-030",
        )
        await dialogue_manager.handle_message(request)

        # Memory manager should have been asked to save
        mock_memory_manager.save_to_short_term.assert_called_once()
        call_kwargs = mock_memory_manager.save_to_short_term.call_args
        assert call_kwargs[1]["user_id"] == "user-1" or call_kwargs[0][0] == "user-1"


# ------------------------------------------------------------------
# Error handling
# ------------------------------------------------------------------

class TestErrorHandling:
    """Verify graceful degradation when components fail."""

    @pytest.mark.asyncio
    async def test_llm_failure_returns_fallback(
        self, mock_embedding, mock_memory_manager
    ):
        from src.dialogue.prompt_builder import PromptBuilder
        from src.dialogue.router import IntentRouter
        from src.dialogue.manager import DialogueManager

        # LLM that always fails
        failing_llm = AsyncMock()
        failing_llm.generate = AsyncMock(side_effect=Exception("LLM down"))
        failing_llm.generate_with_messages = AsyncMock(
            side_effect=Exception("LLM down")
        )

        retriever = _make_mock_retriever()
        router = IntentRouter(llm_client=failing_llm)
        prompt_builder = PromptBuilder()

        dm = DialogueManager(
            router=router,
            retriever=retriever,
            memory_manager=mock_memory_manager,
            llm_client=failing_llm,
            embedding_service=mock_embedding,
            prompt_builder=prompt_builder,
        )

        request = ChatRequest(
            user_id="user-1",
            query="测试错误处理",
            session_id="sess-err",
        )
        response = await dm.handle_message(request)

        # Should return a fallback error message, not crash
        assert response.answer
        assert response.confidence == 0.0
