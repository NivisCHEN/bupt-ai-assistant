"""Pydantic domain models used across the BUPT AI assistant."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MemoryType(str, Enum):
    """Classification of a memory entry's persistence tier."""

    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    EPISODIC = "episodic"


class IntentType(str, Enum):
    """Recognized user-intent categories."""

    KNOWLEDGE = "knowledge"
    CHITCHAT = "chitchat"
    TASK_EXECUTION = "task_execution"
    CLARIFICATION = "clarification"


# ---------------------------------------------------------------------------
# Core data models
# ---------------------------------------------------------------------------

class MemoryEntry(BaseModel):
    """A single entry in the user memory system."""

    id: str
    type: MemoryType
    content: str
    summary: str
    timestamp: datetime
    importance_score: float = Field(ge=0.0, le=1.0)
    source_ref: Optional[str] = None
    vector: Optional[list[float]] = None
    user_id: str
    metadata: dict = Field(default_factory=dict)


class ChatMessage(BaseModel):
    """One message in a conversation turn."""

    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class ChatRequest(BaseModel):
    """Incoming chat request from a client."""

    user_id: str
    query: str
    session_id: str


class Source(BaseModel):
    """A single evidence source attached to a response."""

    id: str
    title: str
    snippet: str
    url: Optional[str] = None
    score: float
    timestamp: Optional[datetime] = None


class ChatResponse(BaseModel):
    """Outgoing chat response returned to the client."""

    answer: str
    sources: list[Source] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    confidence: float


# ---------------------------------------------------------------------------
# Intent & retrieval models
# ---------------------------------------------------------------------------

class IntentResult(BaseModel):
    """Result of intent classification on a user query."""

    intent: IntentType
    confidence: float
    entities: dict = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    """Aggregated result from the retrieval pipeline."""

    chunks: list[Source]
    query_vector: list[float]


# ---------------------------------------------------------------------------
# Document & user models
# ---------------------------------------------------------------------------

class DocumentChunk(BaseModel):
    """A chunk of a crawled / ingested document ready for indexing."""

    id: str
    content: str
    title: str
    source_url: str
    published_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    author: Optional[str] = None
    category: str
    metadata: dict = Field(default_factory=dict)
    vector: Optional[list[float]] = None


class UserProfile(BaseModel):
    """Persistent profile that captures user preferences and behaviour."""

    user_id: str
    preferences: dict = Field(default_factory=dict)
    frequent_queries: list[str] = Field(default_factory=list)
    profile_summary: str = ""
    last_active: datetime = Field(default_factory=datetime.now)
