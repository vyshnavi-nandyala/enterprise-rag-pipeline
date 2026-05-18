from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/ragdb"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # API Authentication
    api_key: str = "changeme-api-key"

    # Anthropic
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 2048

    # OpenAI (embeddings)
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # RAG
    chunk_size: int = 512
    chunk_overlap: int = 64
    top_k: int = 5
    min_similarity: float = 0.3

    # Observability
    log_level: str = "INFO"
    audit_log_path: str = "/tmp/audit.jsonl"

    # SLOs (milliseconds)
    retrieval_slo_p95_ms: float = 3000.0
    e2e_slo_p95_ms: float = 8000.0

    # CORS
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
