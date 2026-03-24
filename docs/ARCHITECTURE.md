# Architecture – BUPT AI Campus Assistant

## Overview

A RAG-based intelligent campus assistant for Beijing University of Posts and Telecommunications (BUPT). The system answers campus-related questions by retrieving relevant documents from a knowledge base and generating responses using a large language model, while maintaining per-user conversational memory.

## System Diagram

```
                        ┌─────────────────────┐
                        │   FastAPI (app.py)   │
                        │  CORS · Logging MW   │
                        └──────────┬──────────┘
                                   │
               ┌───────────────────┼───────────────────┐
               │                   │                   │
    ┌──────────▼──────────┐ ┌──────▼───────┐ ┌────────▼─────────┐
    │    API Routes        │ │  Dependency  │ │ BackgroundScheduler│
    │  (src/api/routes.py) │ │  Injection   │ │ (src/scheduler/)   │
    └──────────┬──────────┘ │  (deps.py)   │ │ • weekly compress  │
               │            └──────────────┘ │ • session timeout  │
               │                             │ • daily profiling  │
    ┌──────────▼──────────┐                  └──────────────────┘
    │  DialogueManager     │
    │  (src/dialogue/)     │
    │  ├─ IntentRouter     │
    │  ├─ PromptBuilder    │
    │  └─ handle_message() │
    └───┬──────┬───────┬───┘
        │      │       │
   ┌────▼──┐ ┌─▼────┐ ┌▼──────────┐
   │Memory │ │Hybrid│ │ LLMClient │
   │Manager│ │Retriv.│ │(DeepSeek) │
   └───┬───┘ └──┬───┘ └───────────┘
       │        │
  ┌────▼────┐ ┌─▼──────────┐
  │ Memory  │ │ BM25+FAISS │
  │ Store   │ │ + Reranker │
  └─────────┘ └────────────┘
```

## Module Reference

### `app.py` – Application Entry Point

FastAPI application with CORS middleware, request logging, startup/shutdown lifecycle, and the background scheduler. Runs via `uvicorn`.

### `config/settings.py` – Configuration

Pydantic-settings based configuration. All values are overridable via `BUPT_`-prefixed environment variables or a `.env` file. Sub-settings: App, LLM, Embedding, FAISS, Memory, Crawler, Redis, Privacy.

### `src/api/` – HTTP Layer

- **`routes.py`** – FastAPI router with endpoints:
  - `POST /api/chat` – main chat endpoint
  - `GET /api/health` – health check
  - `POST /api/memory/{user_id}/search` – search user memories
  - `GET /api/memory/{user_id}/history` – conversation history
  - `DELETE /api/memory/{user_id}/{memory_id}` – delete memory (with confirmation token)
  - `POST /api/admin/reindex` – trigger re-indexing
  - `POST /api/admin/crawl/{source_name}` – trigger crawl
  - `GET /api/admin/stats` – system statistics

- **`dependencies.py`** – Singleton dependency injection for all services.

### `src/dialogue/` – Conversation Management

- **`router.py`** (`IntentRouter`) – Classifies user queries into intents: `KNOWLEDGE`, `CHITCHAT`, `TASK_EXECUTION`, `CLARIFICATION`. Uses keyword matching and LLM fallback.
- **`prompt_builder.py`** (`PromptBuilder`) – Constructs system/user prompts for RAG and chitchat flows. Formats retrieved sources, conversation history, and user memories.
- **`manager.py`** (`DialogueManager`) – Main orchestrator. Routes intent → retrieves context → builds prompt → generates response → records memory. Returns `ChatResponse` with sources and intent metadata.

### `src/retriever/` – Hybrid Retrieval

- **`faiss_store.py`** (`FAISSStore`) – FAISS vector index wrapper. Supports `build_index`, `search`, `save_index`, `load_index`.
- **`hybrid_retriever.py`** (`HybridRetriever`) – Combines BM25 (sparse) and FAISS (dense) scores via Reciprocal Rank Fusion (RRF). Falls back to dense-only when BM25 corpus is empty.
- **`reranker.py`** (`Reranker`) – Score-based reranking with configurable weights for dense, sparse, and freshness signals.

### `src/embedding/` – Text Embedding

- **`service.py`** (`EmbeddingService`) – Wraps the BGE-M3 model (via `sentence-transformers`). Provides `encode()` for batch encoding and `encode_query()` for single queries.

### `src/memory/` – Tiered Memory System

Inspired by MemGPT / OpenClaw architecture with three tiers:

- **Short-term** – Current session context (TTL-based, default 30 min)
- **Long-term** – Persistent user knowledge and preferences (embedding-indexed)
- **Episodic** – Significant events and interactions

Components:
- **`store.py`** (`MemoryStore`) – CRUD operations for all memory tiers. JSON file-based persistence with per-user FAISS indexing.
- **`compressor.py`** (`MemoryCompressor`) – Merges similar memories, scores importance, archives low-value entries.
- **`manager.py`** (`MemoryManager`) – Lifecycle orchestrator: `record_conversation`, `promote_to_long_term`, `extract_user_profile` (async, LLM-based), `run_maintenance`, `retrieve_context` (hierarchical retrieval with deduplication).

### `src/llm/` – LLM Client

- **`client.py`** (`LLMClient`) – Async OpenAI-compatible client targeting DeepSeek API. Supports streaming and non-streaming generation.

### `src/crawler/` – Web Crawling

- **`base.py`** – `DataSource` definitions for BUPT websites (教务处, 图书馆, 研究生院, campus news, etc.)
- **`spider.py`** (`BUPTSpider`) – Async HTTP spider using `httpx` + `BeautifulSoup`. Respects `robots.txt`, implements rate limiting and retries.
- **`processor.py`** – Document processing pipeline (HTML cleaning, deduplication, metadata extraction).
- **`scheduler.py`** – Crawl job scheduler for periodic updates.

### `src/scheduler/` – Background Tasks

- **`background.py`** (`BackgroundScheduler`) – APScheduler-based async scheduler with three jobs:
  1. Weekly memory compression (per-user)
  2. Session timeout detection (every 5 min)
  3. Daily user profile extraction

### `src/utils/` – Utilities

- **`privacy.py`** – PII detection and masking for student IDs, phone numbers, and ID cards.
- **`text_processing.py`** – HTML cleaning (`clean_html`) and text chunking (`chunk_text`) with configurable overlap.

### `src/models.py` – Shared Data Models

Pydantic models: `ChatRequest`, `ChatResponse`, `Source`, `MemoryEntry`, `IntentType` enum, `Document`, etc.

## Data Flow: Chat Request

1. User sends `POST /api/chat` with `user_id`, `query`, `session_id`
2. `IntentRouter` classifies intent (KNOWLEDGE / CHITCHAT / TASK_EXECUTION / CLARIFICATION)
3. For KNOWLEDGE intent:
   - `EmbeddingService.encode_query()` encodes the query
   - `HybridRetriever.retrieve()` fetches top-k documents (BM25 + FAISS + RRF)
   - `Reranker.rerank()` re-scores results
   - `MemoryManager.retrieve_context()` fetches relevant user memories
4. `PromptBuilder` constructs the system + user prompt with sources and history
5. `LLMClient.generate()` produces the response
6. `MemoryManager.record_conversation()` saves the exchange
7. `ChatResponse` returned with answer, sources, and intent

## Data Flow: Knowledge Base Build (Offline)

1. `scripts/build_knowledge_base.py` loads documents from files and/or crawlers
2. Documents are cleaned and chunked (`text_processing.chunk_text`)
3. Chunks are embedded via `EmbeddingService.encode()`
4. FAISS index is built and saved to `data/indices/`

## Configuration

All settings are managed via `config/settings.py` using pydantic-settings. Override via environment variables with `BUPT_` prefix or a `.env` file.

Key settings:
| Setting | Default | Description |
|---------|---------|-------------|
| `LLM.model_name` | `deepseek-chat` | LLM model identifier |
| `EMBEDDING.model_name` | `BAAI/bge-m3` | Embedding model |
| `EMBEDDING.dimension` | `1024` | Vector dimension |
| `MEMORY.short_term_ttl` | `1800` | Session memory TTL (seconds) |
| `MEMORY.importance_threshold` | `0.5` | Threshold for memory archival |
| `FAISS.top_k` | `10` | Retrieval candidates |
| `FAISS.rerank_top_k` | `5` | Final results after reranking |

## Testing

```bash
pytest tests/ -v
```

- **Unit tests** (`tests/unit/`) – Cover models, FAISS store, reranker, memory store, privacy, text processing, prompt builder
- **Integration tests** (`tests/integration/`) – End-to-end dialogue flow with mocked LLM and retriever
- **Fixtures** (`tests/fixtures/`) – Sample campus Q&A queries and multi-turn scenarios

## Performance Targets

| Metric | Target |
|--------|--------|
| Precision@5 | >= 0.70 |
| Recall@10 | >= 0.80 |
| Factual accuracy | >= 85% |
| Latency (cached) | < 2.5s |
| Latency (full retrieval) | < 6s |
| Memory query latency | < 200ms |
