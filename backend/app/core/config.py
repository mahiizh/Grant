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
    NEO4J_DATABASE: str = "neo4j"

    # Redis. DB 0 is the developer cache; tests must use a separate DB so a
    # helper process cannot poison live cache entries.
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_url(self) -> str:
        if self.REDIS_PASSWORD:
            return (
                f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:"
                f"{self.REDIS_PORT}/{self.REDIS_DB}"
            )
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # Model Layer (LiteLLM + FastEmbed + CrossEncoder)
    LITELLM_API_BASE: str | None = None
    GEMINI_API_KEY: str | None = None
    LLM_MODEL: str = "gemini/gemini-3.5-flash-lite"
    LITELLM_TIMEOUT_SECONDS: float = 30.0
    LITELLM_MAX_ATTEMPTS: int = 2
    ASK_TOTAL_BUDGET_SECONDS: float = 45.0
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIM: int = 384
    SPARSE_MODEL: str = "Qdrant/bm25"
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    # ONNX int8 build of the same MiniLM-L-6 cross-encoder. It is warmed once
    # at startup and scored in a single batch on a dedicated executor.
    RERANK_ONNX_MODEL: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    RRF_K: int = 60
    HYBRID_PREFETCH_MULTIPLIER: int = 5
    RERANK_TIMEOUT_SECONDS: float = 5.0
    RERANK_ENABLED: bool = True
    RERANK_MAX_CANDIDATES: int = 10
    RERANK_MAX_LENGTH: int = 256
    RERANK_TARGET_MS: float = 800.0
    RERANK_POOL_WORKERS: int = 1
    # Local inference runs on a bounded pool, never on the event loop. Startup
    # builds each local model once and warms it before the API accepts traffic.
    MODEL_POOL_WORKERS: int = 2
    MODEL_INFERENCE_TIMEOUT_SECONDS: float = 15.0
    MODEL_STARTUP_TIMEOUT_SECONDS: float = 120.0
    # Evidence scores are not comparable across scoring schemes. Cross-encoder
    # logits use one floor. RRF is rank-only and must never be used as a
    # relevance score, so hybrid evidence carries the chunk's Qdrant dense
    # cosine score for the gate (including when reranking times out).
    EVIDENCE_MIN_RERANK_SCORE: float = 0.0
    EVIDENCE_MIN_DENSE_COSINE: float = 0.55
    # Answer policy and web grounding. The chat API defaults to grounded_plus_web;
    # the eval runner explicitly defaults to grounded_only.
    ANSWER_POLICY: Literal["grounded_only", "grounded_plus_web"] = "grounded_plus_web"
    EVAL_ANSWER_POLICY: Literal["grounded_only", "grounded_plus_web"] = "grounded_only"
    GRASPREACH_SRC_PATH: str = r"C:\projects\grasp_agent\src"
    GRASPREACH_PYTHON: str | None = None
    WEB_SEARCH_RESULTS: int = 3
    WEB_MAX_PAGE_CHARS: int = 12000
    # Split each fetched page into bounded chunks before write-back, then keep
    # only the chunks most similar to the question for prompt context.
    WEB_CHUNK_CHARS: int = 1200
    WEB_CHUNK_OVERLAP_CHARS: int = 120
    WEB_TOP_CHUNKS: int = 5
    # Fetch well above the response cap so the wrapper can truncate locally
    # instead of failing a whole Ask on one oversized page.
    WEB_FETCH_MAX_BYTES: int = 2 * 1024 * 1024
    WEB_SEARCH_TIMEOUT_SECONDS: float = 8.0
    WEB_FETCH_TIMEOUT_SECONDS: float = 5.0
    WEB_TOTAL_BUDGET_SECONDS: float = 12.0
    WEB_CACHE_TTL_SECONDS: int = 600

    # Extraction (GLiNER, local, no LLM in ingestion)
    GLINER_MODEL: str = "urchade/gliner_medium-v2.1"
    GLINER_LABELS: list[str] = Field(
        default_factory=lambda: [
            "Person",
            "Organization",
            "Software",
            "Standard",
            "Control",
            "Process",
            "Concept",
            "Document",
            "Location",
        ]
    )
    GLINER_THRESHOLD: float = 0.5
    GLINER_THRESHOLD_BY_TYPE: dict[str, float] = Field(
        default_factory=lambda: {"Concept": 0.55, "Document": 0.55, "Location": 0.55}
    )
    GLINER_STOPLIST: list[str] = Field(
        default_factory=lambda: [
            "the organization",
            "organization",
            "supplier",
            "suppliers",
            "documented information",
            "changes",
            "information",
            "requirements",
            "requirement",
            "processes",
            "process",
            "controls",
            "control",
            "document",
            "documents",
            "personnel",
            "persons",
            "management",
            "top management",
            "interested parties",
            "relevant interested parties",
            "this document",
            "the document",
        ]
    )
    GLINER_WINDOW_TOKENS: int = 384
    GLINER_WINDOW_OVERLAP_TOKENS: int = 48
    GLINER_INFERENCE_TIMEOUT_SECONDS: float = 30.0

    # Entity resolution / co-occurrence
    QDRANT_ENTITY_COLLECTION: str = "grant_entities"
    ENTITY_RESOLUTION_THRESHOLD: float = 0.85
    ENTITY_RESOLUTION_TOP_K: int = 5
    ENTITY_SEED_MIN_COSINE: float = 0.35
    COOCCURRENCE_MIN_COUNT: int = 2
    COOCCURRENCE_TOP_K_PMI: int = 5

    # LLM response cache. Keyed by (model, prompt hash) so repeated eval runs
    # do not pay for the same completion twice. Cache hits cost $0 in the run.
    LLM_CACHE_ENABLED: bool = True
    LLM_CACHE_DIR: str = ".llm_cache"
    LLM_MAX_BUDGET_PER_RUN: float = 0.50

    # User-supplied corpus and evaluation data paths. There are no bundled
    # demo assets: ingestion and eval harnesses require explicit directories.
    CORPUS_DIR: str | None = None
    EVAL_CORPUS_DIR: str | None = None
    EVAL_GOLDEN_DIR: str | None = None
    EVAL_CANDIDATES_DIR: str | None = None
    # Isolated stores for `make eval`: a dedicated database and Qdrant
    # collection so an eval run cannot mutate the developer database.
    EVAL_POSTGRES_DB: str = "graphrag_lab_eval"
    EVAL_QDRANT_COLLECTION: str = "grant_chunks_eval"
    EVAL_QDRANT_ENTITY_COLLECTION: str = "grant_entities_eval"
    EVAL_REDIS_DB: int = 2
    EVAL_CONCURRENCY: int = 2
    # LLM judge (DeepEval GEval). Off by default so hermetic runs never call a
    # provider; `make eval JUDGE=1` turns it on.
    EVAL_JUDGE_ENABLED: bool = False
    EVAL_JUDGE_MODEL: str | None = None
    EVAL_JUDGE_THRESHOLD: float = 0.5

    # Observability
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # Dev Users mapping for X-Dev-User header authentication
    DEV_USERS: dict[str, dict[str, Any]] = Field(
        default_factory=lambda: {
            "alice": {
                "user_id": "usr_alice_01",
                "name": "Alice Chen",
                "shared_scopes": ["shared-analytics"],
            },
            "bob": {
                "user_id": "usr_bob_02",
                "name": "Bob Kumar",
                "shared_scopes": ["shared-operations"],
            },
            "elena": {
                "user_id": "usr_elena_03",
                "name": "Elena Rostova",
                "shared_scopes": ["shared-finance"],
            },
            "dave": {
                "user_id": "usr_dave_04",
                "name": "Dave Miller",
                "shared_scopes": ["shared-banking"],
            },
            "auditor": {
                "user_id": "usr_auditor_05",
                "name": "Executive Auditor",
                "shared_scopes": ["shared-audit"],
            },
            "admin": {
                "user_id": "usr_admin_00",
                "name": "Platform Admin",
                "shared_scopes": [],
                "is_admin": True,
            },
        }
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
