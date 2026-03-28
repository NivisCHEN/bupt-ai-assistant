FROM python:3.11-slim AS base

WORKDIR /app

# Install system dependencies for faiss-cpu
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] pydantic pydantic-settings \
    faiss-cpu sentence-transformers openai aiosqlite \
    apscheduler jieba loguru httpx beautifulsoup4 \
    rank_bm25 tenacity

COPY . .

# Create data directory for SQLite and indices
RUN mkdir -p data

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
