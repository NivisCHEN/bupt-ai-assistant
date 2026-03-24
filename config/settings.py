"""Application settings managed via pydantic-settings.

All configuration values can be overridden through environment variables
prefixed with ``BUPT_`` or by placing them in a ``.env`` file at the
project root.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    """General application metadata."""

    name: str = "bupt-ai-assistant"
    version: str = "0.1.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000


class LLMSettings(BaseSettings):
    """Settings for the large-language-model backend."""

    api_key: str = Field(default="", description="LLM API key, loaded from env")
    base_url: str = "https://api.deepseek.com/v1"
    model_name: str = "deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 2048


class EmbeddingSettings(BaseSettings):
    """Settings for the text-embedding model (BGE-M3)."""

    model_name: str = "BAAI/bge-m3"
    dimension: int = 1024
    device: str = "cpu"
    batch_size: int = 32


class FAISSSettings(BaseSettings):
    """Settings for FAISS vector indices."""

    school_index_path: str = "data/indices/school.index"
    user_index_prefix: str = "data/indices/user_"
    top_k: int = 10
    rerank_top_k: int = 5


class MemorySettings(BaseSettings):
    """Settings for the multi-tier memory system."""

    short_term_ttl: int = 1800  # seconds
    long_term_retention_days: int = 730
    compression_interval_days: int = 7
    importance_threshold: float = 0.5
    max_memory_entries: int = 100_000


class CrawlerSettings(BaseSettings):
    """Settings for the web crawler."""

    concurrent_per_domain: int = 5
    retry_max: int = 3
    respect_robots_txt: bool = True
    user_agent: str = (
        "BUPTAssistantBot/1.0 (+https://www.bupt.edu.cn; academic-use)"
    )


class RedisSettings(BaseSettings):
    """Settings for the Redis connection."""

    host: str = "localhost"
    port: int = 6379
    db: int = 0


class PrivacySettings(BaseSettings):
    """Settings for PII detection and masking."""

    pii_patterns: dict[str, str] = {
        "student_id": r"\b\d{10}\b",
        "phone": r"1[3-9]\d{9}",
        "id_card": r"\d{17}[\dXx]",
    }


class Settings(BaseSettings):
    """Root settings object that aggregates all sub-settings."""

    model_config = {"env_prefix": "BUPT_", "env_file": ".env", "extra": "ignore"}

    app: AppSettings = AppSettings()
    llm: LLMSettings = LLMSettings()
    embedding: EmbeddingSettings = EmbeddingSettings()
    faiss: FAISSSettings = FAISSSettings()
    memory: MemorySettings = MemorySettings()
    crawler: CrawlerSettings = CrawlerSettings()
    redis: RedisSettings = RedisSettings()
    privacy: PrivacySettings = PrivacySettings()


# Module-level singleton for convenient imports.
settings = Settings()
