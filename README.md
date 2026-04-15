# BUPT AI Campus Assistant

RAG-based intelligent campus assistant for Beijing University of Posts and Telecommunications (BUPT), featuring long-term memory, hybrid retrieval, and multi-turn dialogue management.

## Architecture

```
                    +-------------------+
                    |   FastAPI (app.py) |
                    +--------+----------+
                             |
              +--------------+--------------+
              |                             |
     +--------v--------+         +---------v---------+
     | IntentRouter     |         | BackgroundScheduler|
     | (dialogue/router)|         | (scheduler/)       |
     +--------+---------+         +--------------------+
              |
    +---------+---------+----------+
    |                   |          |
+---v---+         +-----v----+ +--v-----------+
|Memory |         |Hybrid    | |LLMClient     |
|Manager|         |Retriever | |(DeepSeek API)|
+---+---+         +-----+----+ +--------------+
    |                   |
+---v---+         +-----v----+
|FAISS  |         |BM25 +    |
|Store  |         |FAISS     |
+-------+         +----------+
```

## Key Features

- **Hybrid Retrieval**: BM25 (sparse) + FAISS/BGE-M3 (dense) with reciprocal rank fusion
- **Tiered Memory**: Short-term (session), long-term (user profile), episodic (events) inspired by MemGPT/OpenClaw
- **Intent Classification**: KNOWLEDGE / CHITCHAT / TASK_EXECUTION / CLARIFICATION
- **Auto Crawling**: Scheduled crawlers for BUPT websites (教务处, 图书馆, 研究生院, etc.)
- **Privacy**: PII detection and masking for student IDs, phone numbers, ID cards
- **Background Maintenance**: Automatic memory compression, profile extraction, session timeout handling

## Project Structure

```
bupt-ai-assistant/
├── app.py                      # FastAPI application entry point
├── config/
│   └── settings.py             # Pydantic-settings configuration
├── src/
│   ├── models.py               # Shared Pydantic data models
│   ├── api/                    # FastAPI routes and dependencies
│   │   ├── routes.py
│   │   └── dependencies.py
│   ├── crawler/                # Web crawling and data collection
│   │   ├── base.py             # Data source definitions
│   │   ├── spider.py           # Async HTTP spider
│   │   ├── processor.py        # Document processing pipeline
│   │   └── scheduler.py        # Crawl job scheduler
│   ├── embedding/              # BGE-M3 embedding service
│   │   └── service.py
│   ├── retriever/              # Hybrid retrieval engine
│   │   ├── faiss_store.py      # FAISS vector index
│   │   ├── hybrid_retriever.py # BM25 + FAISS fusion
│   │   └── reranker.py         # Score-based reranking
│   ├── memory/                 # Tiered memory system
│   │   ├── store.py            # Memory CRUD operations
│   │   ├── compressor.py       # LLM-based memory compression
│   │   └── manager.py          # Memory lifecycle orchestrator
│   ├── dialogue/               # Conversation management
│   │   ├── router.py           # Intent classification
│   │   ├── prompt_builder.py   # RAG prompt construction
│   │   └── manager.py          # Dialogue orchestrator
│   ├── llm/                    # LLM API client
│   │   └── client.py           # DeepSeek/OpenAI-compatible client
│   ├── scheduler/              # Background task scheduler
│   │   └── background.py       # Memory maintenance jobs
│   └── utils/
│       ├── privacy.py          # PII detection and masking
│       └── text_processing.py  # Text chunking and HTML cleaning
├── scripts/
│   ├── build_knowledge_base.py # Offline index builder
│   ├── seed_test_data.py       # Sample data generator
│   └── run_crawler.py          # Manual crawler trigger
├── tests/
│   ├── unit/                   # Unit tests for each module
│   ├── integration/            # End-to-end dialogue tests
│   └── fixtures/               # Test data and sample queries
├── data/
│   ├── raw/                    # Raw crawled documents
│   ├── processed/              # Cleaned and chunked data
│   └── indices/                # FAISS index files
└── docs/
    └── ARCHITECTURE.md         # Detailed architecture document
```

## Quick Start

```bash
# 1. Install dependencies
pip install -e .

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Seed test data and build knowledge base
python scripts/seed_test_data.py
python scripts/build_knowledge_base.py --source file

# 4. Run the server
python app.py
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

## API Usage

```bash
# Chat
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_001", "query": "北邮图书馆几点开门？", "session_id": "sess_001"}'

# Search user memory
curl -X POST http://localhost:8000/api/memory/user_001/search \
  -H "Content-Type: application/json" \
  -d '{"query": "图书馆", "top_k": 5}'
```

## Performance Targets

| Metric | Target |
|--------|--------|
| Precision@5 | >= 0.70 |
| Recall@10 | >= 0.80 |
| Factual accuracy | >= 85% |
| Latency (cached) | < 2.5s |
| Latency (full retrieval) | < 6s |
| Memory query latency | < 200ms |
| Memory capacity | >= 100k entries |

## Testing

```bash
pytest tests/ -v
```

## License

MIT
