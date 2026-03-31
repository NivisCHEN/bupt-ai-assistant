"""Application settings managed via pydantic-settings.

All configuration values can be overridden through environment variables.
Each sub-settings class reads from its own prefix (e.g. ``BUPT_LLM__``
for LLM settings, ``BUPT_EMBEDDING__`` for embedding settings).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """General application metadata."""

    model_config = SettingsConfigDict(env_prefix="BUPT_APP__", extra="ignore")

    name: str = "bupt-ai-assistant"
    version: str = "0.1.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000


class LLMSettings(BaseSettings):
    """Settings for the large-language-model backend."""

    model_config = SettingsConfigDict(env_prefix="BUPT_LLM__", extra="ignore")

    api_key: str = Field(default="", description="LLM API key, loaded from env")
    base_url: str = "https://api.deepseek.com/v1"
    model_name: str = "deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 2048


class EmbeddingSettings(BaseSettings):
    """Settings for the text-embedding model (bge-small-zh-v1.5)."""

    model_config = SettingsConfigDict(env_prefix="BUPT_EMBEDDING__", extra="ignore")

    model_name: str = "BAAI/bge-small-zh-v1.5"
    dimension: int = 512
    device: str = "cpu"
    batch_size: int = 32


class FAISSSettings(BaseSettings):
    """Settings for FAISS vector indices."""

    model_config = SettingsConfigDict(env_prefix="BUPT_FAISS__", extra="ignore")

    school_index_path: str = "data/indices/school.index"
    user_index_prefix: str = "data/indices/user_"
    top_k: int = 10
    rerank_top_k: int = 5


class MemorySettings(BaseSettings):
    """Settings for the multi-tier memory system."""

    model_config = SettingsConfigDict(env_prefix="BUPT_MEMORY__", extra="ignore")

    short_term_ttl: int = 1800  # seconds
    long_term_retention_days: int = 730
    compression_interval_days: int = 7
    importance_threshold: float = 0.5
    max_memory_entries: int = 100_000


class CrawlerSettings(BaseSettings):
    """Settings for the web crawler."""

    model_config = SettingsConfigDict(env_prefix="BUPT_CRAWLER__", extra="ignore")

    concurrent_per_domain: int = 5
    retry_max: int = 3
    respect_robots_txt: bool = True
    user_agent: str = (
        "BUPTAssistantBot/1.0 (+https://www.bupt.edu.cn; academic-use)"
    )


class RedisSettings(BaseSettings):
    """Settings for the Redis connection."""

    model_config = SettingsConfigDict(env_prefix="BUPT_REDIS__", extra="ignore")

    host: str = "localhost"
    port: int = 6379
    db: int = 0


class PrivacySettings(BaseSettings):
    """Settings for PII detection and masking."""

    model_config = SettingsConfigDict(env_prefix="BUPT_PRIVACY__", extra="ignore")

    pii_patterns: dict[str, str] = {
        "student_id": r"\b\d{10}\b",
        "phone": r"1[3-9]\d{9}",
        "id_card": r"\d{17}[\dXx]",
    }


class Settings(BaseSettings):
    """Root settings object that aggregates all sub-settings."""

    model_config = SettingsConfigDict(env_prefix="BUPT_", env_file=".env", extra="ignore")

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
