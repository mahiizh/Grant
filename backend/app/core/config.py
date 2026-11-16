from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PROJECT_NAME: str = "GraphRAG Intelligence Lab"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # PostgreSQL
    # Host port 5433 by default so the Docker container can coexist with a
    # native PostgreSQL install that already owns 5432. Keep this in sync with
    # POSTGRES_PORT in infra/docker-compose.yml and .env.example.
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "graphrag_lab"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_GRPC_PORT: int = 6334
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION: str = "grant_chunks"

    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "graphrag_password"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_url(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    # Model Layer (LiteLLM + FastEmbed + CrossEncoder)
    LITELLM_API_BASE: str | None = None
    GEMINI_API_KEY: str | None = None
    LLM_MODEL: str = "gemini/gemini-3.5-flash-lite"
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIM: int = 384
    SPARSE_MODEL: str = "Qdrant/bm25"
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    ACQUISITION_ENABLED: bool = False
    MAX_ACQUISITION_CALLS: int = 3
    MIN_TRUST_TO_CITE: float = 0.7

    # LLM response cache. Keyed by (model, prompt hash) so repeated eval runs
    # do not pay for the same completion twice. Cache hits cost $0 in the run.
    LLM_CACHE_ENABLED: bool = True
    LLM_CACHE_DIR: str = ".llm_cache"
    LLM_MAX_BUDGET_PER_RUN: float = 0.50

    # Evaluation data paths. Override these in tests so runs never write into
    # tracked files under evals/.
    EVAL_GOLDEN_DIR: str | None = None
    EVAL_CANDIDATES_DIR: str | None = None
    # Isolated stores for `make eval`: a dedicated database and Qdrant
    # collection so an eval run cannot mutate the developer database.
    EVAL_POSTGRES_DB: str = "graphrag_lab_eval"
    EVAL_QDRANT_COLLECTION: str = "grant_chunks_eval"
    EVAL_CONCURRENCY: int = 2
    # LLM judge (DeepEval GEval). Off by default so hermetic runs never call a
    # provider; `make eval JUDGE=1` turns it on.
    EVAL_JUDGE_ENABLED: bool = False
    EVAL_JUDGE_MODEL: str | None = None
    EVAL_JUDGE_THRESHOLD: float = 0.5

    # Observability
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4318"
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # Dev Users mapping for X-Dev-User header authentication
    DEV_USERS: dict[str, dict[str, Any]] = Field(
        default_factory=lambda: {
            "alice": {
                "user_id": "usr_alice_01",
                "name": "Alice Chen",
                "allowed_scopes": ["data-platform", "public"],
                "roles": ["engineer", "data-lead"],
                "groups": ["data-platform"],
            },
            "bob": {
                "user_id": "usr_bob_02",
                "name": "Bob Kumar",
                "allowed_scopes": ["sre", "public"],
                "roles": ["incident-commander", "sre-lead"],
                "groups": ["sre"],
            },
            "elena": {
                "user_id": "usr_elena_03",
                "name": "Elena Rostova",
                "allowed_scopes": ["payments", "public"],
                "roles": ["payments-lead"],
                "groups": ["payments"],
            },
            "dave": {
                "user_id": "usr_dave_04",
                "name": "Dave Miller",
                "allowed_scopes": ["core-banking", "public"],
                "roles": ["banking-lead"],
                "groups": ["core-banking"],
            },
            "auditor": {
                "user_id": "usr_auditor_05",
                "name": "Executive Auditor",
                "allowed_scopes": ["executive-audit", "public"],
                "roles": ["auditor", "executive"],
                "groups": ["audit-council"],
            },
            "admin": {
                "user_id": "usr_admin_00",
                "name": "Platform Admin",
                "allowed_scopes": [
                    "data-platform",
                    "payments",
                    "core-banking",
                    "sre",
                    "executive-audit",
                    "public",
                ],
                "roles": ["admin"],
                "groups": ["platform-admins"],
            },
        }
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
