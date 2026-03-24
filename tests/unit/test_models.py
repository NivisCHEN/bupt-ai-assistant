"""Tests for Pydantic domain models."""

from datetime import datetime

import pytest

from src.models import (
    MemoryEntry,
    MemoryType,
    IntentType,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Source,
    IntentResult,
    RetrievalResult,
    DocumentChunk,
    UserProfile,
)


class TestMemoryEntry:

    def test_creation_with_required_fields(self):
        entry = MemoryEntry(
            id="mem-001",
            type=MemoryType.SHORT_TERM,
            content="用户问了图书馆开放时间",
            summary="图书馆开放时间",
            timestamp=datetime(2025, 6, 1, 10, 0),
            importance_score=0.7,
            user_id="user-123",
        )
        assert entry.id == "mem-001"
        assert entry.type == MemoryType.SHORT_TERM
        assert entry.importance_score == 0.7
        assert entry.source_ref is None
        assert entry.vector is None
        assert entry.metadata == {}

    def test_creation_with_all_fields(self):
        entry = MemoryEntry(
            id="mem-002",
            type=MemoryType.LONG_TERM,
            content="重要知识",
            summary="摘要",
            timestamp=datetime.now(),
            importance_score=0.9,
            source_ref="https://www.bupt.edu.cn",
            vector=[0.1, 0.2, 0.3],
            user_id="user-456",
            metadata={"category": "academic"},
        )
        assert entry.vector == [0.1, 0.2, 0.3]
        assert entry.metadata["category"] == "academic"

    def test_importance_score_bounds(self):
        with pytest.raises(Exception):
            MemoryEntry(
                id="x",
                type=MemoryType.SHORT_TERM,
                content="c",
                summary="s",
                timestamp=datetime.now(),
                importance_score=1.5,
                user_id="u",
            )
        with pytest.raises(Exception):
            MemoryEntry(
                id="x",
                type=MemoryType.SHORT_TERM,
                content="c",
                summary="s",
                timestamp=datetime.now(),
                importance_score=-0.1,
                user_id="u",
            )


class TestMemoryType:

    def test_enum_values(self):
        assert MemoryType.SHORT_TERM.value == "short_term"
        assert MemoryType.LONG_TERM.value == "long_term"
        assert MemoryType.EPISODIC.value == "episodic"

    def test_from_string(self):
        assert MemoryType("short_term") == MemoryType.SHORT_TERM


class TestIntentType:

    def test_enum_values(self):
        assert IntentType.KNOWLEDGE.value == "knowledge"
        assert IntentType.CHITCHAT.value == "chitchat"
        assert IntentType.TASK_EXECUTION.value == "task_execution"
        assert IntentType.CLARIFICATION.value == "clarification"

    def test_all_members(self):
        assert len(IntentType) == 4


class TestChatRequest:

    def test_valid_request(self):
        req = ChatRequest(
            user_id="user-1",
            query="北邮图书馆几点开门？",
            session_id="sess-001",
        )
        assert req.user_id == "user-1"
        assert req.query == "北邮图书馆几点开门？"

    def test_missing_required_field(self):
        with pytest.raises(Exception):
            ChatRequest(user_id="u", query="q")  # missing session_id


class TestChatResponse:

    def test_valid_response(self):
        resp = ChatResponse(
            answer="图书馆早上8点开门",
            confidence=0.95,
        )
        assert resp.answer == "图书馆早上8点开门"
        assert resp.sources == []
        assert resp.suggestions == []
        assert resp.confidence == 0.95

    def test_response_with_sources(self):
        src = Source(id="s1", title="图书馆", snippet="开放时间", score=0.9)
        resp = ChatResponse(
            answer="answer",
            sources=[src],
            suggestions=["了解更多"],
            confidence=0.8,
        )
        assert len(resp.sources) == 1
        assert resp.sources[0].title == "图书馆"


class TestSource:

    def test_creation(self):
        src = Source(id="s1", title="Title", snippet="Snip", score=0.85)
        assert src.url is None
        assert src.timestamp is None

    def test_with_optional_fields(self):
        src = Source(
            id="s2",
            title="T",
            snippet="S",
            score=0.7,
            url="https://example.com",
            timestamp=datetime.now(),
        )
        assert src.url == "https://example.com"


class TestIntentResult:

    def test_creation(self):
        ir = IntentResult(
            intent=IntentType.KNOWLEDGE,
            confidence=0.9,
        )
        assert ir.entities == {}

    def test_with_entities(self):
        ir = IntentResult(
            intent=IntentType.TASK_EXECUTION,
            confidence=0.85,
            entities={"task_type": "repair", "location": "学一楼"},
        )
        assert ir.entities["task_type"] == "repair"


class TestRetrievalResult:

    def test_creation(self):
        src = Source(id="c1", title="T", snippet="S", score=0.8)
        rr = RetrievalResult(chunks=[src], query_vector=[0.1, 0.2])
        assert len(rr.chunks) == 1
        assert len(rr.query_vector) == 2


class TestDocumentChunk:

    def test_creation(self):
        dc = DocumentChunk(
            id="doc-1",
            content="图书馆位于教三楼",
            title="校园设施",
            source_url="https://www.bupt.edu.cn",
            category="facility",
        )
        assert dc.author is None
        assert dc.vector is None


class TestUserProfile:

    def test_creation(self):
        up = UserProfile(user_id="user-1")
        assert up.preferences == {}
        assert up.frequent_queries == []
        assert up.profile_summary == ""
